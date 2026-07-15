"use client";

import { useEffect, useState } from "react";
import { getJob, type Job, type JobStatus } from "@/lib/api";

const POLL_INTERVAL_MS = 1500;
const TERMINAL_STATUSES: JobStatus[] = ["done", "failed", "cancelled"];

// Polls GET /api/jobs/{id} every 1.5s while mounted; stops automatically
// once the job reaches a terminal status (done/failed/cancelled) - per
// specs/03-design/07-job-queue-and-progress.md.
export function useJob(jobId: string | null) {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!jobId) {
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    function poll() {
      getJob(jobId as string)
        .then((result) => {
          if (cancelled) return;
          setJob(result);
          setError(null);
          if (!TERMINAL_STATUSES.includes(result.status)) {
            timer = setTimeout(poll, POLL_INTERVAL_MS);
          }
        })
        .catch(() => {
          if (cancelled) return;
          // A single dropped request (network blip, a slow server under
          // load) must not permanently freeze the progress display - the
          // render itself keeps going server-side regardless. Keep polling
          // and only show a soft, non-alarming notice, never the raw
          // browser error ("Failed to fetch" etc.) which reads as broken.
          setError("Reconnecting…");
          timer = setTimeout(poll, POLL_INTERVAL_MS);
        });
    }

    poll();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [jobId]);

  return { job, error };
}
