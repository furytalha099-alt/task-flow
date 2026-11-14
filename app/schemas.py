"""Validated request and response models."""
from datetime import datetime
from typing import Annotated
from typing import Optional
from pydantic import AwareDatetime, BaseModel, ConfigDict, EmailStr, Field, StringConstraints
from app.models import TaskPriority, TaskStatus, UserRole

Subdomain = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=3, max_length=63, pattern=r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])$")]
Password = Annotated[str, Field(min_length=12, max_length=128)]


class CompanyCreate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=160)]
    subdomain: Subdomain
    admin_email: EmailStr
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
    admin_email: EmailStr
    admin_password: str = Field(min_length=1, max_length=128)


class UserCreate(BaseModel):
    email: EmailStr
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
    email: EmailStr
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
    title: Annotated[str, Field(min_length=1, max_length=200)]
    description: Annotated[str | None, Field(max_length=10000)] = None
    status: TaskStatus
    priority: TaskPriority
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
    content: str
    task_id: int
    user_id: int


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


class ProjectCreate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=160)]
    description: Annotated[str | None, Field(max_length=10000)] = None


class ProjectUpdate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=160)]
    description: Annotated[str | None, Field(max_length=10000)] = None

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
    id: int
    content: str
    task_id: int
    user_id: int
    author_email: EmailStr


class MessageResponse(BaseModel):
    message: str

class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: Optional[str] = None


class GroupResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    company_id: int

    class Config:
        from_attributes = True


class ProjectCreate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=160)]
    description: Annotated[str | None, Field(max_length=10000)] = None
    group_id: int | None = Field(default=None, gt=0)


class ProjectUpdate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=160)]
    description: Annotated[str | None, Field(max_length=10000)] = None
    group_id: int | None = Field(default=None, gt=0)