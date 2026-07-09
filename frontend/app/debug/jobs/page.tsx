"use client";

// Debug-only page (not one of the 7 product routes) - kicks the noop_render
// demo pipeline so task-07's job worker + polling + checklist can be
// watched live without any real pipeline existing yet.
import { useState } from "react";
import StageChecklist from "@/components/StageChecklist";
import { useJob } from "@/hooks/useJob";
import { ApiRequestError, cancelJob, createDebugNoopJob } from "@/lib/api";

export default function DebugJobsPage() {
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { job, error: pollError } = useJob(jobId);

  async function kickJob() {
    setError(null);
    try {
      const created = await createDebugNoopJob();
      setJobId(created.id);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.hint ?? err.message : "Failed to create job");
    }
  }

  async function cancel() {
    if (!jobId) return;
    try {
      await cancelJob(jobId);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.hint ?? err.message : "Failed to cancel job");
    }
  }

  const busy = job !== null && !["done", "failed", "cancelled"].includes(job.status);

  return (
    <main style={{ maxWidth: 480, margin: "0 auto", padding: "4rem 1.5rem" }}>
      <h1 style={{ fontSize: "1.5rem", fontWeight: 600 }}>Job worker debug</h1>
      <p style={{ color: "var(--text-dim)", marginTop: "0.5rem" }}>
        Kicks the noop_render demo pipeline (3 fake stages) to watch the job worker live.
      </p>

      <div style={{ display: "flex", gap: "0.5rem", marginTop: "1.5rem" }}>
        <button
          type="button"
          onClick={kickJob}
          disabled={busy}
          style={{
            padding: "0.6rem 1.2rem",
            borderRadius: 6,
            border: "none",
            background: "var(--accent)",
            color: "#0b0c0f",
            fontWeight: 600,
            cursor: busy ? "not-allowed" : "pointer",
          }}
        >
          Kick a job
        </button>
        <button
          type="button"
          onClick={cancel}
          disabled={!busy}
          style={{
            padding: "0.6rem 1.2rem",
            borderRadius: 6,
            border: "1px solid var(--bad)",
            background: "transparent",
            color: "var(--bad)",
            cursor: !busy ? "not-allowed" : "pointer",
          }}
        >
          Cancel
        </button>
      </div>

      {(error || pollError) && (
        <p style={{ color: "var(--bad)", marginTop: "1rem" }}>{error ?? pollError}</p>
      )}

      {job && (
        <div style={{ marginTop: "2rem" }}>
          <p style={{ color: "var(--text-dim)", fontSize: "0.85rem", marginBottom: "0.75rem" }}>
            Job {job.id} · {job.status}
          </p>
          <StageChecklist job={job} />
        </div>
      )}
    </main>
  );
}
