"use client";

// Environment doctor — moved here from "/" at task-13, once "/" became the
// real project library. Still useful for verifying the free stack is ready.
import { useEffect, useState } from "react";
import { getHealth, type HealthStatus } from "@/lib/api";

interface Check {
  label: string;
  ok: boolean;
  detail?: string;
}

function checksFromHealth(health: HealthStatus): Check[] {
  return [
    {
      label: "ffmpeg",
      ok: health.ffmpeg.present,
      detail: health.ffmpeg.version ?? "not found on PATH",
    },
    {
      label: "Subtitle filters (libass/HarfBuzz)",
      ok: health.subtitle_filters_available,
    },
    {
      label: "GPU worker (torch.cuda)",
      ok: health.cuda_available,
      detail: health.cuda_available ? undefined : "CPU-only — expected on the VM without the worker",
    },
    {
      label: "GEMINI_API_KEY",
      ok: health.keys_configured.gemini,
    },
    {
      label: "PEXELS_API_KEY",
      ok: health.keys_configured.pexels,
    },
    {
      label: "PIXABAY_API_KEY",
      ok: health.keys_configured.pixabay,
    },
    {
      label: `Database migrated (schema v${health.schema_version})`,
      ok: health.db_migrated,
    },
  ];
}

export default function SetupChecklistPage() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getHealth()
      .then((result) => {
        if (!cancelled) setHealth(result);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not reach the backend");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main style={{ maxWidth: 640, margin: "0 auto", padding: "4rem 1.5rem" }}>
      <h1 style={{ fontSize: "1.75rem", fontWeight: 600 }}>Environment doctor</h1>
      <p style={{ color: "var(--text-dim)", marginTop: "0.5rem" }}>
        Confirms the free stack is ready before you build anything on top of it.
      </p>

      {error && (
        <div
          style={{
            marginTop: "2rem",
            padding: "1rem",
            borderRadius: 8,
            border: "1px solid var(--border)",
            background: "var(--surface)",
          }}
        >
          <p style={{ color: "var(--bad)" }}>Backend unreachable: {error}</p>
          <p style={{ color: "var(--text-dim)", marginTop: "0.5rem" }}>
            Is `uvicorn app.main:app --reload` running in `backend/`?
          </p>
        </div>
      )}

      {!error && !health && (
        <p style={{ marginTop: "2rem", color: "var(--text-dim)" }}>Checking backend…</p>
      )}

      {health && (
        <ul
          style={{
            marginTop: "2rem",
            listStyle: "none",
            display: "flex",
            flexDirection: "column",
            gap: "0.5rem",
          }}
        >
          {checksFromHealth(health).map((check) => (
            <li
              key={check.label}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.75rem",
                padding: "0.75rem 1rem",
                borderRadius: 8,
                border: "1px solid var(--border)",
                background: "var(--surface)",
              }}
            >
              <span
                aria-hidden
                style={{
                  width: 10,
                  height: 10,
                  borderRadius: "50%",
                  background: check.ok ? "var(--ok)" : "var(--bad)",
                  flexShrink: 0,
                }}
              />
              <span style={{ flex: 1 }}>{check.label}</span>
              {check.detail && (
                <span style={{ color: "var(--text-dim)", fontSize: "0.85rem" }}>{check.detail}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
