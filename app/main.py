"""TaskFlow secure multi-tenant API."""
from app.schemas import NotificationResponse
from sqlalchemy import or_, select, text
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.models import User, Company, Notification  # Make sure Notification is listed here!
from app.schemas import MessageResponse, GoogleAuthRequest
from fastapi import WebSocket, WebSocketDisconnect
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
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
from types import SimpleNamespace
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
from sqlalchemy.orm import Session, joinedload
load_dotenv()
from dotenv import load_dotenv
import ssl
import traceback
from app.ai_assistant import generate_task_ai_response
from app.database import get_db
from app.models import (
    AuditEvent, AuthRefreshToken, AuthSession, Comment, Company, Group,
    GroupMembership, Notification, Project, Task, TaskPriority, TaskStatus,
    User, UserRole,
)
from app.schemas import (
    AuditEventResponse, CommentCreate, CommentResponse, CommentWithAuthorResponse,
    CompanyCreate, CompanyLogin, CompanyPatch, CompanyResponse, CompanyUpdate,
    GoogleAuthRequest, GroupCreate, GroupResponse, MessageResponse,
    NotificationResponse, ProjectAIRequest, ProjectAIResponse, ProjectCreate,
    ProjectResponse, ProjectUpdate, TaskAIRequest, TaskAIResponse, TaskCreate,
    TaskResponse, TaskStatusUpdate, TaskUpdate, UserCreate, UserLogin,
    UserResponse, UserSummary,
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


SMTP_SERVER = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SENDER_EMAIL = os.getenv("SMTP_USER", "muhammadtalha5037@gmail.com").strip()
SENDER_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()


def send_admin_email_alert(admin_email: str, subject: str, body: str):
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        print("Failed to send email alert: SMTP_USER or SMTP_PASSWORD is missing.")
        return

    try:
        msg = MIMEMultipart()
        msg["From"] = SENDER_EMAIL
        msg["To"] = admin_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        context = ssl.create_default_context()
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context, timeout=20) as server:
                server.login(SENDER_EMAIL, SENDER_PASSWORD)
                server.sendmail(SENDER_EMAIL, admin_email, msg.as_string())
        else:
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=20) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(SENDER_EMAIL, SENDER_PASSWORD)
                server.sendmail(SENDER_EMAIL, admin_email, msg.as_string())
    except Exception as e:
        print(f"Failed to send email alert ({type(e).__name__}): {e!r}")
        traceback.print_exc()

class ConnectionManager:
    def __init__(self):
        # Maps company_id -> list of active admin WebSockets
        self.active_connections: dict[int, list[WebSocket]] = defaultdict(list)

    async def connect(self, company_id: int, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[company_id].append(websocket)

    def disconnect(self, company_id: int, websocket: WebSocket):
        conns = self.active_connections.get(company_id)
        if conns and websocket in conns:
            conns.remove(websocket)
            if not conns:
                del self.active_connections[company_id]

    async def broadcast_to_company(self, company_id: int, message: dict):
        if company_id in self.active_connections:
            for connection in self.active_connections[company_id]:
                await connection.send_json(message)

manager = ConnectionManager()

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
        allow_origins=ALLOWED_ORIGINS,  # <--- Use the parsed list from .env, not a hardcoded string
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
            # First check for unconsumed tokens
            refresh_row = db.query(AuthRefreshToken).filter(
                AuthRefreshToken.session_id == auth_session.id,
                AuthRefreshToken.token_hash == token_digest(refresh_cookie),
                AuthRefreshToken.consumed_at.is_(None),
            ).first()

            # Gracefully handle concurrent requests by allowing tokens consumed within the last 10 seconds
            if refresh_row is None:
                recent_cutoff = utc_now() - timedelta(seconds=10)
                refresh_row = db.query(AuthRefreshToken).filter(
                    AuthRefreshToken.session_id == auth_session.id,
                    AuthRefreshToken.token_hash == token_digest(refresh_cookie),
                    AuthRefreshToken.consumed_at >= recent_cutoff,
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
    
    # 🔒 ENFORCE GMAIL/GOOGLE ONLY
    admin_email = str(data.admin_email).strip().lower()
    if not admin_email.endswith("@gmail.com"):
        raise HTTPException(
            status_code=400, 
            detail="Registration is restricted to verified Google (@gmail.com) accounts only."
        )

    company = Company(
        name=data.name.strip(), 
        subdomain=data.subdomain, 
        admin_email=admin_email, 
        admin_hashed_password=hash_password(data.admin_password)
    )
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
async def login_user(data: UserLogin, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
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
    
    # 🔔 Notify Company Admin on User Login (Email + In-App)
    # Notify Company Admin on User Login (Email + In-App)
    company = db.query(Company).filter(Company.id == user.company_id).first()
    if company and company.admin_email:
        send_admin_email_alert(
            admin_email=company.admin_email,
            subject=f"User Login Alert: {user.email}",
            body=f"User {user.email} has successfully logged into TaskFlow OS."
        )

        admin_notif = Notification(
            recipient_id=company.id,
            recipient_type="admin",
            company_id=company.id,
            title="User Login",
            message=f"User {user.email} logged into the system."
        )
        db.add(admin_notif)

    # Also log an in-app notification for the user who logged in
    user_notif = Notification(
        recipient_id=user.id,
        recipient_type="user",
        company_id=user.company_id,
        title="Login Confirmed",
        message="You signed in to TaskFlow OS."
    )
    db.add(user_notif)

    db.commit()

    if company:
        await manager.broadcast_to_company(
            company.id,
            {"type": "NOTIFICATION", "message": f"User {user.email} is now online."}
        )

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

    # Company admins bypass filters and see all projects
    if isinstance(actor, User):
        group_ids = user_group_ids(db, company_id, actor.id)

        assigned_project_ids = db.query(Task.project_id).filter(
            Task.company_id == company_id,
            Task.assigned_to_id == actor.id,
            Task.project_id.is_not(None),
        ).subquery()

        query = query.filter(
            or_(
                Project.group_id.in_(select(group_ids.c.group_id)),
                Project.id.in_(select(assigned_project_ids.c.project_id)),
            )
        )

    return query


def visible_task_query(db: Session, company_id: int, actor):
    query = db.query(Task).options(
        joinedload(Task.assignee),
        joinedload(Task.project)
    ).filter(Task.company_id == company_id)

    # Only regular users are restricted to their own assigned tasks
    if isinstance(actor, User):
        query = query.filter(Task.assigned_to_id == actor.id)

    return query
@app.post("/projects/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    data: ProjectCreate,
    principal=Depends(require_company_admin),
    db: Session = Depends(get_db),
) -> Project:
    payload, company = principal
    validate_project_group(db, company.id, data.group_id)

    project = Project(
        name=data.name.strip(),
        description=data.description,
        company_id=company.id,
        group_id=data.group_id,
    )
    db.add(project)
    db.flush()

    # 🔔 Notify all users belonging to the assigned group
  # Notify all users belonging to the assigned group
    if project.group_id:
        group_members = db.query(GroupMembership).filter(
            GroupMembership.company_id == company.id,
            GroupMembership.group_id == project.group_id
        ).all()
        for member in group_members:
            project_notification = Notification(
                recipient_id=member.user_id,
                recipient_type="user",
                company_id=company.id,
                title="Project Update",
                message=f"You have been added to project: {project.name}."
            )
            db.add(project_notification)

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

    # Send Admin Email Alert on Project Creation
    if company.admin_email:
        send_admin_email_alert(
            admin_email=company.admin_email,
            subject=f"TaskFlow OS: New Project Created - {project.name}",
            body=f"A new project '{project.name}' was successfully created in your workspace."
        )

    # Broadcast live notification to company clients
    await manager.broadcast_to_company(
        company.id,
        {"type": "NOTIFICATION", "message": f"New project created: {project.name}"}
    )
    

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

@app.put("/tasks/{task_id}", response_model=TaskResponse)
def edit_task(task_id: int, data: TaskUpdate, principal=Depends(require_company_admin), db: Session = Depends(get_db)) -> Task:
    payload, company = principal
    updates = data.model_dump(exclude_unset=True)
    task = db.query(Task).filter(Task.id == task_id, Task.company_id == payload["company_id"]).first()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    before = {
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
        "due_at": task.due_at.isoformat() if task.due_at else None,
        "project_id": task.project_id,
        "assigned_to_id": task.assigned_to_id,
    }
    if "project_id" in updates and updates["project_id"] is not None:
        project = db.query(Project).filter(
            Project.id == updates["project_id"],
            Project.company_id == payload["company_id"],
        ).first()
        if project is None:
            raise HTTPException(status_code=400, detail="Project not found in your company.")
    if "assigned_to_id" in updates and updates["assigned_to_id"] is not None:
        assignee = db.query(User).filter(
            User.id == updates["assigned_to_id"],
            User.company_id == payload["company_id"],
            User.is_active.is_(True),
        ).first()
        if assignee is None:
            raise HTTPException(status_code=400, detail="Assigned user is not active in this company.")

    if "title" in updates:
        if updates["title"] is None:
            raise HTTPException(status_code=422, detail="title cannot be null.")
        cleaned_title = updates["title"].strip()
        if not cleaned_title:
            raise HTTPException(status_code=422, detail="title cannot be blank.")
        task.title = cleaned_title
    if "description" in updates:
        task.description = updates["description"].strip() if updates["description"] else None
    if "status" in updates:
        if updates["status"] is None:
            raise HTTPException(status_code=422, detail="status cannot be null.")
        task.status = data.status.value if isinstance(data.status, TaskStatus) else str(updates["status"])
    if "priority" in updates:
        if updates["priority"] is None:
            raise HTTPException(status_code=422, detail="priority cannot be null.")
        task.priority = data.priority.value if isinstance(data.priority, TaskPriority) else str(updates["priority"])
    if "due_at" in updates:
        task.due_at = updates["due_at"]
    if "project_id" in updates:
        task.project_id = updates["project_id"]
    if "assigned_to_id" in updates:
        task.assigned_to_id = updates["assigned_to_id"]

    audit_event(
        db,
        company_id=company.id,
        actor_type="company_admin",
        actor_id=company.id,
        action="task.update",
        target_type="task",
        target_id=task.id,
        details={
            "before": before,
            "after": {
                "title": task.title,
                "description": task.description,
                "status": task.status,
                "priority": task.priority,
                "due_at": task.due_at.isoformat() if task.due_at else None,
                "project_id": task.project_id,
                "assigned_to_id": task.assigned_to_id,
            },
        },
    )
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
) -> list[TaskResponse]:
    payload, actor = principal
    
    query = visible_task_query(db, payload["company_id"], actor)

    if project_id is not None:
        query = query.filter(Task.project_id == project_id)
    if status_filter is not None:
        query = query.filter(Task.status == status_filter.value)
    if priority_filter is not None:
        query = query.filter(Task.priority == priority_filter.value)

    tasks = query.order_by(Task.id).offset(offset).limit(limit).all()

    result = []
    for task in tasks:
        task_data = TaskResponse.model_validate(task)
        # Map assignee details so the frontend inspector modal displays them properly
        if task.assignee:
            task_data.assignee_name = task.assignee.email
            task_data.assigned_to_id = task.assignee.id
        else:
            task_data.assignee_name = "Unassigned"
            task_data.assigned_to_id = None
        result.append(task_data)

    return result

@app.get("/notifications/", response_model=list[NotificationResponse])
def list_notifications(
    principal=Depends(require_company_member),
    db: Session = Depends(get_db),
):
    payload, actor = principal
    query = db.query(Notification).filter(
        Notification.company_id == payload["company_id"]
    )
    if isinstance(actor, User):
        query = query.filter(
            Notification.recipient_type == "user",
            Notification.recipient_id == actor.id,
        )
    else:
        query = query.filter(
            Notification.recipient_type == "admin",
            Notification.recipient_id == actor.id,
        )
    return query.order_by(Notification.id.desc()).all()


@app.patch("/notifications/{notification_id}/read", response_model=NotificationResponse)
def mark_notification_read(
    notification_id: int,
    principal=Depends(require_company_member),
    db: Session = Depends(get_db),
):
    payload, actor = principal
    query = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.company_id == payload["company_id"],
    )
    if isinstance(actor, User):
        query = query.filter(
            Notification.recipient_type == "user",
            Notification.recipient_id == actor.id,
        )
    else:
        query = query.filter(
            Notification.recipient_type == "admin",
            Notification.recipient_id == actor.id,
        )
    notif = query.first()
    if notif is None:
        raise HTTPException(status_code=404, detail="Notification not found.")

    notif.is_read = True
    db.commit()
    db.refresh(notif)
    return notif

@app.patch("/tasks/{task_id}/status", response_model=TaskResponse)
async def update_task_status(task_id: int, data: TaskStatusUpdate, principal=Depends(require_company_member), db: Session = Depends(get_db)) -> Task:
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

    # 🔔 Notify admin when status is changed by a user
    if isinstance(actor, User):
        status_notification = Notification(
            recipient_id=task.company_id,
            recipient_type="admin",
            company_id=task.company_id,
            title="Task Status Updated",
            message=f"User updated task '{task.title}' status from {old_status} to {task.status}."
        )
        db.add(status_notification)
        db.commit()

        await manager.broadcast_to_company(
            task.company_id,
            {"type": "NOTIFICATION", "message": f"Task '{task.title}' status updated to {task.status}"}
        )

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

@app.post(
    "/tasks/{task_id}/comments/",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_task_comment(
    task_id: int,
    data: CommentCreate,
    principal=Depends(require_company_member),
    db: Session = Depends(get_db),
):
    payload, actor = principal
    company_id = payload["company_id"]

    task = db.query(Task).filter(
        Task.id == task_id,
        Task.company_id == company_id,
    ).first()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")

    if not isinstance(actor, User):
        raise HTTPException(
            status_code=403,
            detail="Only assigned team members can post task comments here.",
        )

    if task.assigned_to_id != actor.id:
        raise HTTPException(
            status_code=403,
            detail="You can only comment on tasks assigned to you.",
        )

    cleaned = data.content.strip()
    if not cleaned:
        raise HTTPException(status_code=422, detail="Comment cannot be empty.")

    try:
        comment = Comment(
            company_id=company_id,
            task_id=task.id,
            user_id=actor.id,
            content=cleaned,
        )
        db.add(comment)
        db.flush()

        notif = Notification(
            recipient_id=company_id,
            recipient_type="admin",
            company_id=company_id,
            task_id=task.id,
            comment_id=comment.id,
            title=f"New Comment on '{task.title}'",
            message=f"{actor.email} commented on '{task.title}': {cleaned[:120]}",
            is_read=False,
        )
        db.add(notif)
        db.commit()
        db.refresh(comment)
        db.refresh(notif)
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to save comment and notification.")

    await manager.broadcast_to_company(
        company_id,
        {
            "type": "NOTIFICATION",
            "notification_id": notif.id,
            "task_id": task.id,
            "comment_id": comment.id,
            "title": notif.title,
            "message": notif.message,
        },
    )
    return comment


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
            "company_id": comment.company_id,
            "content": comment.content,
            "task_id": comment.task_id,
            "user_id": comment.user_id,
            "author_email": email,
            "created_at": comment.created_at,
        }
        for comment, email in rows
    ]


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
async def create_group(
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

    # 🔔 Persistent In-App Database Notification for Group Creation
    group_notification = Notification(
        recipient_id=company.id,
        recipient_type="admin",
        company_id=company.id,
        title="Group Created",
        message=f"New group created: {group.name}."
    )
    db.add(group_notification)
    db.commit()

    await manager.broadcast_to_company(
        company.id,
        {"type": "NOTIFICATION", "message": f"New group created: {group.name}"}
    )

    return group


@app.get("/groups/", response_model=list[GroupResponse])
def list_groups(
    principal=Depends(require_company_member),
    db: Session = Depends(get_db),
):
    payload, actor = principal
    company_id = payload["company_id"]

    query = db.query(Group).options(joinedload(Group.users)).filter(Group.company_id == company_id)

    # Regular users see only groups they are members of
    if isinstance(actor, User):
        user_group_ids_subquery = user_group_ids(db, company_id, actor.id)
        query = query.filter(Group.id.in_(select(user_group_ids_subquery.c.group_id)))

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

@app.delete("/groups/{group_id}/members/{user_id}", status_code=204)
def remove_user_from_group(
    group_id: int,
    user_id: int,
    principal=Depends(require_company_admin), # Automatically enforces admin privileges safely
    db: Session = Depends(get_db),
):
    payload, company = principal
    company_id = payload["company_id"]
    
    # 1. Verify group belongs to tenant
    group = db.query(Group).filter(
        Group.id == group_id, 
        Group.company_id == company_id
    ).first()
    
    if not group:
        raise HTTPException(status_code=404, detail="Group not found.")
    
    # 2. Delete association record using GroupMembership model
    membership = db.query(GroupMembership).filter(
        GroupMembership.company_id == company_id,
        GroupMembership.group_id == group_id,
        GroupMembership.user_id == user_id
    ).first()
    
    if membership:
        db.delete(membership)
        audit_event(
            db,
            company_id=company_id,
            actor_type="company_admin",
            actor_id=company.id,
            action="group.member.remove",
            target_type="group_membership",
            target_id=f"{group_id}:{user_id}",
        )
        db.commit()
        
    return Response(status_code=204)

@app.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(
    group_id: int,
    principal=Depends(require_company_admin),
    db: Session = Depends(get_db),
) -> Response:
    payload, company = principal
    company_id = payload["company_id"]

    # Verify the group belongs to the company before deleting
    group = db.query(Group).filter(
        Group.id == group_id,
        Group.company_id == company_id,
    ).first()

    if group is None:
        raise HTTPException(status_code=404, detail="Group not found.")

    audit_event(
        db,
        company_id=company.id,
        actor_type="company_admin",
        actor_id=company.id,
        action="group.delete",
        target_type="group",
        target_id=group.id,
    )
    
    db.delete(group)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")

@app.post("/auth/google", response_model=MessageResponse)
def google_auth_login(data: GoogleAuthRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    token = data.credential.strip()
    if not token:
        raise HTTPException(status_code=400, detail="Google credential missing.")

    try:
        # Verify the Google ID token securely
        idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), GOOGLE_CLIENT_ID)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid Google token.")

    if not idinfo.get("email_verified"):
        raise HTTPException(status_code=403, detail="Google email must be verified.")

    email = (idinfo.get("email") or "").strip().lower()
    local_part, sep, domain = email.partition("@")
    if not sep or not local_part or domain != "gmail.com":
        raise HTTPException(status_code=403, detail="Only @gmail.com Google accounts are allowed.")

    # 1. Check if regular user exists in the database
    user = db.query(User).filter(User.email == email).first()
    if user is not None:
        if not user.is_active:
            raise HTTPException(status_code=403, detail="User account is deactivated.")

        # Create standard TaskFlow session for user
        create_session(response, db, subject_id=user.id, company_id=user.company_id, principal_type="user", role=user.role)
        db.commit()
        return {"message": "Google authentication successful."}

    # 2. Check if company admin exists in the Company table
    company = db.query(Company).filter(Company.admin_email == email).first()
    if company is not None:
        # Create session for company admin
        create_session(response, db, subject_id=company.id, company_id=company.id, principal_type="company_admin", role="admin")
        db.commit()
        return {"message": "Google authentication successful."}

    # If neither user nor company admin is found
    raise HTTPException(status_code=404, detail="No company account associated with this Google email.")


def _authenticate_websocket_company(websocket: WebSocket, db: Session) -> int | None:
    access_token = websocket.cookies.get(ACCESS_COOKIE)
    if not access_token:
        return None
    try:
        payload = decode_token(access_token)
    except HTTPException:
        return None

    auth_session = db.get(AuthSession, payload["sid"])
    if (
        auth_session is None
        or auth_session.revoked_at is not None
        or datetime_is_expired(auth_session.expires_at)
        or auth_session.company_id != payload["company_id"]
    ):
        return None

    company = db.get(Company, payload["company_id"])
    if company is None:
        return None

    principal_type = payload.get("principal_type")
    if principal_type == "company_admin":
        if (
            auth_session.principal_type != "company_admin"
            or auth_session.principal_id != company.id
            or payload.get("role") != UserRole.admin.value
            or str(company.id) != payload["sub"]
        ):
            return None
        return company.id

    if principal_type == "user":
        try:
            user_id = int(payload["sub"])
        except (KeyError, TypeError, ValueError):
            return None
        if auth_session.principal_id != user_id:
            return None
        user = db.query(User).filter(
            User.id == user_id,
            User.company_id == company.id,
        ).first()
        if user is None or not user.is_active or user.role != payload.get("role"):
            return None
        return company.id

    return None


@app.websocket("/ws/notifications")
async def websocket_endpoint(websocket: WebSocket, db: Session = Depends(get_db)):
    company_id = _authenticate_websocket_company(websocket, db)
    if company_id is None:
        await websocket.close(code=1008)
        return

    await manager.connect(company_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(company_id, websocket)


@app.post(
    "/tasks/",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_task(
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
            Project.company_id == company.id,
        ).first()
        if project is None:
            raise HTTPException(
                status_code=400,
                detail="Project not found in your company.",
            )

    assignee = None
    if data.assigned_to_id is not None:
        assignee = db.query(User).filter(
            User.id == data.assigned_to_id,
            User.company_id == company.id,
            User.is_active.is_(True),
        ).first()
        if assignee is None:
            raise HTTPException(
                status_code=400,
                detail="Assigned user is not active in this company.",
            )

    task = Task(
        title=data.title.strip(),
        description=data.description.strip() if data.description else None,
        status=data.status.value,
        priority=data.priority.value,
        due_at=data.due_at,
        assigned_to_id=data.assigned_to_id,
        project_id=data.project_id,
        company_id=company.id,
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

    if assignee is not None:
        assignment_notification = Notification(
            recipient_id=assignee.id,
            recipient_type="user",
            company_id=company.id,
            title="New Assignment",
            message=f"You have been assigned to: {task.title}.",
        )
        db.add(assignment_notification)

        if assignee.email:
            send_admin_email_alert(
                admin_email=assignee.email,
                subject=f"TaskFlow OS: New Task Assigned - {task.title}",
                body=f"You have been assigned task '{task.title}' (Priority: {task.priority}).",
            )

    if company and company.admin_email:
        send_admin_email_alert(
            admin_email=company.admin_email,
            subject=f"TaskFlow OS: New Task Dispatched - {task.title}",
            body=(
                f"Task '{task.title}' (Priority: {task.priority}) has been created in company ID {company.id}."
                + (f" Assigned to: {assignee.email}." if assignee else " Assigned to: Unassigned.")
            ),
        )

    db.commit()
    db.refresh(task)

    await manager.broadcast_to_company(
        company.id,
        {"type": "NOTIFICATION", "message": f"New task dispatched: {task.title}"},
    )
    return task


@app.post("/tasks/{task_id}/ai", response_model=TaskAIResponse)
def run_task_ai(
    task_id: int,
    data: TaskAIRequest,
    request: Request,
    principal=Depends(require_company_member),
    db: Session = Depends(get_db),
):
    payload, actor = principal
    company_id = payload["company_id"]
    enforce_rate_limit(request, "task-ai", 30, 60)

    task = db.query(Task).filter(
        Task.id == task_id,
        Task.company_id == company_id,
    ).first()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")

    if isinstance(actor, User) and task.assigned_to_id != actor.id:
        raise HTTPException(
            status_code=403,
            detail="You can only use AI assistance on tasks assigned to you.",
        )

    try:
        answer, model_used = generate_task_ai_response(
            db=db,
            task=task,
            mode=data.mode,
            question=data.question,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        import traceback
        print("AI error:", type(exc).__name__, exc)
        traceback.print_exc()
        raise HTTPException(status_code=502, detail="AI service temporarily unavailable.")

    return {
        "task_id": task.id,
        "mode": data.mode,
        "model": model_used,
        "response": answer,
    }


@app.post("/projects/{project_id}/ai", response_model=ProjectAIResponse)
def run_project_ai(
    project_id: int,
    data: ProjectAIRequest,
    request: Request,
    principal=Depends(require_company_member),
    db: Session = Depends(get_db),
):
    payload, actor = principal
    company_id = payload["company_id"]
    enforce_rate_limit(request, "project-ai", 30, 60)

    project = (
        visible_project_query(db, company_id, actor)
        .filter(Project.id == project_id)
        .first()
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")

    question_text = (data.question or "").strip()
    if data.mode == "ask" and not question_text:
        raise HTTPException(status_code=422, detail="Question is required.")

    project_tasks = (
        db.query(Task)
        .filter(
            Task.company_id == company_id,
            Task.project_id == project.id,
        )
        .order_by(Task.id)
        .limit(50)
        .all()
    )

    task_lines = [
        f"- [#{t.id}] {t.title} (status={t.status}, priority={t.priority}): {t.description or 'No description'}"
        for t in project_tasks
    ]
    scoped_context = (
        f"Project ID: {project.id}\n"
        f"Project Name: {project.name}\n"
        f"Project Description: {project.description or 'No description provided.'}\n"
        f"Project Tasks ({len(project_tasks)}):\n"
        + ("\n".join(task_lines) if task_lines else "No tasks in this project.")
    )

    scoped_task_proxy = SimpleNamespace(
        id=project.id,
        title=f"Project: {project.name}",
        description=scoped_context,
        status="in_progress",
        priority="normal",
        company_id=company_id,
        project_id=project.id,
        assigned_to_id=None,
    )

    prompt_instruction = (
        f"{question_text}\n\n"
        "Respond directly to the user's request above (such as a step-by-step breakdown, plan, status check, or explanation) "
        "grounded strictly in the project details and tasks in the context. Do not just summarize unless asked."
        if data.mode == "ask"
        else "Provide a concise summary of this project and its tasks strictly from the context provided."
    )

    try:
        answer, model_used = generate_task_ai_response(
            db=db,
            task=scoped_task_proxy,
            mode="ask",
            question=prompt_instruction,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        import traceback
        print("Project AI error:", type(exc).__name__, exc)
        traceback.print_exc()
        raise HTTPException(status_code=502, detail="AI service temporarily unavailable.")

    return {
        "project_id": project.id,
        "mode": data.mode,
        "model": model_used,
        "response": answer,
    }

@app.get("/")
def root():
    return {
        "service": "TaskFlow API",
        "version": "2.0.0",
        "status": "ok",
        "openapi": "/openapi.json",
        "health": "/health",
    }