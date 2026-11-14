# TaskFlow Backend

TaskFlow is a multi-tenant project and task management API. Each company manages its own users, groups, projects, and tasks, with access controlled by company and role.

## Features

- Company registration and company-admin authentication
- Company user registration and management
- Groups, memberships, and group-based project visibility
- Project and task creation and management
- Task assignment to active users in the same company
- Task status updates and comments
- JWT access and refresh sessions, logout, and bcrypt password hashing
- Company-scoped and role-based authorization
- Audit event records
- PostgreSQL persistence with Neon

## Technology

- Python
- FastAPI
- SQLAlchemy
- Pydantic
- PostgreSQL, Neon, and Psycopg
- Alembic migrations
- OpenAPI and Swagger UI

## Access model

- Company admins manage their company’s users, groups, projects, and tasks.
- Members can see projects and tasks available to their group.
- Members can update status and comment only on tasks assigned to them.
- Company data is scoped to the authenticated user’s company.

## Run locally

Requirements: Python and a PostgreSQL database.

1. Create and activate a virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` and enter your local configuration.
4. Apply database migrations with `alembic upgrade head`.
5. Start the API from the project root:

   `python -m uvicorn app.main:app --reload`

6. Open `http://127.0.0.1:8000/docs` for the interactive API documentation when Swagger is enabled.

Keep `.env` private. Use environment variables or your hosting provider’s secret manager for database credentials and signing keys.

## Database

Alembic manages schema migrations. Neon PostgreSQL stores the application data, including companies, users, groups, projects, tasks, comments, authentication sessions, refresh tokens, and audit events.

## Manual verification

Manually checked through the API:

- Company and member login
- Company and group visibility boundaries
- Task assignment and member status/comment permissions
- Refresh-session behavior
- Database records saved in Neon