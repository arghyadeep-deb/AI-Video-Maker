"use client";

// Reusable confirm dialog for destructive actions (project/avatar delete).
export default function DeleteConfirm({
  title,
  message,
  busy,
  onConfirm,
  onCancel,
}: {
  title: string;
  message: string;
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.6)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 50,
      }}
    >
      <div
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: 8,
          padding: "1.5rem",
          maxWidth: 360,
          width: "90%",
        }}
      >
        <h2 style={{ fontSize: "1.05rem", fontWeight: 600 }}>{title}</h2>
        <p style={{ color: "var(--text-dim)", fontSize: "0.9rem", marginTop: "0.5rem" }}>{message}</p>
        <div style={{ display: "flex", gap: "0.5rem", marginTop: "1.25rem", justifyContent: "flex-end" }}>
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            style={{
              padding: "0.5rem 1rem",
              borderRadius: 6,
              border: "1px solid var(--border)",
              background: "transparent",
              color: "var(--text)",
              cursor: "pointer",
            }}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            style={{
              padding: "0.5rem 1rem",
              borderRadius: 6,
              border: "none",
              background: "var(--bad)",
              color: "#fff",
              fontWeight: 600,
              cursor: busy ? "not-allowed" : "pointer",
            }}
          >
            {busy ? "Deleting…" : "Delete"}
          </button>
        </div>
      </div>
    </div>
  );
}
