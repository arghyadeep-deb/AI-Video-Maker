"use client";

import type { Job } from "@/lib/api";

// Honest stages beat a fake smooth bar — specs/03-design/07-job-queue-and-progress.md.
export default function StageChecklist({ job }: { job: Job }) {
  const currentIndex = job.stage ? job.stages.indexOf(job.stage) : -1;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
      {job.stages.map((stage, i) => {
        const isDone =
          job.status === "done" || (currentIndex !== -1 && i < currentIndex);
        const isCurrent = i === currentIndex && job.status === "running";
        const isFailed = isCurrent && job.status === "failed";

        return (
          <div
            key={stage}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.75rem",
              padding: "0.6rem 0.9rem",
              borderRadius: 8,
              border: "1px solid var(--border)",
              background: isCurrent ? "var(--surface)" : "transparent",
              opacity: isDone || isCurrent ? 1 : 0.5,
            }}
          >
            <span
              aria-hidden
              style={{
                width: 10,
                height: 10,
                borderRadius: "50%",
                flexShrink: 0,
                background: isDone
                  ? "var(--ok)"
                  : isFailed
                    ? "var(--bad)"
                    : isCurrent
                      ? "var(--accent)"
                      : "var(--border)",
              }}
            />
            <span style={{ flex: 1, textTransform: "capitalize" }}>
              {stage.replace(/_/g, " ")}
            </span>
            {isCurrent && (
              <span style={{ color: "var(--text-dim)", fontSize: "0.85rem" }}>
                {job.progress.toFixed(0)}%
              </span>
            )}
            {isDone && <span style={{ color: "var(--ok)" }}>✓</span>}
          </div>
        );
      })}

      {job.status === "failed" && job.error && (
        <p style={{ color: "var(--bad)", fontSize: "0.85rem", marginTop: "0.25rem" }}>
          {job.error}
        </p>
      )}
      {job.status === "cancelled" && (
        <p style={{ color: "var(--text-dim)", fontSize: "0.85rem", marginTop: "0.25rem" }}>
          Cancelled.
        </p>
      )}
    </div>
  );
}
