"use client";

// Voice enrollment: passage -> record (MediaRecorder + level meter) ->
// consent -> upload -> preview-in-your-own-voice —
// specs/04-tasks/task-18-voice-cloning-voxcpm.md.
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  ApiRequestError,
  deleteVoiceProfile,
  enrollVoice,
  getVoicePassage,
  listVoiceProfiles,
  voicePreviewUrlForProfile,
  type VoiceProfile,
} from "@/lib/api";

export default function VoiceEnrollment({ language }: { language: string }) {
  const [passage, setPassage] = useState<string | null>(null);
  const [profile, setProfile] = useState<VoiceProfile | null>(null);
  const [profileChecked, setProfileChecked] = useState(false);
  const [recording, setRecording] = useState(false);
  const [recordedBlob, setRecordedBlob] = useState<Blob | null>(null);
  const [level, setLevel] = useState(0);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const audioContextRef = useRef<AudioContext | null>(null);
  const animationFrameRef = useRef<number | null>(null);

  useEffect(() => {
    getVoicePassage(language)
      .then((result) => setPassage(result.text))
      .catch(() => setPassage(null));
    listVoiceProfiles()
      .then((profiles) => {
        setProfile(profiles.find((p) => p.kind === "cloned") ?? null);
        setProfileChecked(true);
      })
      .catch(() => setProfileChecked(true));
  }, [language]);

  async function startRecording() {
    setError(null);
    setRecordedBlob(null);
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const recorder = new MediaRecorder(stream);
    chunksRef.current = [];
    recorder.ondataavailable = (e) => chunksRef.current.push(e.data);
    recorder.onstop = () => {
      setRecordedBlob(new Blob(chunksRef.current, { type: "audio/webm" }));
      stream.getTracks().forEach((track) => track.stop());
    };
    mediaRecorderRef.current = recorder;
    recorder.start();
    setRecording(true);

    const audioContext = new AudioContext();
    audioContextRef.current = audioContext;
    const source = audioContext.createMediaStreamSource(stream);
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);
    const data = new Uint8Array(analyser.frequencyBinCount);

    function tick() {
      analyser.getByteFrequencyData(data);
      const avg = data.reduce((sum, v) => sum + v, 0) / data.length;
      setLevel(avg / 255);
      animationFrameRef.current = requestAnimationFrame(tick);
    }
    tick();
  }

  function stopRecording() {
    mediaRecorderRef.current?.stop();
    setRecording(false);
    if (animationFrameRef.current) cancelAnimationFrame(animationFrameRef.current);
    audioContextRef.current?.close();
    setLevel(0);
  }

  async function handleUpload() {
    if (!recordedBlob || !consent) return;
    setBusy(true);
    setError(null);
    try {
      const created = await enrollVoice({ sample: recordedBlob, language, consent });
      setProfile(created);
      setRecordedBlob(null);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.hint ?? err.message : "Failed to enroll your voice");
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (!profile) return;
    setBusy(true);
    try {
      await deleteVoiceProfile(profile.id);
      setProfile(null);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.hint ?? err.message : "Failed to delete voice profile");
    } finally {
      setBusy(false);
    }
  }

  if (!profileChecked) {
    return <p style={{ color: "var(--text-dim)" }}>Loading…</p>;
  }

  if (profile) {
    return (
      <div style={{ maxWidth: 480 }}>
        <p style={{ color: "var(--ok)", marginBottom: "0.75rem" }}>
          Your voice is enrolled ✓ every render will default to it.
        </p>
        <audio controls src={voicePreviewUrlForProfile(profile.id)} style={{ width: "100%", marginBottom: "0.75rem" }} />
        {error && <p style={{ color: "var(--bad)", marginBottom: "0.5rem" }}>{error}</p>}
        <button
          type="button"
          disabled={busy}
          onClick={handleDelete}
          style={{
            padding: "0.5rem 1rem", borderRadius: 6, border: "1px solid var(--bad)",
            background: "transparent", color: "var(--bad)", cursor: busy ? "not-allowed" : "pointer",
          }}
        >
          Delete and re-record
        </button>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 480 }}>
      <p style={{ color: "var(--text-dim)", marginBottom: "0.75rem" }}>
        Record 30–45 seconds reading the passage below. This becomes your personal voice - every
        video will be narrated in it by default.
      </p>

      {passage && (
        <div
          style={{
            padding: "1rem", borderRadius: 8, border: "1px solid var(--border)",
            background: "var(--surface)", marginBottom: "1rem", lineHeight: 1.6,
          }}
        >
          {passage}
        </div>
      )}

      {!recordedBlob && (
        <button
          type="button"
          onClick={recording ? stopRecording : startRecording}
          style={{
            padding: "0.7rem 1.2rem", borderRadius: 8, border: "none",
            background: recording ? "var(--bad)" : "var(--accent)",
            color: recording ? "#fff" : "#0b0c0f", fontWeight: 600, cursor: "pointer",
          }}
        >
          {recording ? "Stop recording" : "Start recording"}
        </button>
      )}

      {recording && (
        <div
          style={{
            marginTop: "0.75rem", height: 8, borderRadius: 4, background: "var(--bg)",
            border: "1px solid var(--border)", overflow: "hidden",
          }}
        >
          <div
            style={{
              height: "100%", width: `${Math.min(100, level * 100)}%`,
              background: "var(--accent)", transition: "width 0.05s linear",
            }}
          />
        </div>
      )}

      {recordedBlob && (
        <div style={{ marginTop: "1rem" }}>
          <audio controls src={URL.createObjectURL(recordedBlob)} style={{ width: "100%", marginBottom: "0.75rem" }} />

          <label style={{ display: "flex", alignItems: "flex-start", gap: "0.5rem", fontSize: "0.85rem", marginBottom: "0.75rem" }}>
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
              style={{ marginTop: "0.2rem" }}
            />
            <span>
              I confirm this is my own voice, and I consent to it being used to narrate my videos.{" "}
              <Link href="/responsible-use" style={{ color: "var(--accent)" }}>
                Responsible use
              </Link>
              .
            </span>
          </label>

          {error && <p style={{ color: "var(--bad)", marginBottom: "0.75rem" }}>{error}</p>}

          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button
              type="button"
              disabled={!consent || busy}
              onClick={handleUpload}
              style={{
                padding: "0.6rem 1.2rem", borderRadius: 6, border: "none",
                background: consent ? "var(--accent)" : "var(--border)",
                color: consent ? "#0b0c0f" : "var(--text-dim)", fontWeight: 600,
                cursor: consent && !busy ? "pointer" : "not-allowed",
              }}
            >
              {busy ? "Uploading…" : "Use this recording"}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => setRecordedBlob(null)}
              style={{
                padding: "0.6rem 1.2rem", borderRadius: 6, border: "1px solid var(--border)",
                background: "transparent", color: "var(--text)", cursor: "pointer",
              }}
            >
              Re-record
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
