import os
from dotenv import load_dotenv
from openai import OpenAI
from sqlalchemy.orm import Session
from app.models import Comment, Task, User

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=True)

DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "openai/gpt-oss-20b"


def _get_llm_config() -> tuple[str, str, str]:
    api_key = os.getenv("LLM_API_KEY", "").strip()
    base_url = os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL
    model = os.getenv("LLM_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    return api_key, base_url, model


def build_task_context(db: Session, task: Task) -> str:
    comments = (
        db.query(Comment, User.email)
        .join(User, User.id == Comment.user_id)
        .filter(Comment.task_id == task.id, Comment.company_id == task.company_id)
        .order_by(Comment.id)
        .limit(30)
        .all()
    )

    comment_lines = (
        "\n".join(f"- {email}: {c.content}" for c, email in comments)
        if comments
        else "- None"
    )

    return (
        f"Task ID: #{task.id}\n"
        f"Title: {task.title}\n"
        f"Status: {task.status}\n"
        f"Priority: {task.priority}\n"
        f"Description: {task.description or 'No description provided.'}\n"
        f"Recent Task Comments:\n{comment_lines}"
    )


def generate_task_ai_response(
    *,
    db: Session,
    task: Task,
    mode: str,
    question: str | None = None,
) -> tuple[str, str]:
    api_key, base_url, model = _get_llm_config()
    if not api_key:
        raise RuntimeError("LLM_API_KEY is not configured on the server.")

    client = OpenAI(api_key=api_key, base_url=base_url)
    task_context = build_task_context(db, task)

    system_prompt = (
        "You are a concise, professional engineering task assistant inside TaskFlow. "
        "Answer strictly using the provided task details and task comments. "
        "Do not invent facts, guess missing requirements, or reference external data. "
        "If a question cannot be answered from the provided task details, state clearly "
        "that the information is not specified in the task details and ask the user to "
        "confirm with the project admin."
    )

    if mode == "summarize":
        user_prompt = (
            "Provide a clear, professional summary of this task for the assignee.\n"
            "Include:\n"
            "1. Objective (1-2 sentences)\n"
            "2. Key Requirements & Constraints\n"
            "3. Current Status, Priority & Next Steps\n\n"
            f"{task_context}"
        )
    elif mode == "ask":
        cleaned_q = (question or "").strip()
        if not cleaned_q:
            raise ValueError("A question is required when mode is 'ask'.")
        user_prompt = (
            f"Answer the user's question professionally based only on this task:\n"
            f"Question: {cleaned_q}\n\n"
            f"{task_context}"
        )
    else:
        raise ValueError("Unsupported AI mode.")

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )

    text = ((completion.choices[0].message.content if completion.choices else "") or "").strip()
    if not text:
        raise RuntimeError("Empty response received from the language model.")

    return text, model