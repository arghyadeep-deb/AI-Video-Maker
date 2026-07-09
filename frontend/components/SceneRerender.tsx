"use client";

// Per-scene re-render (re-TTS + re-source + reassemble) —
// specs/04-tasks/task-17-post-render-tools.md.
import { useState } from "react";
import { ApiRequestError, rerenderScene, type Job, type VoiceTable } from "@/lib/api";

export default function SceneRerender({
  projectId,
  sceneId,
  language,
  voices,
  onJobStarted,
}: {
  projectId: string;
  sceneId: number;
  language: string;
  voices: VoiceTable;
  onJobStarted: (job: Job) => void;
}) {
  const [open, setOpen] = useState(false);
  const [voice, setVoice] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const languageVoices = voices[language] ?? {};

  async function handleRerender() {
    setBusy(true);
    setError(null);
    try {
      const job = await rerenderScene(projectId, sceneId, { voice: voice || undefined });
      onJobStarted(job);
      setOpen(false);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.hint ?? err.message : "Failed to re-render scene");
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        style={{
          fontSize: "0.75rem", padding: "0.3rem 0.6rem", borderRadius: 6,
          border: "1px solid var(--border)", background: "transparent", color: "var(--text-dim)", cursor: "pointer",
        }}
      >
        Re-render scene
      </button>
    );
  }

  return (
    <div
      style={{
        marginTop: "0.5rem", padding: "0.75rem", borderRadius: 8,
        border: "1px solid var(--border)", background: "var(--surface)",
      }}
    >
      <p style={{ fontSize: "0.8rem", color: "var(--text-dim)", marginBottom: "0.5rem" }}>
        Re-generates this scene&apos;s narration and image, then reassembles the video.
      </p>
      {Object.keys(languageVoices).length > 0 && (
        <select
          value={voice}
          onChange={(e) => setVoice(e.target.value)}
          style={{
            marginBottom: "0.5rem", padding: "0.4rem", borderRadius: 6,
            border: "1px solid var(--border)", background: "var(--bg)", color: "var(--text)",
          }}
        >
          <option value="">Keep current voice</option>
          {Object.entries(languageVoices).map(([gender, voiceId]) => (
            <option key={voiceId} value={voiceId}>
              {gender}
            </option>
          ))}
        </select>
      )}
      {error && <p style={{ color: "var(--bad)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{error}</p>}
      <div style={{ display: "flex", gap: "0.5rem" }}>
        <button
          type="button"
          disabled={busy}
          onClick={handleRerender}
          style={{
            padding: "0.4rem 0.85rem", borderRadius: 6, border: "none",
            background: "var(--accent)", color: "#0b0c0f", fontWeight: 600,
            cursor: busy ? "not-allowed" : "pointer", fontSize: "0.8rem",
          }}
        >
          {busy ? "Starting…" : "Re-render"}
        </button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          style={{
            padding: "0.4rem 0.85rem", borderRadius: 6, border: "1px solid var(--border)",
            background: "transparent", color: "var(--text)", cursor: "pointer", fontSize: "0.8rem",
          }}
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
