"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ApiRequestError,
  createProject,
  generateScript,
  type DurationS,
  type Language,
  type VideoFormat,
} from "@/lib/api";

const DURATION_PRESETS: { value: DurationS; label: string }[] = [
  { value: 30, label: "30s" },
  { value: 60, label: "1 min" },
  { value: 120, label: "2 min" },
  { value: 300, label: "5 min" },
];

const FORMATS: { value: VideoFormat; label: string }[] = [
  { value: "9x16", label: "9:16 (Reels)" },
  { value: "16x9", label: "16:9 (Widescreen)" },
];

const segmentedStyle = (active: boolean): React.CSSProperties => ({
  padding: "0.5rem 1rem",
  borderRadius: 8,
  border: `1px solid ${active ? "var(--accent)" : "var(--border)"}`,
  background: active ? "var(--accent)" : "var(--surface)",
  color: active ? "#0b0c0f" : "var(--text)",
  fontWeight: active ? 600 : 400,
  cursor: "pointer",
});

export default function CreatePage() {
  return (
    <Suspense fallback={null}>
      <CreateForm />
    </Suspense>
  );
}

function CreateForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [description, setDescription] = useState(searchParams.get("description") ?? "");
  const [language, setLanguage] = useState<Language>("hi");
  const [duration, setDuration] = useState<DurationS>(60);
  const [format, setFormat] = useState<VideoFormat>("9x16");
  const [status, setStatus] = useState<"idle" | "generating" | "error">("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const canSubmit = description.trim().length > 0 && status !== "generating";

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;

    setStatus("generating");
    setErrorMessage(null);
    try {
      const project = await createProject({
        description: description.trim(),
        language,
        duration_s: duration,
        format,
      });
      await generateScript(project.id);
      router.push(`/project/${project.id}/script`);
    } catch (err) {
      setStatus("error");
      if (err instanceof ApiRequestError) {
        setErrorMessage(err.hint ?? err.message);
      } else {
        setErrorMessage("Something went wrong talking to the backend.");
      }
    }
  }

  return (
    <main style={{ maxWidth: 640, margin: "0 auto", padding: "4rem 1.5rem" }}>
      <h1 style={{ fontSize: "1.75rem", fontWeight: 600 }}>Describe your video</h1>
      <p style={{ color: "var(--text-dim)", marginTop: "0.5rem" }}>
        A rough idea is enough — tone and structure are inferred from it.
      </p>

      <form
        onSubmit={handleSubmit}
        style={{ marginTop: "2rem", display: "flex", flexDirection: "column", gap: "1.5rem" }}
      >
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Describe the video you want…"
          rows={5}
          style={{
            width: "100%",
            padding: "1rem",
            borderRadius: 8,
            border: "1px solid var(--border)",
            background: "var(--surface)",
            color: "var(--text)",
            fontSize: "1rem",
            resize: "vertical",
          }}
        />

        <div>
          <label style={{ display: "block", marginBottom: "0.5rem", color: "var(--text-dim)" }}>
            Language
          </label>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button type="button" style={segmentedStyle(language === "hi")} onClick={() => setLanguage("hi")}>
              हिन्दी
            </button>
            <button type="button" style={segmentedStyle(language === "en")} onClick={() => setLanguage("en")}>
              English
            </button>
          </div>
        </div>

        <div>
          <label style={{ display: "block", marginBottom: "0.5rem", color: "var(--text-dim)" }}>
            Duration
          </label>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            {DURATION_PRESETS.map((preset) => (
              <button
                key={preset.value}
                type="button"
                style={segmentedStyle(duration === preset.value)}
                onClick={() => setDuration(preset.value)}
              >
                {preset.label}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label style={{ display: "block", marginBottom: "0.5rem", color: "var(--text-dim)" }}>
            Format
          </label>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            {FORMATS.map((f) => (
              <button
                key={f.value}
                type="button"
                style={segmentedStyle(format === f.value)}
                onClick={() => setFormat(f.value)}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        {status === "error" && errorMessage && (
          <p style={{ color: "var(--bad)" }}>{errorMessage}</p>
        )}

        <button
          type="submit"
          disabled={!canSubmit}
          style={{
            padding: "0.85rem",
            borderRadius: 8,
            border: "none",
            background: canSubmit ? "var(--accent)" : "var(--border)",
            color: canSubmit ? "#0b0c0f" : "var(--text-dim)",
            fontWeight: 600,
            fontSize: "1rem",
            cursor: canSubmit ? "pointer" : "not-allowed",
          }}
        >
          {status === "generating" ? "Writing your script…" : "Generate script"}
        </button>
      </form>
    </main>
  );
}
