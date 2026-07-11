"use client";

// Mode select + voice setup — specs/03-design/10-frontend-pages.md,
// specs/03-design/04-mode-a-pipeline.md. Mode B stays the default-highlighted
// mode (R3's own mitigation text: "100% CPU-safe... deliberately the
// default-highlighted mode"); Mode A is available once an approved avatar
// exists and the script is <=2 minutes.
//
// HD avatars (task-20a): there is still no user-facing HD toggle - the
// server decides at render time (hd_requested=null => SadTalker HD by
// default while the home GPU worker is online, Wav2Lip otherwise), which
// is honest without asking the user to reason about GPU availability.
// The TierBadge reflects what's live; Mode B's footage level below is the
// one explicit quality choice users actually control.
//
// Personal voice enrollment (task-18): every render now defaults to the
// user's enrolled voice via make_narration_engine on the backend; stock
// voice only ever narrates when nothing's enrolled or conversion fails
// (an explicit notice either way, per the hard invariant).
import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import TierBadge from "@/components/TierBadge";
import VoiceEnrollment from "@/components/VoiceEnrollment";
import {
  ApiRequestError,
  avatarPortraitUrl,
  createRenderJob,
  getMusicMoods,
  getProject,
  getTierState,
  getVoices,
  listApprovedAvatars,
  listVoiceProfiles,
  musicPreviewUrl,
  voicePreviewUrl,
  type Avatar,
  type MusicMood,
  type Project,
  type SubtitleStyle,
  type TierState,
  type VoiceTable,
} from "@/lib/api";

const MOOD_LABELS: Record<MusicMood, string> = {
  calm: "Calm",
  upbeat: "Upbeat",
  mystical: "Mystical",
  corporate: "Corporate",
};

const MODE_A_MAX_DURATION_S = 120;

export default function GeneratePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const [project, setProject] = useState<Project | null>(null);
  const [voices, setVoices] = useState<VoiceTable | null>(null);
  const [avatars, setAvatars] = useState<Avatar[]>([]);
  const [selectedVoice, setSelectedVoice] = useState<string | null>(null);
  const [mode, setMode] = useState<"a" | "b">("b");
  const [selectedAvatarId, setSelectedAvatarId] = useState<string | null>(null);
  const [subtitlesOn, setSubtitlesOn] = useState(true);
  const [subtitleStyle, setSubtitleStyle] = useState<SubtitleStyle>("phrase");
  const [musicMoods, setMusicMoods] = useState<MusicMood[]>([]);
  const [musicEnabled, setMusicEnabled] = useState(false);
  const [musicMood, setMusicMood] = useState<MusicMood | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [hasEnrolledVoice, setHasEnrolledVoice] = useState<boolean | null>(null);
  const [manageVoiceOpen, setManageVoiceOpen] = useState(false);
  // Generated footage (task-20a): only offered while the home GPU worker
  // is online AND its scene_gen engine actually loaded - the toggle is
  // gated on live tier state, never a checkbox that silently does nothing.
  const [tier, setTier] = useState<TierState | null>(null);
  const [visualLevel, setVisualLevel] = useState<"photo" | "footage">("photo");

  useEffect(() => {
    let cancelled = false;
    Promise.all([getProject(id), getVoices(), listApprovedAvatars(), getMusicMoods(), listVoiceProfiles()])
      .then(([proj, voiceTable, avatarList, moods, voiceProfiles]) => {
        if (cancelled) return;
        setProject(proj);
        setVoices(voiceTable);
        setAvatars(avatarList);
        setMusicMoods(moods);
        setHasEnrolledVoice(voiceProfiles.some((p) => p.kind === "cloned"));
        if (moods.length > 0) setMusicMood(moods[0]);
        const defaultVoice = voiceTable[proj.language]?.female;
        if (defaultVoice) setSelectedVoice(defaultVoice);
        if (avatarList.length > 0) setSelectedAvatarId(avatarList[0].id);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof ApiRequestError ? err.hint ?? err.message : "Failed to load project");
      });
    getTierState()
      .then((state) => {
        if (!cancelled) {
          setTier(state);
          // The worker went offline since the page loaded? Never leave a
          // stale "footage" selection that the API would reject.
          if (!state.worker_capabilities.includes("scene_gen")) setVisualLevel("photo");
        }
      })
      .catch(() => {
        // Best-effort: without tier state the footage option just stays off.
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  const modeATooLong = (project?.duration_s ?? 0) > MODE_A_MAX_DURATION_S;
  const modeADisabled = modeATooLong || avatars.length === 0;
  const footageAvailable = tier?.worker_capabilities.includes("scene_gen") ?? false;

  async function handleGenerate() {
    if (!project) return;
    if (mode === "a" && !selectedAvatarId) {
      setError("Pick an avatar first");
      return;
    }
    setGenerating(true);
    setError(null);
    try {
      const job = await createRenderJob(project.id, {
        mode,
        avatar_id: mode === "a" ? selectedAvatarId ?? undefined : undefined,
        voice_profile_id: selectedVoice ?? undefined,
        subtitles: mode === "a" ? subtitlesOn : true,
        subtitle_style: subtitleStyle,
        visual_level: mode === "b" ? visualLevel : undefined,
        music_enabled: musicEnabled,
        music_mood: musicEnabled ? musicMood ?? undefined : undefined,
      });
      router.push(`/project/${project.id}/result?job=${job.id}`);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.hint ?? err.message : "Failed to start generation");
      setGenerating(false);
    }
  }

  if (error && !project) {
    return (
      <main style={{ maxWidth: 640, margin: "0 auto", padding: "4rem 1.5rem" }}>
        <p style={{ color: "var(--bad)" }}>{error}</p>
      </main>
    );
  }

  if (!project || !voices) {
    return (
      <main style={{ maxWidth: 640, margin: "0 auto", padding: "4rem 1.5rem" }}>
        <p style={{ color: "var(--text-dim)" }}>Loading…</p>
      </main>
    );
  }

  const languageVoices = voices[project.language] ?? {};

  return (
    <main style={{ maxWidth: 640, margin: "0 auto", padding: "4rem 1.5rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 600 }}>{project.title ?? "Untitled"}</h1>
        <TierBadge />
      </div>
      <p style={{ color: "var(--text-dim)", marginTop: "0.5rem" }}>
        Script accepted. Choose how to bring it to life.
      </p>

      <div style={{ display: "flex", gap: "1rem", marginTop: "2rem" }}>
        <button
          type="button"
          disabled={modeADisabled}
          onClick={() => setMode("a")}
          style={{
            flex: 1,
            textAlign: "left",
            padding: "1.25rem",
            borderRadius: 8,
            border: `1px solid ${mode === "a" ? "var(--accent)" : "var(--border)"}`,
            background: mode === "a" ? "var(--surface)" : "transparent",
            opacity: modeADisabled ? 0.5 : 1,
            cursor: modeADisabled ? "not-allowed" : "pointer",
          }}
        >
          <h2 style={{ fontSize: "1.05rem", fontWeight: 600 }}>My Avatar</h2>
          <p style={{ color: "var(--text-dim)", fontSize: "0.85rem", marginTop: "0.4rem" }}>
            {modeATooLong
              ? "Avatar videos are limited to 2 minutes - this script is longer."
              : avatars.length === 0
                ? "Create and approve an avatar first."
                : "A talking avatar built from your selfie."}
          </p>
        </button>
        <button
          type="button"
          onClick={() => setMode("b")}
          style={{
            flex: 1,
            textAlign: "left",
            padding: "1.25rem",
            borderRadius: 8,
            border: `1px solid ${mode === "b" ? "var(--accent)" : "var(--border)"}`,
            background: mode === "b" ? "var(--surface)" : "transparent",
            cursor: "pointer",
          }}
        >
          <h2 style={{ fontSize: "1.05rem", fontWeight: 600 }}>Image Video</h2>
          <p style={{ color: "var(--text-dim)", fontSize: "0.85rem", marginTop: "0.4rem" }}>
            Topic-relevant images with narration, music, and subtitles.
          </p>
        </button>
      </div>

      {mode === "a" && (
        <div style={{ marginTop: "2rem" }}>
          <h3 style={{ fontSize: "0.95rem", fontWeight: 600, marginBottom: "0.5rem" }}>Avatar</h3>
          <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
            {avatars.map((avatar) => (
              <button
                key={avatar.id}
                type="button"
                onClick={() => setSelectedAvatarId(avatar.id)}
                style={{
                  padding: "0.5rem",
                  borderRadius: 8,
                  border: `1px solid ${selectedAvatarId === avatar.id ? "var(--accent)" : "var(--border)"}`,
                  background: "var(--surface)",
                  cursor: "pointer",
                  textAlign: "center",
                }}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={avatarPortraitUrl(avatar.id)}
                  alt={avatar.name ?? "Avatar"}
                  crossOrigin="use-credentials"
                  style={{ width: 80, height: 80, objectFit: "cover", borderRadius: 6 }}
                />
                <p style={{ fontSize: "0.75rem", marginTop: "0.3rem", color: "var(--text)" }}>
                  {avatar.name}
                </p>
              </button>
            ))}
          </div>

          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              marginTop: "1rem",
              fontSize: "0.85rem",
              color: "var(--text-dim)",
            }}
          >
            <input
              type="checkbox"
              checked={subtitlesOn}
              onChange={(e) => setSubtitlesOn(e.target.checked)}
            />
            Subtitles
          </label>
        </div>
      )}

      {mode === "b" && (
        <div style={{ marginTop: "2rem" }}>
          <h3 style={{ fontSize: "0.95rem", fontWeight: 600, marginBottom: "0.5rem" }}>
            Visual quality
          </h3>
          <div style={{ display: "flex", gap: "1rem" }}>
            <button
              type="button"
              onClick={() => setVisualLevel("photo")}
              style={{
                flex: 1,
                textAlign: "left",
                padding: "0.85rem 1rem",
                borderRadius: 8,
                border: `1px solid ${visualLevel === "photo" ? "var(--accent)" : "var(--border)"}`,
                background: visualLevel === "photo" ? "var(--surface)" : "transparent",
                cursor: "pointer",
              }}
            >
              <p style={{ fontWeight: 600, fontSize: "0.9rem", color: "var(--text)" }}>Photo (fast)</p>
              <p style={{ color: "var(--text-dim)", fontSize: "0.8rem", marginTop: "0.25rem" }}>
                Stock/AI images with cinematic motion. Ready in a couple of minutes.
              </p>
            </button>
            <button
              type="button"
              disabled={!footageAvailable}
              onClick={() => setVisualLevel("footage")}
              style={{
                flex: 1,
                textAlign: "left",
                padding: "0.85rem 1rem",
                borderRadius: 8,
                border: `1px solid ${visualLevel === "footage" ? "var(--accent)" : "var(--border)"}`,
                background: visualLevel === "footage" ? "var(--surface)" : "transparent",
                opacity: footageAvailable ? 1 : 0.5,
                cursor: footageAvailable ? "pointer" : "not-allowed",
              }}
            >
              <p style={{ fontWeight: 600, fontSize: "0.9rem", color: "var(--text)" }}>
                Generated footage
              </p>
              <p style={{ color: "var(--text-dim)", fontSize: "0.8rem", marginTop: "0.25rem" }}>
                {footageAvailable
                  ? "A real AI video clip for every scene. Takes 20-60 minutes - you'll be able to leave and come back."
                  : "Needs the GPU machine online - check the badge above and try later."}
              </p>
            </button>
          </div>
        </div>
      )}

      <div style={{ marginTop: "2rem" }}>
        <h3 style={{ fontSize: "0.95rem", fontWeight: 600, marginBottom: "0.25rem" }}>Voice</h3>
        {hasEnrolledVoice === true && (
          <p style={{ color: "var(--ok)", fontSize: "0.8rem", marginBottom: "0.75rem" }}>
            Your enrolled voice will narrate this video by default.{" "}
            <button
              type="button"
              onClick={() => setManageVoiceOpen((v) => !v)}
              style={{ background: "none", border: "none", color: "var(--accent)", cursor: "pointer", padding: 0, textDecoration: "underline" }}
            >
              Manage
            </button>
          </p>
        )}
        {hasEnrolledVoice === false && (
          <p style={{ color: "var(--text-dim)", fontSize: "0.8rem", marginBottom: "0.75rem" }}>
            Stock voice — you haven&apos;t enrolled your own voice yet.{" "}
            <button
              type="button"
              onClick={() => setManageVoiceOpen((v) => !v)}
              style={{ background: "none", border: "none", color: "var(--accent)", cursor: "pointer", padding: 0, textDecoration: "underline" }}
            >
              Enroll now
            </button>{" "}
            to have every video narrated in your own voice by default.
          </p>
        )}
        {manageVoiceOpen && (
          <div style={{ marginBottom: "1rem" }}>
            <VoiceEnrollment language={project.language} />
          </div>
        )}
        <div style={{ display: "flex", gap: "0.5rem" }}>
          {Object.entries(languageVoices).map(([gender, voiceId]) => (
            <div
              key={voiceId}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
                padding: "0.5rem 0.85rem",
                borderRadius: 8,
                border: `1px solid ${selectedVoice === voiceId ? "var(--accent)" : "var(--border)"}`,
                background: "var(--surface)",
              }}
            >
              <button
                type="button"
                onClick={() => setSelectedVoice(voiceId)}
                style={{
                  border: "none",
                  background: "transparent",
                  color: "var(--text)",
                  cursor: "pointer",
                  fontWeight: selectedVoice === voiceId ? 600 : 400,
                  textTransform: "capitalize",
                  // A text-hugging button with zero padding measured out to
                  // a ~30x15px hit target in practice - too small to click
                  // reliably, especially sitting right next to the audio
                  // player's own scrubber (found live: clicks meant for
                  // this button kept missing).
                  padding: "0.4rem 0.5rem",
                  minHeight: 32,
                }}
              >
                {gender}
              </button>
              <audio controls preload="none" style={{ height: 28 }} src={voicePreviewUrl(voiceId)} />
            </div>
          ))}
        </div>
      </div>

      <div style={{ marginTop: "2rem" }}>
        <h3 style={{ fontSize: "0.95rem", fontWeight: 600, marginBottom: "0.5rem" }}>Subtitles</h3>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          {(["phrase", "karaoke"] as const).map((style) => (
            <button
              key={style}
              type="button"
              onClick={() => setSubtitleStyle(style)}
              style={{
                padding: "0.5rem 0.85rem",
                borderRadius: 8,
                border: `1px solid ${subtitleStyle === style ? "var(--accent)" : "var(--border)"}`,
                background: "var(--surface)",
                color: "var(--text)",
                cursor: "pointer",
                fontWeight: subtitleStyle === style ? 600 : 400,
              }}
            >
              {style === "phrase" ? "Phrase (one line at a time)" : "Karaoke (word-by-word highlight)"}
            </button>
          ))}
        </div>
      </div>

      <div style={{ marginTop: "2rem" }}>
        <label
          style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.95rem", fontWeight: 600 }}
        >
          <input
            type="checkbox"
            checked={musicEnabled}
            onChange={(e) => setMusicEnabled(e.target.checked)}
          />
          Background music
        </label>
        {musicEnabled && (
          <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.75rem", flexWrap: "wrap" }}>
            {musicMoods.map((moodOption) => (
              <div
                key={moodOption}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "0.5rem",
                  padding: "0.5rem 0.85rem",
                  borderRadius: 8,
                  border: `1px solid ${musicMood === moodOption ? "var(--accent)" : "var(--border)"}`,
                  background: "var(--surface)",
                }}
              >
                <button
                  type="button"
                  onClick={() => setMusicMood(moodOption)}
                  style={{
                    border: "none",
                    background: "transparent",
                    color: "var(--text)",
                    cursor: "pointer",
                    fontWeight: musicMood === moodOption ? 600 : 400,
                  }}
                >
                  {MOOD_LABELS[moodOption]}
                </button>
                <audio controls preload="none" style={{ height: 28 }} src={musicPreviewUrl(moodOption)} />
              </div>
            ))}
          </div>
        )}
      </div>

      {error && <p style={{ color: "var(--bad)", marginTop: "1.5rem" }}>{error}</p>}

      <button
        type="button"
        disabled={generating}
        onClick={handleGenerate}
        style={{
          marginTop: "2rem",
          padding: "0.85rem 1.5rem",
          borderRadius: 8,
          border: "none",
          background: "var(--accent)",
          color: "#0b0c0f",
          fontWeight: 600,
          fontSize: "1rem",
          cursor: generating ? "not-allowed" : "pointer",
        }}
      >
        {generating ? "Starting…" : "Generate video"}
      </button>
    </main>
  );
}
