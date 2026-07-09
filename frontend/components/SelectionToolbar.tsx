"use client";

import { useState } from "react";

// Rendered by SceneCard directly below its textarea whenever that card has
// a non-empty text selection. A plain <textarea> gives no pixel coordinates
// for an arbitrary text range (unlike contenteditable + Range), so this is
// an attached toolbar rather than a true floating-at-the-cursor button —
// functionally equivalent for the task's acceptance criteria, much less
// engineering than rebuilding the editor as contenteditable.
export default function SelectionToolbar({
  onSubmit,
  onCancel,
  busy,
}: {
  onSubmit: (instruction?: string) => void | Promise<void>;
  onCancel: () => void;
  busy: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [instruction, setInstruction] = useState("");

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        style={{
          marginTop: "0.4rem",
          padding: "0.3rem 0.7rem",
          borderRadius: 999,
          border: "1px solid var(--accent)",
          background: "transparent",
          color: "var(--accent)",
          fontSize: "0.8rem",
          cursor: "pointer",
        }}
      >
        ✨ Improve
      </button>
    );
  }

  return (
    <div
      style={{
        marginTop: "0.4rem",
        display: "flex",
        gap: "0.4rem",
        alignItems: "center",
      }}
    >
      <input
        autoFocus
        value={instruction}
        onChange={(e) => setInstruction(e.target.value)}
        placeholder="Optional instruction (e.g. make this funnier)"
        style={{
          flex: 1,
          padding: "0.3rem 0.5rem",
          borderRadius: 6,
          border: "1px solid var(--border)",
          background: "var(--bg)",
          color: "var(--text)",
          fontSize: "0.85rem",
        }}
      />
      <button
        type="button"
        disabled={busy}
        onClick={() => onSubmit(instruction.trim() || undefined)}
        style={{
          padding: "0.3rem 0.7rem",
          borderRadius: 6,
          border: "none",
          background: "var(--accent)",
          color: "#0b0c0f",
          fontWeight: 600,
          fontSize: "0.85rem",
          cursor: busy ? "not-allowed" : "pointer",
        }}
      >
        {busy ? "Improving…" : "Improve"}
      </button>
      <button
        type="button"
        disabled={busy}
        onClick={() => {
          setOpen(false);
          setInstruction("");
          onCancel();
        }}
        style={{
          padding: "0.3rem 0.6rem",
          borderRadius: 6,
          border: "1px solid var(--border)",
          background: "transparent",
          color: "var(--text-dim)",
          fontSize: "0.85rem",
          cursor: busy ? "not-allowed" : "pointer",
        }}
      >
        Cancel
      </button>
    </div>
  );
}
