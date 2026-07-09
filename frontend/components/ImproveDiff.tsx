"use client";

import type { Language } from "@/lib/api";

export default function ImproveDiff({
  oldSpan,
  newSpan,
  language,
  busy,
  onKeep,
  onRevert,
}: {
  oldSpan: string;
  newSpan: string;
  language: Language;
  busy: boolean;
  onKeep: () => void | Promise<void>;
  onRevert: () => void;
}) {
  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.6)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 30,
      }}
    >
      <div
        style={{
          padding: "1.5rem",
          borderRadius: 8,
          border: "1px solid var(--border)",
          background: "var(--surface)",
          maxWidth: 480,
          width: "90%",
        }}
      >
        <p style={{ color: "var(--text-dim)", fontSize: "0.85rem", marginBottom: "0.75rem" }}>
          AI proposal — keep it or revert to leave your script untouched.
        </p>
        <p
          lang={language}
          style={{
            textDecoration: "line-through",
            color: "var(--bad)",
            lineHeight: 1.6,
            marginBottom: "0.5rem",
          }}
        >
          {oldSpan}
        </p>
        <p lang={language} style={{ color: "var(--ok)", lineHeight: 1.6 }}>
          {newSpan}
        </p>
        <div style={{ display: "flex", gap: "0.5rem", marginTop: "1.25rem", justifyContent: "flex-end" }}>
          <button
            type="button"
            disabled={busy}
            onClick={onRevert}
            style={{
              padding: "0.5rem 1rem",
              borderRadius: 6,
              border: "1px solid var(--border)",
              background: "transparent",
              color: "var(--text)",
              cursor: busy ? "not-allowed" : "pointer",
            }}
          >
            Revert
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={onKeep}
            style={{
              padding: "0.5rem 1rem",
              borderRadius: 6,
              border: "none",
              background: "var(--accent)",
              color: "#0b0c0f",
              fontWeight: 600,
              cursor: busy ? "not-allowed" : "pointer",
            }}
          >
            {busy ? "Keeping…" : "Keep"}
          </button>
        </div>
      </div>
    </div>
  );
}
