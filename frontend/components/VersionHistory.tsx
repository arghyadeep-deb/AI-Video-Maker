"use client";

import { useState } from "react";
import type { ScriptVersionSummary } from "@/lib/api";

const ORIGIN_LABEL: Record<string, string> = {
  generated: "Generated",
  improved: "AI improved",
  edited: "Edited",
};

export default function VersionHistory({
  versions,
  onRestore,
}: {
  versions: ScriptVersionSummary[];
  onRestore: (versionId: string) => void | Promise<void>;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div style={{ position: "relative" }}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        style={{
          padding: "0.4rem 0.75rem",
          borderRadius: 6,
          border: "1px solid var(--border)",
          background: "var(--surface)",
          color: "var(--text)",
          cursor: "pointer",
          fontSize: "0.85rem",
        }}
      >
        History ({versions.length}) ▾
      </button>
      {open && (
        <div
          style={{
            position: "absolute",
            top: "calc(100% + 0.5rem)",
            right: 0,
            zIndex: 10,
            minWidth: 240,
            borderRadius: 8,
            border: "1px solid var(--border)",
            background: "var(--surface)",
            boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
            overflow: "hidden",
          }}
        >
          {versions.map((v, i) => (
            <button
              key={v.id}
              type="button"
              onClick={() => {
                setOpen(false);
                onRestore(v.id);
              }}
              style={{
                display: "flex",
                justifyContent: "space-between",
                width: "100%",
                padding: "0.6rem 0.9rem",
                border: "none",
                borderBottom: i < versions.length - 1 ? "1px solid var(--border)" : "none",
                background: "transparent",
                color: "var(--text)",
                cursor: "pointer",
                textAlign: "left",
                fontSize: "0.85rem",
              }}
            >
              <span>v{v.n} · {ORIGIN_LABEL[v.origin] ?? v.origin}</span>
              <span style={{ color: "var(--text-dim)" }}>Restore</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
