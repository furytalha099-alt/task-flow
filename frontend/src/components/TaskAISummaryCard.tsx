import { useState } from "react";

function getCsrfToken() {
  const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : "";
}

interface TaskAISummaryCardProps {
  task: {
    id: number | string;
    title?: string;
    description?: string | null;
    status?: string;
    priority?: string;
    assigned_to_id?: number | string | null;
  } | null;
  currentUserId?: number | string | null;
  userRole?: string;
  apiBaseUrl?: string;
}

export function TaskAISummaryCard({
  task,
  currentUserId = null,
  userRole = "member",
  apiBaseUrl = "",
}: TaskAISummaryCardProps) {
  const [summary, setSummary] = useState("");
  const [model, setModel] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const canUseAI =
    userRole === "admin" ||
    (currentUserId != null &&
      task?.assigned_to_id != null &&
      Number(task.assigned_to_id) === Number(currentUserId));
console.log("AI visibility check:", {
    taskId: task?.id,
    userRole,
    currentUserId,
    assigned_to_id: task?.assigned_to_id,
    taskKeys: task ? Object.keys(task) : [],
    canUseAI,
  });

  if (!task || !canUseAI) {
    return null;
  }

  async function handleGenerateSummary() {
    setLoading(true);
    setError("");

    try {
      if (!task) {
        throw new Error("Task is missing.");
      }

      const csrfToken = getCsrfToken();
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
      };
      if (csrfToken) {
        headers["X-CSRF-Token"] = csrfToken;
      }

      const response = await fetch(`${apiBaseUrl}/tasks/${task.id}/ai`, {
        method: "POST",
        credentials: "include",
        headers,
        body: JSON.stringify({ mode: "summarize" }),
      });

      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || `Summarization failed (${response.status})`);
      }

      setSummary(payload.response || "");
      setModel(payload.model || "");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Unable to summarize task.");
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
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "12px",
          flexWrap: "wrap",
        }}
      >
        <strong style={{ fontSize: "13px", color: "#f8fafc" }}>
          AI Task Summary
        </strong>
        <button
          type="button"
          onClick={handleGenerateSummary}
          disabled={loading}
          style={{
            background: "rgba(99, 102, 241, 0.2)",
            color: "#818cf8",
            border: "1px solid rgba(99, 102, 241, 0.4)",
            padding: "6px 12px",
            borderRadius: "8px",
            fontSize: "12px",
            fontWeight: 700,
            cursor: loading ? "not-allowed" : "pointer",
          }}
        >
          {loading ? "Generating Summary..." : "Summarize Task"}
        </button>
      </div>

      {error && (
        <p
          role="alert"
          style={{
            marginTop: "10px",
            fontSize: "12px",
            color: "#f87171",
            wordBreak: "break-word",
          }}
        >
          {error}
        </p>
      )}

      {summary && (
        <div style={{ marginTop: "12px" }}>
          {model && (
            <div style={{ fontSize: "11px", color: "#94a3b8", marginBottom: "6px" }}>
              Model: {model}
            </div>
          )}
          <pre
            style={{
              margin: 0,
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              fontFamily: "inherit",
              fontSize: "13px",
              lineHeight: 1.55,
              color: "#e2e8f0",
            }}
          >
            {summary}
          </pre>
        </div>
      )}
    </div>
  );
}