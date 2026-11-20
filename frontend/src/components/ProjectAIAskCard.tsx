import React, { useState } from "react";

function getCsrfToken() {
  const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : "";
}

export function ProjectAIAskCard({
  project,
  currentUserId = null,
  userRole = "member",
  apiBaseUrl = "",
}) {
  const [isAskOpen, setIsAskOpen] = useState(true);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [model, setModel] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  if (!project) {
    return null;
  }

  async function handleAskQuestion(e) {
    e.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || loading) {
      return;
    }

    setLoading(true);
    setError("");

    try {
      const csrfToken = getCsrfToken();
      const headers = {
        "Content-Type": "application/json",
      };
      if (csrfToken) {
        headers["X-CSRF-Token"] = csrfToken;
      }

      const response = await fetch(`${apiBaseUrl}/projects/${project.id}/ai`, {
        method: "POST",
        credentials: "include",
        headers,
        body: JSON.stringify({
          mode: "ask",
          question: trimmed,
          project_id: project.id,
          user_id: currentUserId,
          role: userRole,
        }),
      });

      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || `Project AI request failed (${response.status})`);
      }

      setAnswer(payload.response || "");
      setModel(payload.model || "");
    } catch (err) {
      setError(err.message || "Unable to answer project question.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      style={{
        width: "100%",
        boxSizing: "border-box",
        background: "#131d31",
        border: "1px solid #334155",
        borderRadius: "12px",
        padding: "14px 16px",
        marginTop: "12px",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "12px",
          flexWrap: "wrap",
          marginBottom: "10px",
        }}
      >
        <strong style={{ fontSize: "13px", color: "#f8fafc" }}>
          Ask AI About {project.name || `Project #${project.id}`}
        </strong>
        <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
          {model && (
            <span style={{ fontSize: "11px", color: "#94a3b8" }}>
              Model: {model}
            </span>
          )}
          <button
            type="button"
            onClick={() => setIsAskOpen((prev) => !prev)}
            style={{
              background: "rgba(99, 102, 241, 0.22)",
              color: "#c7d2fe",
              border: "1px solid rgba(99, 102, 241, 0.45)",
              padding: "6px 12px",
              borderRadius: "8px",
              fontSize: "12px",
              fontWeight: 700,
              cursor: "pointer",
            }}
          >
            {isAskOpen ? "Hide Ask AI" : "Ask AI"}
          </button>
        </div>
      </div>

      {isAskOpen && (
        <form
          onSubmit={handleAskQuestion}
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "8px",
            width: "100%",
            boxSizing: "border-box",
          }}
        >
          <textarea
            rows={2}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Write anything / comment to ask Groq about this project..."
            disabled={loading}
            style={{
              width: "100%",
              background: "#0c1322",
              border: "1px solid #334155",
              color: "#f8fafc",
              padding: "9px 12px",
              borderRadius: "8px",
              fontSize: "13px",
              lineHeight: 1.45,
              resize: "vertical",
              outline: "none",
              boxSizing: "border-box",
            }}
          />
          <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px" }}>
            <button
              type="submit"
              disabled={loading || !question.trim()}
              style={{
                background: "rgba(99, 102, 241, 0.22)",
                color: "#818cf8",
                border: "1px solid rgba(99, 102, 241, 0.45)",
                padding: "9px 14px",
                borderRadius: "8px",
                fontSize: "12px",
                fontWeight: 700,
                cursor: loading || !question.trim() ? "not-allowed" : "pointer",
              }}
            >
              {loading ? "Asking..." : "Ask Groq"}
            </button>
          </div>
        </form>
      )}

      {error && (
        <p
          role="alert"
          style={{
            marginTop: "10px",
            marginBottom: 0,
            fontSize: "12px",
            color: "#f87171",
            wordBreak: "break-word",
          }}
        >
          {error}
        </p>
      )}

      {answer && (
        <pre
          style={{
            marginTop: "12px",
            marginBottom: 0,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            fontFamily: "inherit",
            fontSize: "13px",
            lineHeight: 1.55,
            color: "#e2e8f0",
          }}
        >
          {answer}
        </pre>
      )}
    </div>
  );
}