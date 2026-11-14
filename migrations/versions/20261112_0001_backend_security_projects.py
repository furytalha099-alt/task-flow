"""Add projects, revocable auth sessions, audit log, and tenant constraints.

For databases created by the earlier TaskFlow MVP this migration adds the new
tables and nullable tasks.project_id column while preserving existing rows.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
from app.database import Base
from app import models  # noqa: F401 - ensure all current tables are registered

revision = "20261112_0001"
down_revision = None
branch_labels = None
depends_on = None


def _inspector():
    return inspect(op.get_bind())


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(_inspector().get_table_names())

    # Preserve data from the earlier MVP schema while adding newer columns.
    if "users" in tables:
        user_cols = {c["name"] for c in _inspector().get_columns("users")}
        if "role" not in user_cols:
            op.add_column("users", sa.Column("role", sa.String(20), nullable=False, server_default="member"))
        if "is_active" not in user_cols:
            op.add_column("users", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    if "tasks" in tables:
        task_cols = {c["name"] for c in _inspector().get_columns("tasks")}
        if "project_id" not in task_cols:
            op.add_column("tasks", sa.Column("project_id", sa.Integer(), nullable=True))
        if "priority" not in task_cols:
            op.add_column("tasks", sa.Column("priority", sa.String(20), nullable=False, server_default="normal"))
        if "due_at" not in task_cols:
            op.add_column("tasks", sa.Column("due_at", sa.DateTime(timezone=True), nullable=True))

    # Creates all tables on an empty database and only missing tables otherwise.
    Base.metadata.create_all(bind=bind)

    tables = set(_inspector().get_table_names())
    if "tasks" in tables:
        indexes = {i["name"] for i in _inspector().get_indexes("tasks")}
        if "ix_tasks_project_id" not in indexes:
            op.create_index("ix_tasks_project_id", "tasks", ["project_id"])
        if "ix_tasks_due_at" not in indexes:
            op.create_index("ix_tasks_due_at", "tasks", ["due_at"])

        # Before adding database-level tenant constraints, fail clearly if old
        # data already contains a cross-company assignee or project reference.
        bad_assignee = bind.execute(text(
            "SELECT count(*) FROM tasks t JOIN users u ON u.id=t.assigned_to_id "
            "WHERE t.company_id <> u.company_id"
        )).scalar_one()
        if bad_assignee:
            raise RuntimeError("Migration stopped: tasks contain cross-company assignees; repair those rows first.")

        unique_by_table = {
            "users": {tuple(u["column_names"]) for u in _inspector().get_unique_constraints("users")},
            "projects": {tuple(u["column_names"]) for u in _inspector().get_unique_constraints("projects")},
        }
        if ("id", "company_id") not in unique_by_table["users"]:
            op.create_unique_constraint("uq_user_id_company", "users", ["id", "company_id"])
        if ("id", "company_id") not in unique_by_table["projects"]:
            op.create_unique_constraint("uq_project_id_company", "projects", ["id", "company_id"])

        existing_fks = {fk.get("name") for fk in _inspector().get_foreign_keys("tasks")}
        if "fk_task_project_same_company" not in existing_fks:
            op.create_foreign_key(
                "fk_task_project_same_company", "tasks", "projects",
                ["project_id", "company_id"], ["id", "company_id"], ondelete="CASCADE",
            )
        if "fk_task_assignee_same_company" not in existing_fks:
            op.create_foreign_key(
                "fk_task_assignee_same_company", "tasks", "users",
                ["assigned_to_id", "company_id"], ["id", "company_id"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "tasks" in tables:
        for name in ("fk_task_assignee_same_company", "fk_task_project_same_company"):
            if name in {fk.get("name") for fk in inspect(bind).get_foreign_keys("tasks")}:
                op.drop_constraint(name, "tasks", type_="foreignkey")
        if "ix_tasks_project_id" in {i["name"] for i in inspect(bind).get_indexes("tasks")}:
            op.drop_index("ix_tasks_project_id", table_name="tasks")
        if "ix_tasks_due_at" in {i["name"] for i in inspect(bind).get_indexes("tasks")}:
            op.drop_index("ix_tasks_due_at", table_name="tasks")
        if "project_id" in {c["name"] for c in inspect(bind).get_columns("tasks")}:
            op.drop_column("tasks", "project_id")
        task_columns = {c["name"] for c in inspect(bind).get_columns("tasks")}
        if "due_at" in task_columns:
            op.drop_column("tasks", "due_at")
        if "priority" in task_columns:
            op.drop_column("tasks", "priority")
    if "users" in tables and "uq_user_id_company" in {u["name"] for u in inspect(bind).get_unique_constraints("users")}:
        op.drop_constraint("uq_user_id_company", "users", type_="unique")
    if "projects" in tables:
        for name in ("uq_project_id_company", "uq_project_company_name"):
            if name in {u["name"] for u in inspect(bind).get_unique_constraints("projects")}:
                op.drop_constraint(name, "projects", type_="unique")
    for table in ("auth_refresh_tokens", "auth_sessions", "audit_events", "projects"):
        if table in set(inspect(bind).get_table_names()):
            op.drop_table(table)
