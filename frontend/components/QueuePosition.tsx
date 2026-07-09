"use client";

// "N jobs ahead of you" — specs/03-design/10-frontend-pages.md's result
// page: "While queued: queue position". Purely presentational - the
// useJob poll already refreshes the underlying Job (including
// queue_position) every 1.5s.
import type { Job } from "@/lib/api";

export default function QueuePosition({ job }: { job: Job }) {
  if (job.status !== "queued" || job.queue_position === null) return null;

  const label =
    job.queue_position === 0
      ? "Next in line"
      : `${job.queue_position} job${job.queue_position === 1 ? "" : "s"} ahead of you`;

  return <p style={{ color: "var(--text-dim)", fontSize: "0.9rem" }}>{label}</p>;
}
