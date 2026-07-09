"use client";

import { useState } from "react";
import { utf16OffsetToCodepointOffset, type Language, type Scene } from "@/lib/api";
import SelectionToolbar from "./SelectionToolbar";

const WORDS_PER_MINUTE: Record<Language, number> = { hi: 120, en: 140 };

function sceneSeconds(text: string, language: Language): number {
  const wordCount = text.trim().split(/\s+/).filter(Boolean).length;
  return (wordCount / WORDS_PER_MINUTE[language]) * 60;
}

// Caller must render this with `key={`${scene.id}:${scene.text}`}` so that
// when the authoritative text changes out from under us (another scene's
// save triggered a version bump that also refreshed this one, or a
// restore), React remounts with a fresh initial value instead of us
// needing an effect to resync local state from a prop change.
export default function SceneCard({
  scene,
  language,
  disabled,
  onSave,
  onImprove,
}: {
  scene: Scene;
  language: Language;
  disabled: boolean;
  onSave: (sceneId: number, text: string) => void | Promise<void>;
  onImprove: (sceneId: number, start: number, end: number, instruction?: string) => void | Promise<void>;
}) {
  const [text, setText] = useState(scene.text);
  const [selection, setSelection] = useState<{ start: number; end: number } | null>(null);
  const [improving, setImproving] = useState(false);

  const seconds = sceneSeconds(text, language);
  const dirty = text !== scene.text;

  function handleSelect(e: React.SyntheticEvent<HTMLTextAreaElement>) {
    const el = e.currentTarget;
    // A textarea's selection can never span more than one scene card - each
    // card is its own DOM element, so cross-scene selection is impossible
    // by construction (no extra suppression logic needed).
    if (el.selectionStart !== el.selectionEnd) {
      setSelection({ start: el.selectionStart, end: el.selectionEnd });
    } else {
      setSelection(null);
    }
  }

  async function handleImproveSubmit(instruction?: string) {
    if (!selection) return;
    setImproving(true);
    try {
      const start = utf16OffsetToCodepointOffset(text, selection.start);
      const end = utf16OffsetToCodepointOffset(text, selection.end);
      await onImprove(scene.id, start, end, instruction);
      setSelection(null);
    } finally {
      setImproving(false);
    }
  }

  return (
    <div
      style={{
        padding: "1rem",
        borderRadius: 8,
        border: "1px solid var(--border)",
        background: "var(--surface)",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          color: "var(--text-dim)",
          fontSize: "0.8rem",
          marginBottom: "0.5rem",
        }}
      >
        <span>
          Scene {scene.id} · {scene.visual_hint}
          {scene.visual_hint_stale && " (stale)"}
        </span>
        <span>~{seconds.toFixed(0)}s</span>
      </div>
      <textarea
        lang={language}
        value={text}
        disabled={disabled}
        onChange={(e) => setText(e.target.value)}
        onSelect={handleSelect}
        onBlur={() => {
          if (dirty) onSave(scene.id, text);
        }}
        rows={3}
        style={{
          width: "100%",
          padding: "0.5rem",
          borderRadius: 6,
          border: "1px solid var(--border)",
          background: disabled ? "transparent" : "var(--bg)",
          color: "var(--text)",
          fontSize: "1.05rem",
          lineHeight: 1.6,
          resize: "vertical",
        }}
      />
      {selection && !disabled && (
        <SelectionToolbar
          busy={improving}
          onSubmit={handleImproveSubmit}
          onCancel={() => setSelection(null)}
        />
      )}
    </div>
  );
}
