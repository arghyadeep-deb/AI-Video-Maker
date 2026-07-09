"use client";

// Selfie upload + consent + persona + approval gate —
// specs/03-design/04-mode-a-pipeline.md, specs/01-requirements/04-mode-a-avatar.md.
import { useState } from "react";
import Link from "next/link";
import { useJob } from "@/hooks/useJob";
import {
  ApiRequestError,
  approveAvatar,
  avatarPortraitUrl,
  createAvatar,
  restyleAvatar,
  type Avatar,
} from "@/lib/api";

const PERSONA_PRESETS = [
  { label: "Astrologer", text: "Astrologer, saffron robes, mystical study with celestial charts behind you" },
  { label: "Businessman", text: "Successful businessman, sharp suit, modern office background" },
  { label: "Teacher", text: "Friendly teacher, smart casual attire, classroom with a whiteboard behind you" },
  { label: "Doctor", text: "Doctor, white coat with stethoscope, clean clinical background" },
  { label: "News Anchor", text: "News anchor, formal attire, news studio background" },
];

export default function AvatarSetup({ onApproved }: { onApproved?: (avatar: Avatar) => void }) {
  const [selfieFile, setSelfieFile] = useState<File | null>(null);
  const [selfiePreview, setSelfiePreview] = useState<string | null>(null);
  const [persona, setPersona] = useState("");
  const [name, setName] = useState("My Avatar");
  const [consent, setConsent] = useState(false);
  const [avatar, setAvatar] = useState<Avatar | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [regenerating, setRegenerating] = useState(false);

  const { job } = useJob(jobId);
  const styling = job !== null && job.status !== "awaiting_user" && job.status !== "failed";
  const readyForReview = job !== null && job.status === "awaiting_user";

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] ?? null;
    setSelfieFile(file);
    setSelfiePreview(file ? URL.createObjectURL(file) : null);
  }

  async function handleUpload() {
    if (!selfieFile || !consent || !persona.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const created = await createAvatar({
        selfie: selfieFile,
        persona_description: persona.trim(),
        name,
        consent,
      });
      setAvatar(created);
      setJobId(created.job_id);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.hint ?? err.message : "Failed to upload selfie");
    } finally {
      setBusy(false);
    }
  }

  async function handleApprove() {
    if (!avatar) return;
    setBusy(true);
    setError(null);
    try {
      const approved = await approveAvatar(avatar.id);
      setAvatar(approved);
      onApproved?.(approved);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.hint ?? err.message : "Failed to approve avatar");
    } finally {
      setBusy(false);
    }
  }

  async function handleRestyle(newPersona: string) {
    if (!avatar) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await restyleAvatar(avatar.id, newPersona);
      setAvatar(updated);
      setJobId(updated.job_id);
      setPersona(newPersona);
      setRegenerating(false);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.hint ?? err.message : "Failed to restyle avatar");
    } finally {
      setBusy(false);
    }
  }

  const canUpload = Boolean(selfieFile) && consent && persona.trim().length > 0 && !busy && !avatar;

  return (
    <div style={{ maxWidth: 480 }}>
      {!avatar && (
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          <div>
            <label style={{ display: "block", marginBottom: "0.5rem", color: "var(--text-dim)" }}>
              Selfie
            </label>
            {selfiePreview && (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={selfiePreview}
                alt="Selfie preview"
                style={{ width: 120, height: 120, objectFit: "cover", borderRadius: 8, marginBottom: "0.5rem" }}
              />
            )}
            <input type="file" accept="image/jpeg,image/png" onChange={handleFileChange} />
          </div>

          <div>
            <label style={{ display: "block", marginBottom: "0.5rem", color: "var(--text-dim)" }}>
              Avatar name
            </label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              style={{
                width: "100%",
                padding: "0.5rem",
                borderRadius: 6,
                border: "1px solid var(--border)",
                background: "var(--bg)",
                color: "var(--text)",
              }}
            />
          </div>

          <div>
            <label style={{ display: "block", marginBottom: "0.5rem", color: "var(--text-dim)" }}>
              Persona
            </label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem", marginBottom: "0.5rem" }}>
              {PERSONA_PRESETS.map((preset) => (
                <button
                  key={preset.label}
                  type="button"
                  onClick={() => setPersona(preset.text)}
                  style={{
                    padding: "0.3rem 0.7rem",
                    borderRadius: 999,
                    border: "1px solid var(--border)",
                    background: "var(--surface)",
                    color: "var(--text)",
                    fontSize: "0.8rem",
                    cursor: "pointer",
                  }}
                >
                  {preset.label}
                </button>
              ))}
            </div>
            <textarea
              value={persona}
              onChange={(e) => setPersona(e.target.value)}
              placeholder="Describe the persona (e.g. astrologer in saffron robes, mystical background)"
              rows={3}
              style={{
                width: "100%",
                padding: "0.5rem",
                borderRadius: 6,
                border: "1px solid var(--border)",
                background: "var(--bg)",
                color: "var(--text)",
              }}
            />
          </div>

          <label style={{ display: "flex", alignItems: "flex-start", gap: "0.5rem", fontSize: "0.85rem" }}>
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
              style={{ marginTop: "0.2rem" }}
            />
            <span>
              I confirm this is a photo of myself, and I consent to it being used to generate a
              styled avatar portrait for my own videos.{" "}
              <Link href="/responsible-use" style={{ color: "var(--accent)" }}>
                Responsible use
              </Link>
              .
            </span>
          </label>

          {error && <p style={{ color: "var(--bad)" }}>{error}</p>}

          <button
            type="button"
            disabled={!canUpload}
            onClick={handleUpload}
            style={{
              padding: "0.7rem 1.2rem",
              borderRadius: 8,
              border: "none",
              background: canUpload ? "var(--accent)" : "var(--border)",
              color: canUpload ? "#0b0c0f" : "var(--text-dim)",
              fontWeight: 600,
              cursor: canUpload ? "pointer" : "not-allowed",
            }}
          >
            {busy ? "Uploading…" : "Create avatar"}
          </button>
        </div>
      )}

      {avatar && (
        <div>
          {styling && <p style={{ color: "var(--text-dim)" }}>Styling your portrait…</p>}

          {job?.status === "failed" && (
            <p style={{ color: "var(--bad)" }}>{job.error ?? "Styling failed"}</p>
          )}

          {(readyForReview || avatar.approved) && (
            <div>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                // The portrait URL is stable across restyles (same avatar id)
                // but the file content changes - cache-bust with the job id
                // so a regenerated portrait doesn't show the browser's
                // cached copy of the previous attempt.
                src={`${avatarPortraitUrl(avatar.id)}?v=${jobId ?? "0"}`}
                alt="Styled portrait"
                crossOrigin="use-credentials"
                style={{ width: 240, height: 240, objectFit: "cover", borderRadius: 8 }}
              />
              {!avatar.approved && (
                <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem" }}>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={handleApprove}
                    style={{
                      padding: "0.6rem 1.2rem",
                      borderRadius: 6,
                      border: "none",
                      background: "var(--accent)",
                      color: "#0b0c0f",
                      fontWeight: 600,
                    }}
                  >
                    Approve
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => setRegenerating(true)}
                    style={{
                      padding: "0.6rem 1.2rem",
                      borderRadius: 6,
                      border: "1px solid var(--border)",
                      background: "transparent",
                      color: "var(--text)",
                    }}
                  >
                    Regenerate
                  </button>
                </div>
              )}
              {avatar.approved && <p style={{ color: "var(--ok)", marginTop: "0.75rem" }}>Approved ✓</p>}

              {regenerating && (
                <div style={{ marginTop: "1rem" }}>
                  <textarea
                    defaultValue={avatar.persona_description ?? ""}
                    onChange={(e) => setPersona(e.target.value)}
                    rows={3}
                    style={{
                      width: "100%",
                      padding: "0.5rem",
                      borderRadius: 6,
                      border: "1px solid var(--border)",
                      background: "var(--bg)",
                      color: "var(--text)",
                    }}
                  />
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => handleRestyle(persona)}
                    style={{
                      marginTop: "0.5rem",
                      padding: "0.5rem 1rem",
                      borderRadius: 6,
                      border: "none",
                      background: "var(--accent)",
                      color: "#0b0c0f",
                      fontWeight: 600,
                    }}
                  >
                    Regenerate with this persona
                  </button>
                </div>
              )}
            </div>
          )}

          {error && <p style={{ color: "var(--bad)", marginTop: "1rem" }}>{error}</p>}
        </div>
      )}
    </div>
  );
}
