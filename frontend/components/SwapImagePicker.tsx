"use client";

// Per-scene image swap — specs/04-tasks/task-17-post-render-tools.md.
// Shows the current image + cached alternates (task-08's own 5-candidate
// fetch, retrofitted to persist the losers - see image_service.py) plus a
// "generate new" option, gated by the same genai_image daily cap the
// normal sourcing fallback already respects.
import { useEffect, useState } from "react";
import {
  ApiRequestError,
  getSceneCandidates,
  sceneImageUrl,
  swapSceneImage,
  type Job,
  type SceneCandidates,
} from "@/lib/api";

export default function SwapImagePicker({
  projectId,
  sceneId,
  onClose,
  onJobStarted,
}: {
  projectId: string;
  sceneId: number;
  onClose: () => void;
  onJobStarted: (job: Job) => void;
}) {
  const [candidates, setCandidates] = useState<SceneCandidates | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getSceneCandidates(projectId, sceneId)
      .then((result) => {
        if (!cancelled) setCandidates(result);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof ApiRequestError ? err.hint ?? err.message : "Failed to load candidates");
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, sceneId]);

  async function pick(input: { source_id?: string; generate_new?: boolean }) {
    setBusy(true);
    setError(null);
    try {
      const job = await swapSceneImage(projectId, sceneId, input);
      onJobStarted(job);
      onClose();
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.hint ?? err.message : "Failed to swap image");
      setBusy(false);
    }
  }

  return (
    <div
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)",
        display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12,
          padding: "1.5rem", maxWidth: 480, width: "90%", maxHeight: "80vh", overflowY: "auto",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 style={{ fontSize: "1.05rem", fontWeight: 600, marginBottom: "1rem" }}>Swap scene image</h3>

        {error && <p style={{ color: "var(--bad)", marginBottom: "1rem" }}>{error}</p>}

        {!candidates ? (
          <p style={{ color: "var(--text-dim)" }}>Loading…</p>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "0.75rem" }}>
            <button
              type="button"
              disabled={busy}
              style={{
                border: "2px solid var(--accent)", borderRadius: 8, padding: 0, cursor: "default", background: "none",
              }}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={sceneImageUrl(projectId, sceneId)}
                alt="Current"
                crossOrigin="use-credentials"
                style={{ width: "100%", aspectRatio: "9 / 16", objectFit: "cover", borderRadius: 6 }}
              />
              <p style={{ fontSize: "0.7rem", color: "var(--text-dim)", padding: "0.25rem" }}>Current</p>
            </button>

            {candidates.alternates.map((alt) => (
              <button
                key={alt.source_id}
                type="button"
                disabled={busy}
                onClick={() => pick({ source_id: alt.source_id })}
                style={{
                  border: "1px solid var(--border)", borderRadius: 8, padding: 0,
                  cursor: busy ? "not-allowed" : "pointer", background: "none",
                }}
              >
                {alt.url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={alt.url}
                    alt={alt.photographer ?? "Alternate"}
                    style={{ width: "100%", aspectRatio: "9 / 16", objectFit: "cover", borderRadius: 6 }}
                  />
                ) : (
                  <div
                    style={{
                      width: "100%", aspectRatio: "9 / 16", borderRadius: 6,
                      background: "var(--bg)", display: "flex", alignItems: "center", justifyContent: "center",
                    }}
                  >
                    <span style={{ fontSize: "0.7rem", color: "var(--text-dim)" }}>{alt.source}</span>
                  </div>
                )}
                <p style={{ fontSize: "0.7rem", color: "var(--text-dim)", padding: "0.25rem" }}>
                  {alt.photographer ?? alt.source}
                </p>
              </button>
            ))}

            {candidates.can_generate_new && (
              <button
                type="button"
                disabled={busy}
                onClick={() => pick({ generate_new: true })}
                style={{
                  border: "1px dashed var(--border)", borderRadius: 8,
                  aspectRatio: "9 / 16", display: "flex", alignItems: "center", justifyContent: "center",
                  cursor: busy ? "not-allowed" : "pointer", background: "none", color: "var(--text)",
                }}
              >
                Generate new
              </button>
            )}
          </div>
        )}

        <button
          type="button"
          onClick={onClose}
          style={{
            marginTop: "1.25rem", padding: "0.5rem 1rem", borderRadius: 6,
            border: "1px solid var(--border)", background: "transparent", color: "var(--text)", cursor: "pointer",
          }}
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
