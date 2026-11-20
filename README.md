# TaskFlow OS

**TaskFlow OS** is a multi-tenant task, project, group, and workflow management backend built with **FastAPI**, **SQLAlchemy 2.0**, **PostgreSQL (Neon)**, **Redis**, and **Pydantic v2**, paired with a **React + TypeScript + Vite** frontend (`frontend/`) and an automated **`pytest` + GitHub Actions** CI/CD pipeline.

It is structured around tenant-scoped data isolation, authenticated sessions/JWT workflows, relational schema evolution with Alembic, real-time WebSocket updates, rate-limiting controls, and AI-assisted task/project workflows (`app/ai_assistant.py`).

---

## Key Capabilities & Architecture

- **Multi-Tenant Backend Architecture:** Tenant-aware domain modeling and request scoping so organizations, users, groups, projects, tasks, comments, and notifications stay isolated per tenant.
- **Authentication & Access Control:** Token/session authentication, credential/key handling (`SECRET_KEY`, `PLATFORM_MASTER_KEY`), and protected endpoints across core resources.
- **Relational Persistence & Migrations:** SQLAlchemy 2.0 ORM models (`app/models.py`) and Pydantic v2 schemas (`app/schemas.py`) paired with versioned Alembic migrations (`migrations/versions/`) targeting PostgreSQL / Neon in production and SQLite in isolated test/CI runs.
- **Caching, Rate Limiting & Real-Time Updates:** Redis integration (`REDIS_URL`) for caching/coordination, rate-limit controls, and WebSocket connection management for live updates.
- **AI Assistant & Summarization:** Dedicated assistant module (`app/ai_assistant.py`) and frontend cards (`TaskAISummaryCard.tsx`, `ProjectAIAskCard.tsx`) for task and project assistance.
- **Frontend Workspace:** React + TypeScript + Vite application (`frontend/`) covering dashboard views, command center, projects, tasks, groups, users, tenant settings, and user guide.
- **Automated Testing & CI/CD:** `pytest` suite (`tests/conftest.py`, `tests/test_api.py`) using isolated fixtures (including `DummyConnectionManager` and `_reset_rate_limits`), wired to GitHub Actions (`.github/workflows/ci.yml`) and containerized with a `Dockerfile`.

---

## Tech Stack

| Layer | Technologies |
| :--- | :--- |
| **API & Backend** | Python, FastAPI, Uvicorn, Pydantic v2 |
| **Database & Migrations** | SQLAlchemy 2.0, PostgreSQL (Neon), Alembic, SQLite (test/CI) |
| **Caching & Real-Time** | Redis, WebSockets |
| **Frontend** | React, TypeScript, Vite |
| **Testing, Containerization & CI** | `pytest`, Docker (`python:3.13-slim`), GitHub Actions |

---

## Project Structure

```text
task flow/
├── .github/
│   └── workflows/
│       └── ci.yml                  # GitHub Actions CI workflow (pytest + Docker build check)
├── app/
│   ├── ai_assistant.py             # AI assistant & summarization logic
│   ├── main.py                     # FastAPI application, routes, middleware, WebSockets
│   ├── models.py                   # SQLAlchemy 2.0 ORM models
│   └── schemas.py                  # Pydantic v2 request/response schemas
├── frontend/
│   ├── src/
│   │   ├── components/             # Dashboard, CommandCenter, Projects, Tasks, Groups, Users, Settings
│   │   ├── App.tsx                 # Main frontend application shell
│   │   └── main.tsx                # Frontend entry point
│   ├── package.json                # Frontend dependencies & scripts
│   └── vite.config.ts              # Vite configuration
├── migrations/
│   └── versions/                   # Alembic migration revisions
├── tests/
│   ├── __init__.py
│   ├── conftest.py                 # Test fixtures, DB setup, connection & rate-limit helpers
│   └── test_api.py                 # End-to-end API, auth, multi-tenancy & workflow tests
├── Dockerfile                      # Production-ready container image definition
├── requirements.txt                # Backend Python dependencies
└── README.md