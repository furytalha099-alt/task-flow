"""TaskFlow secure multi-tenant API."""
import hashlib
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse
import hmac
import os
import secrets
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from app.models import Group, GroupMembership
from app.schemas import GroupCreate, GroupResponse
from sqlalchemy import or_, text
import bcrypt
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError, jwt
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text
from sqlalchemy.orm import Session

load_dotenv()

from app.database import get_db
from app.models import (
    AuditEvent, AuthRefreshToken, AuthSession, Comment, Company, Project,
    Task, TaskPriority, TaskStatus, User, UserRole,
)
from app.schemas import (
    AuditEventResponse, CommentCreate, CommentResponse, CommentWithAuthorResponse, CompanyCreate,
    CompanyLogin, CompanyPatch, CompanyResponse, CompanyUpdate, MessageResponse,
    ProjectCreate, ProjectResponse, ProjectUpdate, TaskCreate, TaskResponse,
    TaskStatusUpdate, TaskUpdate, UserCreate, UserLogin, UserResponse,
)

SECRET_KEY = os.getenv("SECRET_KEY", "")
PLATFORM_MASTER_KEY = os.getenv("PLATFORM_MASTER_KEY", "")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").lower() in {"1", "true", "yes"}
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax").lower()
ENVIRONMENT = os.getenv("ENVIRONMENT", "").lower()
ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"
CSRF_COOKIE = "csrf_token"
ALLOWED_ORIGINS = [v.strip() for v in os.getenv("ALLOWED_ORIGINS", "").split(",") if v.strip()]
REDIS_URL = os.getenv("REDIS_URL", "")

if len(SECRET_KEY) < 32:
    raise RuntimeError("Set SECRET_KEY to a random value of at least 32 characters.")
if ENVIRONMENT not in {"development", "test", "production"}:
    raise RuntimeError("Set ENVIRONMENT to development, test, or production.")
if ACCESS_TOKEN_EXPIRE_MINUTES < 1:
    raise RuntimeError("ACCESS_TOKEN_EXPIRE_MINUTES must be positive.")
if REFRESH_TOKEN_EXPIRE_DAYS < 1 or COOKIE_SAMESITE not in {"lax", "strict", "none"}:
    raise RuntimeError("Invalid refresh-token or cookie configuration.")
if COOKIE_SAMESITE == "none" and not COOKIE_SECURE:
    raise RuntimeError("COOKIE_SECURE must be true when COOKIE_SAMESITE=none.")
if ENVIRONMENT == "production" and not COOKIE_SECURE:
    raise RuntimeError("COOKIE_SECURE must be true in production.")
if ENVIRONMENT == "production" and not REDIS_URL:
    raise RuntimeError("Set REDIS_URL in production for shared rate limiting.")
if ENVIRONMENT == "production" and len(PLATFORM_MASTER_KEY) < 32:
    raise RuntimeError("Set a long PLATFORM_MASTER_KEY in production.")
if ENVIRONMENT == "production" and not ALLOWED_ORIGINS:
    raise RuntimeError("Set ALLOWED_ORIGINS to the exact browser frontend origin(s) in production.")

redis_client = Redis.from_url(REDIS_URL, decode_responses=True) if REDIS_URL else None
_rate_lock = threading.Lock()
_memory_buckets: dict[str, deque[float]] = defaultdict(deque)


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    if ENVIRONMENT == "production" and redis_client is not None:
        redis_client.ping()
    yield
    if redis_client is not None:
        redis_client.close()


app = FastAPI(
    title="TaskFlow API",
    version="2.0.0",
    lifespan=app_lifespan,
    docs_url=None,
    redoc_url=None if ENVIRONMENT == "production" else "/redoc",
)

if ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "X-CSRF-Token",
            "X-Platform-Admin-Key",
        ],
    )


if ENVIRONMENT != "production":
    @app.get("/docs", include_in_schema=False)
    async def custom_swagger_docs():
        page = get_swagger_ui_html(
            openapi_url=app.openapi_url,
            title=f"{app.title} - Swagger UI",
        )
        html = page.body.decode("utf-8")
        needle = "SwaggerUIBundle({"

        interceptor = r"""
requestInterceptor: function (request) {
    var method = (request.method || "GET").toUpperCase();
    var url = new URL(request.url, window.location.href);

    if (
        url.origin === window.location.origin &&
        !["GET", "HEAD", "OPTIONS"].includes(method)
    ) {
        var match = document.cookie.match(/(?:^|; )csrf_token=([^;]*)/);
        if (match) {
            request.headers = request.headers || {};
            request.headers["X-CSRF-Token"] = decodeURIComponent(match[1]);
        }
    }

    return request;
},
"""

        if needle not in html:
            raise RuntimeError("Could not add the CSRF helper to Swagger UI.")

        html = html.replace(needle, needle + interceptor, 1)
        return HTMLResponse(content=html, status_code=page.status_code)

def hash_password(password: str) -> str:
    # bcrypt has a 72-byte input limit; reject oversized passwords instead of truncating.
    raw = password.encode("utf-8")
    if len(raw) > 72:
        raise HTTPException(status_code=422, detail="Password must be at most 72 UTF-8 bytes.")
    return bcrypt.hashpw(raw, bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    raw = password.encode("utf-8")
    if len(raw) > 72:
        return False
    try:
        return bcrypt.checkpw(raw, hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


DUMMY_PASSWORD_HASH = bcrypt.hashpw(b"taskflow-dummy-password", bcrypt.gensalt(rounds=12)).decode("utf-8")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def datetime_is_expired(value: datetime) -> bool:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value <= utc_now()


def token_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _enforce_bucket(key: str, limit: int, window_seconds: int) -> None:
    try:
        if redis_client is not None:
            count = int(redis_client.eval(
                "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]) end; return n",
                1, key, window_seconds,
            ))
        else:
            # Development-only per-process limiter. Production requires Redis.
            now = time.monotonic()
            with _rate_lock:
                events = _memory_buckets[key]
                while events and events[0] <= now - window_seconds:
                    events.popleft()
                events.append(now)
                count = len(events)
                if len(_memory_buckets) > 10000:
                    for old_key in [k for k, values in _memory_buckets.items() if not values or values[-1] <= now - window_seconds]:
                        _memory_buckets.pop(old_key, None)
    except RedisError:
        if ENVIRONMENT == "production":
            raise HTTPException(status_code=503, detail="Rate limiting is temporarily unavailable.")
        now = time.monotonic()
        with _rate_lock:
            events = _memory_buckets[key]
            while events and events[0] <= now - window_seconds:
                events.popleft()
            events.append(now)
            count = len(events)
    if count > limit:
        raise HTTPException(status_code=429, detail="Too many requests. Try again later.", headers={"Retry-After": str(window_seconds)})


def enforce_rate_limit(request: Request, bucket: str, limit: int, window_seconds: int) -> None:
    client_ip = request.client.host if request.client else "unknown"
    _enforce_bucket(f"taskflow:rate:{bucket}:ip:{client_ip}", limit, window_seconds)


def enforce_login_limits(request: Request, identifier: str) -> None:
    enforce_rate_limit(request, "login-ip", 30, 300)
    identity = token_digest(identifier.strip().lower())[:32]
    _enforce_bucket(f"taskflow:rate:login-account:{identity}", 10, 900)


def audit_event(
    db: Session,
    *,
    company_id: int | None,
    actor_type: str,
    actor_id: int | None,
    action: str,
    target_type: str,
    target_id: int | str,
    details: dict | None = None,
) -> None:
    db.add(AuditEvent(
        company_id=company_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        details=details or {},
    ))


def create_access_token(*, subject: str, company_id: int, principal_type: str, role: str, session_id: str) -> str:
    now = utc_now()
    claims = {
        "sub": subject,
        "company_id": company_id,
        "principal_type": principal_type,
        "role": role,
        "sid": session_id,
        "jti": str(uuid4()),
        "iss": "taskflow-api",
        "aud": "taskflow-api",
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(claims, SECRET_KEY, algorithm=ALGORITHM)


def set_session_cookies(response: Response, access_token: str, refresh_token: str, csrf_token: str) -> None:
    common = {"secure": COOKIE_SECURE, "samesite": COOKIE_SAMESITE, "path": "/"}
    response.set_cookie(ACCESS_COOKIE, access_token, httponly=True, max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60, **common)
    response.set_cookie(REFRESH_COOKIE, refresh_token, httponly=True, max_age=REFRESH_TOKEN_EXPIRE_DAYS * 86400, **common)
    response.set_cookie(CSRF_COOKIE, csrf_token, httponly=False, max_age=REFRESH_TOKEN_EXPIRE_DAYS * 86400, **common)


def clear_session_cookies(response: Response) -> None:
    for name in (ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE):
        response.delete_cookie(name, path="/", secure=COOKIE_SECURE, httponly=(name != CSRF_COOKIE), samesite=COOKIE_SAMESITE)


def create_session(
    response: Response,
    db: Session,
    *,
    subject_id: int,
    company_id: int,
    principal_type: str,
    role: str,
) -> None:
    session_id = str(uuid4())
    refresh_secret = secrets.token_urlsafe(48)
    refresh_cookie = f"{session_id}.{refresh_secret}"
    csrf_token = secrets.token_urlsafe(32)
    now = utc_now()
    expires_at = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    db.add(AuthSession(
        id=session_id,
        company_id=company_id,
        principal_type=principal_type,
        principal_id=subject_id,
        csrf_token_hash=token_digest(csrf_token),
        created_at=now,
        expires_at=expires_at,
    ))
    db.add(AuthRefreshToken(
        session_id=session_id,
        token_hash=token_digest(refresh_cookie),
        expires_at=expires_at,
    ))
    db.commit()
    access_token = create_access_token(
        subject=str(subject_id), company_id=company_id,
        principal_type=principal_type, role=role, session_id=session_id,
    )
    set_session_cookies(response, access_token, refresh_cookie, csrf_token)


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token, SECRET_KEY, algorithms=[ALGORITHM],
            issuer="taskflow-api", audience="taskflow-api",
            options={"require_sub": True, "require_exp": True, "require_iat": True},
        )
        if not isinstance(payload.get("company_id"), int) or not payload.get("sid"):
            raise JWTError("Missing tenant or session scope")
        return payload
    except (JWTError, ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid or expired session.", headers={"WWW-Authenticate": "Bearer"})


def validate_csrf(request: Request, session: AuthSession) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    cookie_value = request.cookies.get(CSRF_COOKIE, "")
    header_value = request.headers.get("X-CSRF-Token", "")
    if (
        not cookie_value
        or not header_value
        or not hmac.compare_digest(cookie_value, header_value)
        or not hmac.compare_digest(token_digest(cookie_value), session.csrf_token_hash)
    ):
        raise HTTPException(status_code=403, detail="CSRF validation failed.")


def validate_origin(request: Request) -> None:
    origin = request.headers.get("Origin")
    if origin is None:
        return
    expected = {str(request.base_url).rstrip("/")}
    expected.update(ALLOWED_ORIGINS)
    if origin.rstrip("/") not in expected:
        raise HTTPException(status_code=403, detail="Request origin is not allowed.")

def decode_access_token_for_refresh(token: str) -> tuple[dict, datetime]:
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            issuer="taskflow-api",
            audience="taskflow-api",
            options={
                "require_sub": True,
                "require_exp": True,
                "require_iat": True,
                # Verify signature, issuer, and audience, but check expiry below.
                "verify_exp": False,
            },
        )

        if (
            not isinstance(payload.get("company_id"), int)
            or not payload.get("sid")
            or not isinstance(payload.get("exp"), (int, float))
        ):
            raise JWTError("Invalid token claims.")

        expires_at = datetime.fromtimestamp(
            payload["exp"],
            tz=timezone.utc,
        )
        return payload, expires_at

    except (JWTError, TypeError, ValueError, OSError):
        raise HTTPException(
            status_code=401,
            detail="Invalid session.",
            headers={"WWW-Authenticate": "Bearer"},
        )

def get_principal(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> tuple[dict, User | Company]:
    access_token = request.cookies.get(ACCESS_COOKIE)
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload, access_expires_at = decode_access_token_for_refresh(access_token)

    auth_session = db.get(AuthSession, payload["sid"])
    if (
        auth_session is None
        or auth_session.revoked_at is not None
        or datetime_is_expired(auth_session.expires_at)
        or auth_session.company_id != payload["company_id"]
    ):
        raise HTTPException(status_code=401, detail="Session expired or revoked.")

    # Keep CSRF and origin checks for state-changing requests.
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        validate_origin(request)
    validate_csrf(request, auth_session)

    company = db.get(Company, payload["company_id"])
    if company is None:
        raise HTTPException(status_code=401, detail="Session tenant no longer exists.")

    principal_type = payload.get("principal_type")

    if principal_type == "company_admin":
        if (
            auth_session.principal_type != "company_admin"
            or auth_session.principal_id != company.id
            or payload.get("role") != UserRole.admin.value
            or str(company.id) != payload["sub"]
        ):
            raise HTTPException(status_code=401, detail="Invalid session.")

        actor: User | Company = company
        subject_id = company.id
        role = UserRole.admin.value

    elif principal_type == "user":
        try:
            user_id = int(payload["sub"])
        except (KeyError, TypeError, ValueError):
            raise HTTPException(status_code=401, detail="Invalid user session.")

        if auth_session.principal_id != user_id:
            raise HTTPException(status_code=401, detail="Invalid session.")

        user = db.query(User).filter(
            User.id == user_id,
            User.company_id == company.id,
        ).first()

        if user is None or not user.is_active or user.role != payload.get("role"):
            raise HTTPException(status_code=401, detail="User session is no longer valid.")

        actor = user
        subject_id = user.id
        role = user.role

    else:
        raise HTTPException(status_code=401, detail="Invalid session.")

    # Renew when the access token has two minutes or less remaining,
    # or when it has expired. The refresh cookie must belong to this
    # same active server-side session.
    now = utc_now()
    if access_expires_at <= now + timedelta(minutes=2):
        refresh_cookie = request.cookies.get(REFRESH_COOKIE, "")
        try:
            refresh_session_id, _secret = refresh_cookie.split(".", 1)
        except ValueError:
            refresh_session_id = ""

        refresh_row = None
        if refresh_session_id == auth_session.id:
            refresh_row = db.query(AuthRefreshToken).filter(
                AuthRefreshToken.session_id == auth_session.id,
                AuthRefreshToken.token_hash == token_digest(refresh_cookie),
                AuthRefreshToken.consumed_at.is_(None),
            ).first()

        refresh_is_valid = (
            refresh_row is not None
            and not datetime_is_expired(refresh_row.expires_at)
        )

        if refresh_is_valid:
            new_access_token = create_access_token(
                subject=str(subject_id),
                company_id=company.id,
                principal_type=principal_type,
                role=role,
                session_id=auth_session.id,
            )
            response.set_cookie(
                key=ACCESS_COOKIE,
                value=new_access_token,
                httponly=True,
                secure=COOKIE_SECURE,
                samesite=COOKIE_SAMESITE,
                path="/",
                max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            )
        elif access_expires_at <= now:
            raise HTTPException(
                status_code=401,
                detail="Access token expired and refresh session is invalid.",
            )

    return payload, actor


def require_company_admin(principal=Depends(get_principal)) -> tuple[dict, Company]:
    payload, actor = principal
    if not isinstance(actor, Company) or payload.get("role") != UserRole.admin.value:
        raise HTTPException(status_code=403, detail="Company administrator access required.")
    return payload, actor


def require_company_member(principal=Depends(get_principal)) -> tuple[dict, User | Company]:
    return principal


def commit_or_conflict(db: Session, message: str = "A record with these unique values already exists.") -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=message)


@app.get("/health", response_model=MessageResponse)
def health() -> dict:
    return {"message": "TaskFlow API is running."}


@app.get("/health/ready", response_model=MessageResponse)
def readiness(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    return {"message": "TaskFlow API and database are ready."}


@app.post("/companies/", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
def register_company(data: CompanyCreate, request: Request, db: Session = Depends(get_db)) -> Company:
    validate_origin(request)
    enforce_rate_limit(request, "company-signup", 5, 3600)
    company = Company(name=data.name.strip(), subdomain=data.subdomain, admin_email=str(data.admin_email).lower(), admin_hashed_password=hash_password(data.admin_password))
    db.add(company)
    db.flush()
    audit_event(db, company_id=company.id, actor_type="registrant", actor_id=None,
                action="company.register", target_type="company", target_id=company.id)
    commit_or_conflict(db, "Company name, subdomain, or admin email is already registered.")
    db.refresh(company)
    return company


@app.post("/companies/login", response_model=MessageResponse)
def login_company_admin(data: CompanyLogin, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    validate_origin(request)
    enforce_login_limits(request, str(data.admin_email))
    company = db.query(Company).filter(Company.admin_email == str(data.admin_email).lower()).first()
    valid = verify_password(data.admin_password, company.admin_hashed_password if company else DUMMY_PASSWORD_HASH)
    if company is None or not valid:
        raise HTTPException(status_code=401, detail="Incorrect admin email or password.")
    create_session(response, db, subject_id=company.id, company_id=company.id, principal_type="company_admin", role=UserRole.admin.value)
    audit_event(db, company_id=company.id, actor_type="company_admin", actor_id=company.id, action="login", target_type="company", target_id=company.id)
    db.commit()
    return {"message": "Logged in successfully."}


@app.post("/users/login", response_model=MessageResponse)
def login_user(data: UserLogin, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    validate_origin(request)
    enforce_login_limits(request, str(data.email))
    user = db.query(User).filter(User.email == str(data.email).lower()).first()
    valid = verify_password(data.password, user.hashed_password if user else DUMMY_PASSWORD_HASH)
    if user is None or not valid:
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is deactivated.")
    create_session(response, db, subject_id=user.id, company_id=user.company_id, principal_type="user", role=user.role)
    audit_event(db, company_id=user.company_id, actor_type="user", actor_id=user.id, action="login", target_type="user", target_id=user.id)
    db.commit()
    return {"message": "User logged in successfully."}


@app.post("/auth/refresh", response_model=MessageResponse)
def refresh_session(request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    validate_origin(request)
    enforce_rate_limit(request, "refresh", 60, 300)
    supplied = request.cookies.get(REFRESH_COOKIE, "")
    try:
        session_id, _secret = supplied.split(".", 1)
    except ValueError:
        raise HTTPException(status_code=401, detail="Refresh session is missing or invalid.")

    auth_session = db.query(AuthSession).filter(AuthSession.id == session_id).with_for_update().first()
    csrf_cookie = request.cookies.get(CSRF_COOKIE, "")
    csrf_header = request.headers.get("X-CSRF-Token", "")
    if (
        auth_session is None or not csrf_cookie or not csrf_header
        or not hmac.compare_digest(csrf_cookie, csrf_header)
        or not hmac.compare_digest(token_digest(csrf_cookie), auth_session.csrf_token_hash)
    ):
        raise HTTPException(status_code=403, detail="CSRF validation failed or session is invalid.")

    token_hash = token_digest(supplied)
    refresh_row = db.query(AuthRefreshToken).filter(
        AuthRefreshToken.session_id == session_id,
        AuthRefreshToken.token_hash == token_hash,
    ).with_for_update().first()
    now = utc_now()
    if refresh_row is None:
        raise HTTPException(status_code=401, detail="Refresh session is invalid.")
    if refresh_row.consumed_at is not None:
        auth_session.revoked_at = now
        db.query(AuthRefreshToken).filter(
            AuthRefreshToken.session_id == session_id,
            AuthRefreshToken.consumed_at.is_(None),
        ).update({AuthRefreshToken.consumed_at: now})
        db.commit()
        clear_session_cookies(response)
        raise HTTPException(status_code=401, detail="Refresh token reuse detected; sign in again.")
    if auth_session.revoked_at is not None or datetime_is_expired(auth_session.expires_at) or datetime_is_expired(refresh_row.expires_at):
        raise HTTPException(status_code=401, detail="Refresh session expired or revoked.")

    company = db.get(Company, auth_session.company_id)
    if company is None:
        raise HTTPException(status_code=401, detail="Company no longer exists.")
    if auth_session.principal_type == "user":
        user = db.query(User).filter(User.id == auth_session.principal_id, User.company_id == company.id).first()
        if user is None or not user.is_active:
            auth_session.revoked_at = now
            db.commit()
            clear_session_cookies(response)
            raise HTTPException(status_code=401, detail="User session is no longer valid.")
        subject_id, role = user.id, user.role
    elif auth_session.principal_type == "company_admin" and auth_session.principal_id == company.id:
        subject_id, role = company.id, UserRole.admin.value
    else:
        raise HTTPException(status_code=401, detail="Invalid refresh session.")

    refresh_row.consumed_at = now
    next_cookie = f"{session_id}.{secrets.token_urlsafe(48)}"
    db.add(AuthRefreshToken(
        session_id=session_id,
        token_hash=token_digest(next_cookie),
        expires_at=auth_session.expires_at,
    ))
    access_token = create_access_token(
        subject=str(subject_id), company_id=company.id,
        principal_type=auth_session.principal_type, role=role,
        session_id=session_id,
    )
    db.commit()
    set_session_cookies(response, access_token, next_cookie, csrf_cookie)
    return {"message": "Session refreshed."}


@app.post("/companies/logout", response_model=MessageResponse)
@app.post("/users/logout", response_model=MessageResponse)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    validate_origin(request)
    supplied = request.cookies.get(REFRESH_COOKIE, "")
    try:
        session_id, _secret = supplied.split(".", 1)
    except ValueError:
        session_id = ""
    auth_session = db.query(AuthSession).filter(AuthSession.id == session_id).first() if session_id else None
    if auth_session is not None:
        csrf_cookie = request.cookies.get(CSRF_COOKIE, "")
        csrf_header = request.headers.get("X-CSRF-Token", "")
        if (
            not csrf_cookie or not csrf_header
            or not hmac.compare_digest(csrf_cookie, csrf_header)
            or not hmac.compare_digest(token_digest(csrf_cookie), auth_session.csrf_token_hash)
        ):
            raise HTTPException(status_code=403, detail="CSRF validation failed.")
        now = utc_now()
        auth_session.revoked_at = now
        db.query(AuthRefreshToken).filter(
            AuthRefreshToken.session_id == session_id,
            AuthRefreshToken.consumed_at.is_(None),
        ).update({AuthRefreshToken.consumed_at: now})
        db.commit()
    clear_session_cookies(response)
    return {"message": "Logged out successfully."}


@app.get("/companies/me", response_model=CompanyResponse)
def get_company(principal=Depends(require_company_member)) -> Company:
    _, actor = principal
    return actor.company if isinstance(actor, User) else actor

def validate_project_group(
    db: Session,
    company_id: int,
    group_id: int | None,
) -> None:
    if group_id is None:
        return

    group = db.query(Group).filter(
        Group.id == group_id,
        Group.company_id == company_id,
    ).first()

    if group is None:
        raise HTTPException(
            status_code=400,
            detail="Group not found in your company.",
        )

def user_group_ids(db: Session, company_id: int, user_id: int):
    return db.query(GroupMembership.group_id).filter(
        GroupMembership.company_id == company_id,
        GroupMembership.user_id == user_id,
    ).subquery()


def visible_project_query(db: Session, company_id: int, actor):
    query = db.query(Project).filter(Project.company_id == company_id)

    if isinstance(actor, User):
        group_ids = user_group_ids(db, company_id, actor.id)

        assigned_project_ids = db.query(Task.project_id).filter(
            Task.company_id == company_id,
            Task.assigned_to_id == actor.id,
            Task.project_id.is_not(None),
        ).subquery()

        query = query.filter(
            or_(
                Project.group_id.in_(group_ids),
                Project.id.in_(assigned_project_ids),
            )
        )

    return query


def visible_task_query(db: Session, company_id: int, actor):
    query = db.query(Task).outerjoin(
        Project,
        (Task.project_id == Project.id)
        & (Task.company_id == Project.company_id),
    ).filter(Task.company_id == company_id)

    if isinstance(actor, User):
        group_ids = user_group_ids(db, company_id, actor.id)
        query = query.filter(
            or_(
                Project.group_id.in_(group_ids),
                Task.assigned_to_id == actor.id,
            )
        )
        return query  
@app.post("/projects/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    data: ProjectCreate,
    principal=Depends(require_company_admin),
    db: Session = Depends(get_db),
) -> Project:
    _, company = principal
    validate_project_group(db, company.id, data.group_id)

    project = Project(
        name=data.name.strip(),
        description=data.description,
        company_id=company.id,
        group_id=data.group_id,
    )
    db.add(project)
    db.flush()

    audit_event(
        db,
        company_id=company.id,
        actor_type="company_admin",
        actor_id=company.id,
        action="project.create",
        target_type="project",
        target_id=project.id,
    )
    commit_or_conflict(db, "A project with this name already exists in your company.")
    db.refresh(project)
    return project


@app.get("/projects/", response_model=list[ProjectResponse])
def list_projects(
    principal=Depends(require_company_member),
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[Project]:
    payload, actor = principal
    return (
    visible_project_query(db, payload["company_id"], actor)
    .order_by(Project.id)
    .offset(offset)
    .limit(limit)
    .all()
)


@app.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: int,
    principal=Depends(require_company_member),
    db: Session = Depends(get_db),
) -> Project:
    payload, actor = principal
    project = visible_project_query(
        db,
        payload["company_id"],
        actor,
    ).filter(Project.id == project_id).first()

    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")

    return project

 
@app.put("/projects/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: int, 
    data: ProjectUpdate,
    principal=Depends(require_company_admin),
    db: Session = Depends(get_db),
) -> Project:
    payload, company = principal

    project = db.query(Project).filter(
        Project.id == project_id,
        Project.company_id == payload["company_id"],
    ).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")

    validate_project_group(db, company.id, data.group_id)

    project.name = data.name.strip()
    project.description = data.description
    project.group_id = data.group_id

    audit_event(
        db,
        company_id=company.id,
        actor_type="company_admin",
        actor_id=company.id,
        action="project.update",
        target_type="project",
        target_id=project.id,
    )
    commit_or_conflict(db, "A project with this name already exists in your company.")
    db.refresh(project)
    return project


@app.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: int, principal=Depends(require_company_admin), db: Session = Depends(get_db)) -> Response:
    payload, company = principal
    project = db.query(Project).filter(Project.id == project_id, Project.company_id == payload["company_id"]).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    audit_event(db, company_id=company.id, actor_type="company_admin", actor_id=company.id,
                action="project.delete", target_type="project", target_id=project.id)
    db.delete(project)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.put("/companies/{company_id}", response_model=CompanyResponse)
def update_company(company_id: int, data: CompanyUpdate, principal=Depends(require_company_admin), db: Session = Depends(get_db)) -> Company:
    _, company = principal
    if company.id != company_id:
        raise HTTPException(status_code=403, detail="Access denied.")
    company.name, company.subdomain = data.name.strip(), data.subdomain
    audit_event(db, company_id=company.id, actor_type="company_admin", actor_id=company.id,
                action="company.update", target_type="company", target_id=company.id)
    commit_or_conflict(db, "Company name or subdomain is already in use.")
    db.refresh(company)
    return company


@app.patch("/companies/{company_id}", response_model=CompanyResponse)
def patch_company(company_id: int, data: CompanyPatch, principal=Depends(require_company_admin), db: Session = Depends(get_db)) -> Company:
    _, company = principal
    if company.id != company_id:
        raise HTTPException(status_code=403, detail="Access denied.")
    for key, value in data.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(company, key, value.strip() if key == "name" else value)
    audit_event(db, company_id=company.id, actor_type="company_admin", actor_id=company.id,
                action="company.update", target_type="company", target_id=company.id)
    commit_or_conflict(db, "Company name or subdomain is already in use.")
    db.refresh(company)
    return company


@app.post("/users/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(data: UserCreate, principal=Depends(require_company_admin), db: Session = Depends(get_db)) -> User:
    _, company = principal
    if db.query(User).filter(User.company_id == company.id).count() >= 5000:
        raise HTTPException(status_code=409, detail="Company user limit reached.")
    user = User(email=str(data.email).lower(), hashed_password=hash_password(data.password), role=data.role.value, company_id=company.id)
    db.add(user)
    db.flush()
    audit_event(db, company_id=company.id, actor_type="company_admin", actor_id=company.id,
                action="user.create", target_type="user", target_id=user.id)
    commit_or_conflict(db, "This email is already registered.")
    db.refresh(user)
    return user


@app.get("/users/", response_model=list[UserResponse])
def list_company_users(
    principal=Depends(require_company_member),
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[User]:
    payload, _ = principal
    if payload.get("principal_type") != "company_admin":
        raise HTTPException(status_code=403, detail="Company administrator access required.")
    return db.query(User).filter(User.company_id == payload["company_id"]).order_by(User.id).offset(offset).limit(limit).all()


@app.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_company_user(
    user_id: int,
    principal=Depends(require_company_admin),
    db: Session = Depends(get_db),
) -> Response:
    payload, _ = principal
    user = (
        db.query(User)
        .filter(
            User.id == user_id,
            User.company_id == payload["company_id"],
        )
        .first()
    )
    if user is None:
        raise HTTPException(status_code=404, detail="User not found in your company.")

    now = utc_now()
    sessions = db.query(AuthSession).filter(
        AuthSession.principal_type == "user",
        AuthSession.principal_id == user.id,
        AuthSession.company_id == payload["company_id"],
        AuthSession.revoked_at.is_(None),
    ).all()
    for auth_session in sessions:
        auth_session.revoked_at = now
    audit_event(db, company_id=payload["company_id"], actor_type="company_admin", actor_id=payload["company_id"],
                action="user.delete", target_type="user", target_id=user.id)
    db.delete(user)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@app.post(
    "/tasks/",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_task(
    data: TaskCreate,
    request: Request,
    principal=Depends(require_company_admin),
    db: Session = Depends(get_db),
) -> Task:
    payload, company = principal
    enforce_rate_limit(request, "task-create", 120, 3600)

    if data.project_id is not None:
        project = db.query(Project).filter(
            Project.id == data.project_id,
            Project.company_id == payload["company_id"],
        ).first()
        if project is None:
            raise HTTPException(
                status_code=400,
                detail="Project not found in your company.",
            )

    if data.assigned_to_id is not None:
        assignee = db.query(User).filter(
            User.id == data.assigned_to_id,
            User.company_id == payload["company_id"],
            User.is_active.is_(True),
        ).first()
        if assignee is None:
            raise HTTPException(
                status_code=400,
                detail="Assigned user is not active in this company.",
            )

    task = Task(
        title=data.title.strip(),
        description=data.description,
        status=data.status.value,
        priority=data.priority.value,
        due_at=data.due_at,
        company_id=payload["company_id"],
        project_id=data.project_id,
        assigned_to_id=data.assigned_to_id,
    )
    db.add(task)
    db.flush()

    audit_event(
        db,
        company_id=company.id,
        actor_type="company_admin",
        actor_id=company.id,
        action="task.create",
        target_type="task",
        target_id=task.id,
    )

    db.commit()
    db.refresh(task)
    return task


@app.put("/tasks/{task_id}", response_model=TaskResponse)
def edit_task(task_id: int, data: TaskUpdate, principal=Depends(require_company_admin), db: Session = Depends(get_db)) -> Task:
    payload, company = principal
    task = db.query(Task).filter(Task.id == task_id, Task.company_id == payload["company_id"]).first()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    before = {"title": task.title, "description": task.description, "status": task.status,
              "priority": task.priority, "due_at": task.due_at.isoformat() if task.due_at else None,
              "project_id": task.project_id, "assigned_to_id": task.assigned_to_id}
    if data.project_id is not None and db.query(Project).filter(
        Project.id == data.project_id,
        Project.company_id == payload["company_id"],
    ).first() is None:
        raise HTTPException(status_code=400, detail="Project not found in your company.")
    if data.assigned_to_id is not None:
        assignee = db.query(User).filter(
            User.id == data.assigned_to_id,
            User.company_id == payload["company_id"],
            User.is_active.is_(True),
        ).first()
        if assignee is None:
            raise HTTPException(status_code=400, detail="Assigned user is not active in this company.")
    task.title = data.title.strip()
    task.description = data.description
    task.status = data.status.value
    task.priority = data.priority.value
    task.due_at = data.due_at
    task.project_id = data.project_id
    task.assigned_to_id = data.assigned_to_id
    audit_event(db, company_id=company.id, actor_type="company_admin", actor_id=company.id,
                action="task.update", target_type="task", target_id=task.id,
                details={"before": before, "after": {
                    "title": task.title, "description": task.description, "status": task.status,
                    "priority": task.priority, "due_at": task.due_at.isoformat() if task.due_at else None,
                    "project_id": task.project_id, "assigned_to_id": task.assigned_to_id,
                }})
    db.commit()
    db.refresh(task)
    return task


@app.get("/tasks/", response_model=list[TaskResponse])
def list_company_tasks(
    principal=Depends(require_company_member),
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    project_id: int | None = Query(default=None, gt=0),
    status_filter: TaskStatus | None = Query(default=None, alias="status"),
    priority_filter: TaskPriority | None = Query(default=None, alias="priority"),
) -> list[Task]:
    payload, actor = principal
    query = visible_task_query(db, payload["company_id"], actor)

    if project_id is not None:
        query = query.filter(Task.project_id == project_id)
    if status_filter is not None:
        query = query.filter(Task.status == status_filter.value)
    if priority_filter is not None:
        query = query.filter(Task.priority == priority_filter.value)

    return query.order_by(Task.id).offset(offset).limit(limit).all()

@app.patch("/tasks/{task_id}/status", response_model=TaskResponse)
def update_task_status(task_id: int, data: TaskStatusUpdate, principal=Depends(require_company_member), db: Session = Depends(get_db)) -> Task:
    payload, actor = principal
    task = db.query(Task).filter(Task.id == task_id, Task.company_id == payload["company_id"]).first()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    # A company admin may update any task in their own tenant. A member may
    # report progress only on a task assigned to their own user account.
    if isinstance(actor, User) and task.assigned_to_id != actor.id:
        raise HTTPException(status_code=403, detail="Members can change status only on tasks assigned to them.")
    old_status = task.status
    task.status = data.status.value
    if isinstance(actor, Company):
        audit_event(db, company_id=payload["company_id"], actor_type="company_admin", actor_id=actor.id,
                    action="task.status.update", target_type="task", target_id=task.id,
                    details={"old_status": old_status, "new_status": task.status})
    else:
        audit_event(db, company_id=payload["company_id"], actor_type="user", actor_id=actor.id,
                    action="task.status.update", target_type="task", target_id=task.id,
                    details={"old_status": old_status, "new_status": task.status})
    db.commit()
    db.refresh(task)
    return task


@app.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, principal=Depends(require_company_admin), db: Session = Depends(get_db)) -> Response:
    payload, company = principal
    task = db.query(Task).filter(Task.id == task_id, Task.company_id == payload["company_id"]).first()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    audit_event(db, company_id=company.id, actor_type="company_admin", actor_id=company.id,
                action="task.delete", target_type="task", target_id=task.id)
    db.delete(task)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get(
    "/tasks/{task_id}/comments/",
    response_model=list[CommentWithAuthorResponse],
)
def list_task_comments(
    task_id: int,
    principal=Depends(require_company_member),
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[dict]:
    payload, actor = principal

    task = visible_task_query(
        db,
        payload["company_id"],
        actor,
    ).filter(Task.id == task_id).first()

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")

    rows = (
        db.query(Comment, User.email)
        .join(User, User.id == Comment.user_id)
        .filter(Comment.task_id == task.id)
        .order_by(Comment.id)
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [
        {
            "id": comment.id,
            "content": comment.content,
            "task_id": comment.task_id,
            "user_id": comment.user_id,
            "author_email": email,
        }
        for comment, email in rows
    ]


@app.post(
    "/tasks/{task_id}/comments/",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_comment(
    task_id: int,
    data: CommentCreate,
    request: Request,
    principal=Depends(require_company_member),
    db: Session = Depends(get_db),
) -> Comment:
    payload, actor = principal
    enforce_rate_limit(request, "comment-create", 60, 3600)

    if not isinstance(actor, User):
        raise HTTPException(
            status_code=403,
            detail="A user account is required to comment.",
        )

    task = visible_task_query(
        db,
        payload["company_id"],
        actor,
    ).filter(Task.id == task_id).first()

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")

    if task.assigned_to_id != actor.id:
        raise HTTPException(
            status_code=403,
            detail="Members can comment only on tasks assigned to them.",
        )

    comment = Comment(
        content=data.content.strip(),
        task_id=task.id,
        user_id=actor.id,
    )
    db.add(comment)
    db.flush()

    audit_event(
        db,
        company_id=payload["company_id"],
        actor_type="user",
        actor_id=actor.id,
        action="comment.create",
        target_type="comment",
        target_id=comment.id,
        details={"task_id": task.id},
    )

    db.commit()
    db.refresh(comment)
    return comment


@app.get("/admin/audit", response_model=list[AuditEventResponse])
def company_audit_log(
    principal=Depends(require_company_admin),
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[AuditEvent]:
    payload, _ = principal
    return (
        db.query(AuditEvent)
        .filter(AuditEvent.company_id == payload["company_id"])
        .order_by(AuditEvent.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@app.get("/admin/companies", response_model=list[CompanyResponse])
def super_admin_list_all_companies(
    request: Request,
    admin_key: str = Header(alias="X-Platform-Admin-Key"),
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[Company]:
    enforce_rate_limit(request, "platform-admin", 60, 60)
    if not PLATFORM_MASTER_KEY or not hmac.compare_digest(admin_key, PLATFORM_MASTER_KEY):
        raise HTTPException(status_code=403, detail="Access denied.")
    return db.query(Company).order_by(Company.id).offset(offset).limit(limit).all()


@app.get("/platform/audit", response_model=list[AuditEventResponse])
def platform_audit_log(
    request: Request,
    admin_key: str = Header(alias="X-Platform-Admin-Key"),
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[AuditEvent]:
    enforce_rate_limit(request, "platform-admin", 60, 60)
    if not PLATFORM_MASTER_KEY or not hmac.compare_digest(admin_key, PLATFORM_MASTER_KEY):
        raise HTTPException(status_code=403, detail="Access denied.")
    return db.query(AuditEvent).order_by(AuditEvent.id.desc()).offset(offset).limit(limit).all()


@app.delete("/admin/companies/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
def super_admin_delete_company(
    company_id: int,
    request: Request,
    admin_key: str = Header(alias="X-Platform-Admin-Key"),
    db: Session = Depends(get_db),
) -> Response:
    enforce_rate_limit(request, "platform-admin", 60, 60)
    if not PLATFORM_MASTER_KEY or not hmac.compare_digest(admin_key, PLATFORM_MASTER_KEY):
        raise HTTPException(status_code=403, detail="Access denied.")
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found.")
    audit_event(db, company_id=company.id, actor_type="platform_admin", actor_id=None,
                action="company.delete", target_type="company", target_id=company.id)
    db.delete(company)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@app.post("/groups/", response_model=GroupResponse, status_code=201)
def create_group(
    data: GroupCreate,
    principal=Depends(require_company_admin),
    db: Session = Depends(get_db),
):
    payload, company = principal

    group = Group(
        company_id=payload["company_id"],
        name=data.name.strip(),
        description=data.description,
    )
    db.add(group)
    db.flush()

    audit_event(
        db,
        company_id=company.id,
        actor_type="company_admin",
        actor_id=company.id,
        action="group.create",
        target_type="group",
        target_id=group.id,
    )

    commit_or_conflict(db, "A group with this name already exists in your company.")
    db.refresh(group)
    return group


@app.get("/groups/", response_model=list[GroupResponse])
def list_groups(
    principal=Depends(require_company_member),
    db: Session = Depends(get_db),
):
    payload, actor = principal

    query = db.query(Group).filter(
        Group.company_id == payload["company_id"]
    )

    if isinstance(actor, User):
        query = query.join(GroupMembership).filter(
            GroupMembership.company_id == payload["company_id"],
            GroupMembership.user_id == actor.id,
        )

    return query.order_by(Group.name).all()


@app.post("/groups/{group_id}/members/{user_id}", status_code=204)
def add_group_member(
    group_id: int,
    user_id: int,
    principal=Depends(require_company_admin),
    db: Session = Depends(get_db),
):
    payload, company = principal
    company_id = payload["company_id"]

    group = db.query(Group).filter(
        Group.id == group_id,
        Group.company_id == company_id,
    ).first()
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found.")

    user = db.query(User).filter(
        User.id == user_id,
        User.company_id == company_id,
        User.is_active.is_(True),
    ).first()
    if user is None:
        raise HTTPException(
            status_code=404,
            detail="Active user not found in your company.",
        )

    membership = db.query(GroupMembership).filter(
        GroupMembership.company_id == company_id,
        GroupMembership.group_id == group_id,
        GroupMembership.user_id == user_id,
    ).first()

    if membership is None:
        db.add(GroupMembership(
            company_id=company_id,
            group_id=group_id,
            user_id=user_id,
        ))
        audit_event(
            db,
            company_id=company_id,
            actor_type="company_admin",
            actor_id=company.id,
            action="group.member.add",
            target_type="group_membership",
            target_id=f"{group_id}:{user_id}",
        )
        commit_or_conflict(db, "That user is already in the group.")

    return Response(status_code=204)