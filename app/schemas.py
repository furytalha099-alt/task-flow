"""Validated request and response models."""
from pydantic import model_validator
from typing import Literal
from datetime import datetime
from typing import Annotated
from typing import Optional
from pydantic import AwareDatetime, BaseModel, ConfigDict, EmailStr, Field, StringConstraints, AfterValidator
from app.models import TaskPriority, TaskStatus, UserRole

def _require_gmail(value: str) -> str:
    normalized = value.strip().lower()
    local_part, sep, domain = normalized.partition("@")
    if not sep or not local_part or domain != "gmail.com":
        raise ValueError("Only @gmail.com email addresses are allowed.")
    return normalized

GmailEmail = Annotated[EmailStr, AfterValidator(lambda v: _require_gmail(str(v)))]

Subdomain = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=3, max_length=63, pattern=r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])$")]
Password = Annotated[str, Field(min_length=12, max_length=128)]


class CompanyCreate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=160)]
    subdomain: Subdomain
    admin_email: GmailEmail
    admin_password: Password


class CompanyUpdate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=160)]
    subdomain: Subdomain


class CompanyPatch(BaseModel):
    name: Annotated[str | None, Field(min_length=1, max_length=160)] = None
    subdomain: Subdomain | None = None


class CompanyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    subdomain: str
    admin_email: EmailStr


class CompanyLogin(BaseModel):
    admin_email: GmailEmail
    admin_password: str = Field(min_length=1, max_length=128)

class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    role: str
    is_active: bool
class UserCreate(BaseModel):
    email: GmailEmail
    password: Password
    role: UserRole = UserRole.member


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    role: UserRole
    is_active: bool
    company_id: int


class UserLogin(BaseModel):
    email: GmailEmail
    password: str = Field(min_length=1, max_length=128)


class TaskCreate(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=200)]
    description: Annotated[str | None, Field(max_length=10000)] = None
    status: TaskStatus = TaskStatus.todo
    priority: TaskPriority = TaskPriority.normal
    due_at: AwareDatetime | None = None
    project_id: int | None = Field(default=None, gt=0)
    assigned_to_id: int | None = Field(default=None, gt=0)


class TaskUpdate(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    description: Annotated[str | None, Field(max_length=10000)] = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_at: AwareDatetime | None = None
    project_id: int | None = Field(default=None, gt=0)
    assigned_to_id: int | None = Field(default=None, gt=0)

class TaskStatusUpdate(BaseModel):
    status: TaskStatus


class CommentCreate(BaseModel):
    content: Annotated[str, Field(min_length=1, max_length=10000)]


class CommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    content: str
    task_id: int
    user_id: int
    created_at: datetime

class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    due_at: datetime | None
    company_id: int
    project_id: int | None
    assigned_to_id: int | None
    assignee_name: str | None = None  # <--- Ensure this is present

class ProjectCreate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=160)]
    description: Annotated[str | None, Field(max_length=10000)] = None
    group_id: int | None = Field(default=None, gt=0)


class ProjectUpdate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=160)]
    description: Annotated[str | None, Field(max_length=10000)] = None
    group_id: int | None = Field(default=None, gt=0)

class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    company_id: int
    group_id: int | None


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int | None
    actor_type: str
    actor_id: int | None
    action: str
    target_type: str
    target_id: str
    details: dict
    occurred_at: datetime


class CommentWithAuthorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    content: str
    task_id: int
    user_id: int
    author_email: EmailStr
    created_at: datetime

class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    recipient_id: int
    recipient_type: str
    company_id: int
    task_id: int | None = None
    comment_id: int | None = None
    title: str
    message: str
    is_read: bool
    created_at: datetime

class MessageResponse(BaseModel):
    message: str

class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: Optional[str] = None


class GroupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None
    company_id: int
    users: list[UserSummary] = []  # <--- Change 'members' to 'users'

class GoogleAuthRequest(BaseModel):
    credential: str    


class TaskAIRequest(BaseModel):
    mode: Literal["summarize", "ask"] = "summarize"
    question: str | None = Field(default=None, max_length=1000)


class TaskAIResponse(BaseModel):
    task_id: int
    mode: Literal["summarize", "ask"]
    model: str
    response: str


class ProjectAIRequest(BaseModel):
    mode: Literal["ask", "summarize"] = "ask"
    question: str | None = Field(default=None, min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_question_for_ask(self):
        if self.mode == "ask" and (not self.question or not self.question.strip()):
            raise ValueError("A question is required when mode is 'ask'.")
        return self


class ProjectAIResponse(BaseModel):
    project_id: int
    mode: Literal["ask", "summarize"]
    model: str
    response: str