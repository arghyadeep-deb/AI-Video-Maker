"use client";

import { use, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import ImproveDiff from "@/components/ImproveDiff";
import SceneCard from "@/components/SceneCard";
import VersionHistory from "@/components/VersionHistory";
import {
  ApiRequestError,
  acceptScript,
  applyImprovement,
  editScene,
  estimateDurationS,
  getProject,
  improveSelection,
  listScriptVersions,
  restoreVersion,
  scrapScript,
  type ImproveProposal,
  type Project,
  type ScriptVersionSummary,
} from "@/lib/api";

const DURATION_WARN_TOLERANCE = 0.2; // ±20% per specs/03-design/03-review-loop-design.md

export default function ScriptPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const [project, setProject] = useState<Project | null>(null);
  const [versions, setVersions] = useState<ScriptVersionSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmingScrap, setConfirmingScrap] = useState(false);
  const [proposal, setProposal] = useState<ImproveProposal | null>(null);

  const refresh = useCallback(async () => {
    const [proj, vers] = await Promise.all([getProject(id), listScriptVersions(id)]);
    setProject(proj);
    setVersions(vers);
  }, [id]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getProject(id), listScriptVersions(id)])
      .then(([proj, vers]) => {
        if (cancelled) return;
        setProject(proj);
        setVersions(vers);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof ApiRequestError ? err.hint ?? err.message : "Failed to load project");
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  const accepted = project?.status === "accepted";

  async function handleSceneSave(sceneId: number, text: string) {
    if (!project) return;
    setBusy(true);
    setError(null);
    try {
      await editScene(project.id, sceneId, text);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.hint ?? err.message : "Failed to save edit");
    } finally {
      setBusy(false);
    }
  }

  async function handleRestore(versionId: string) {
    if (!project) return;
    setBusy(true);
    setError(null);
    try {
      await restoreVersion(project.id, versionId);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.hint ?? err.message : "Failed to restore version");
    } finally {
      setBusy(false);
    }
  }

  async function handleImprove(sceneId: number, start: number, end: number, instruction?: string) {
    if (!project?.latest_script_version) return;
    setError(null);
    try {
      const result = await improveSelection(project.id, {
        version_id: project.latest_script_version.id,
        scene_id: sceneId,
        start,
        end,
        instruction,
      });
      setProposal(result);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.hint ?? err.message : "Failed to improve selection");
    }
  }

  async function handleKeepImprovement() {
    if (!project || !proposal) return;
    setBusy(true);
    setError(null);
    try {
      await applyImprovement(project.id, {
        scene_id: proposal.scene_id,
        proposed_scene_text: proposal.proposed_scene_text,
      });
      setProposal(null);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.hint ?? err.message : "Failed to apply improvement");
    } finally {
      setBusy(false);
    }
  }

  function handleRevertImprovement() {
    setProposal(null); // nothing was ever persisted - discarding is free
  }

  async function handleAccept() {
    if (!project) return;
    setBusy(true);
    setError(null);
    try {
      await acceptScript(project.id);
      router.push(`/project/${project.id}/generate`);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.hint ?? err.message : "Failed to accept script");
      setBusy(false);
    }
  }

  async function handleScrap() {
    if (!project) return;
    setBusy(true);
    setError(null);
    try {
      await scrapScript(project.id);
      router.push(`/create?description=${encodeURIComponent(project.description)}`);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.hint ?? err.message : "Failed to scrap script");
      setBusy(false);
    }
  }

  // Only the initial load (no project yet) takes over the whole page on
  // error. A mutation-triggered refresh failure (edit/restore/accept/scrap)
  // keeps the last-known-good scenes on screen with an inline banner below
  // instead of discarding everything the user can still see and act on.
  if (!project) {
    return (
      <main style={{ maxWidth: 640, margin: "0 auto", padding: "4rem 1.5rem" }}>
        {error ? (
          <p style={{ color: "var(--bad)" }}>{error}</p>
        ) : (
          <p style={{ color: "var(--text-dim)" }}>Loading…</p>
        )}
      </main>
    );
  }

  const scenes = project.latest_script_version?.scenes ?? [];
  const estimatedS = estimateDurationS(scenes, project.language);
  const targetS = project.duration_s;
  const offRatio = targetS > 0 ? Math.abs(estimatedS - targetS) / targetS : 0;
  const durationWarn = offRatio > DURATION_WARN_TOLERANCE;
  const wordCount = scenes.reduce(
    (sum, s) => sum + s.text.trim().split(/\s+/).filter(Boolean).length,
    0
  );

  return (
    <main style={{ maxWidth: 640, margin: "0 auto", padding: "4rem 1.5rem 6rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 600 }}>{project.title ?? "Untitled"}</h1>
          <p style={{ color: "var(--text-dim)", marginTop: "0.25rem" }}>
            {project.language === "hi" ? "हिन्दी" : "English"} · {project.duration_s}s · {project.format}
            {accepted && <span style={{ color: "var(--ok)" }}> · Accepted</span>}
          </p>
        </div>
        <VersionHistory versions={versions} onRestore={handleRestore} />
      </div>

      {error && (
        <p
          style={{
            marginTop: "1rem",
            padding: "0.75rem 1rem",
            borderRadius: 8,
            border: "1px solid var(--bad)",
            color: "var(--bad)",
            fontSize: "0.9rem",
          }}
        >
          {error}
        </p>
      )}

      {scenes.length === 0 ? (
        <p style={{ marginTop: "2rem", color: "var(--text-dim)" }}>No script yet.</p>
      ) : (
        <div style={{ marginTop: "2rem", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {scenes.map((scene) => (
            <SceneCard
              key={`${scene.id}:${scene.text}`}
              scene={scene}
              language={project.language}
              disabled={busy || accepted}
              onSave={handleSceneSave}
              onImprove={handleImprove}
            />
          ))}
        </div>
      )}

      <div
        style={{
          position: "sticky",
          bottom: 0,
          marginTop: "2rem",
          padding: "1rem",
          borderRadius: 8,
          border: "1px solid var(--border)",
          background: "var(--surface)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "1rem",
        }}
      >
        <div style={{ fontSize: "0.85rem", color: durationWarn ? "var(--bad)" : "var(--text-dim)" }}>
          {wordCount} words · ~{estimatedS.toFixed(0)}s estimated (target {targetS}s)
          {durationWarn && " — off target by more than 20%"}
        </div>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <button
            type="button"
            disabled={busy || accepted}
            onClick={() => setConfirmingScrap(true)}
            style={{
              padding: "0.6rem 1rem",
              borderRadius: 6,
              border: "1px solid var(--bad)",
              background: "transparent",
              color: "var(--bad)",
              cursor: busy || accepted ? "not-allowed" : "pointer",
            }}
          >
            Scrap
          </button>
          <button
            type="button"
            disabled={busy || accepted || scenes.length === 0}
            onClick={handleAccept}
            style={{
              padding: "0.6rem 1.2rem",
              borderRadius: 6,
              border: "none",
              background: "var(--accent)",
              color: "#0b0c0f",
              fontWeight: 600,
              cursor: busy || accepted ? "not-allowed" : "pointer",
            }}
          >
            {accepted ? "Accepted" : "Accept & continue"}
          </button>
        </div>
      </div>

      {confirmingScrap && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.6)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 20,
          }}
        >
          <div
            style={{
              padding: "1.5rem",
              borderRadius: 8,
              border: "1px solid var(--border)",
              background: "var(--surface)",
              maxWidth: 360,
            }}
          >
            <p>Scrap this script? This cannot be undone from here — you will start over from the description.</p>
            <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem", justifyContent: "flex-end" }}>
              <button
                type="button"
                onClick={() => setConfirmingScrap(false)}
                style={{
                  padding: "0.5rem 1rem",
                  borderRadius: 6,
                  border: "1px solid var(--border)",
                  background: "transparent",
                  color: "var(--text)",
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => {
                  setConfirmingScrap(false);
                  handleScrap();
                }}
                style={{
                  padding: "0.5rem 1rem",
                  borderRadius: 6,
                  border: "none",
                  background: "var(--bad)",
                  color: "#0b0c0f",
                  fontWeight: 600,
                }}
              >
                Scrap it
              </button>
            </div>
          </div>
        </div>
      )}

      {proposal && (
        <ImproveDiff
          oldSpan={proposal.old_span}
          newSpan={proposal.new_span}
          language={project.language}
          busy={busy}
          onKeep={handleKeepImprovement}
          onRevert={handleRevertImprovement}
        />
      )}
    </main>
  );
}
