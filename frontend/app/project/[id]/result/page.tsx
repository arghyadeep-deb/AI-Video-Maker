"use client";

// Progress -> player + download — specs/03-design/10-frontend-pages.md.
// Post-render tools (swap image, scene re-render, re-render in other mode)
// — specs/04-tasks/task-17-post-render-tools.md.
import { Suspense, use, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import QueuePosition from "@/components/QueuePosition";
import SceneRerender from "@/components/SceneRerender";
import StageChecklist from "@/components/StageChecklist";
import SwapImagePicker from "@/components/SwapImagePicker";
import { useJob } from "@/hooks/useJob";
import {
  ApiRequestError,
  cancelJob,
  getProject,
  getVoices,
  rerenderOtherMode,
  sceneImageUrl,
  videoDownloadUrl,
  videoStreamUrl,
  type Job,
  type Project,
  type VoiceTable,
} from "@/lib/api";

export default function ResultPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <Suspense fallback={null}>
      <ResultBody projectId={id} />
    </Suspense>
  );
}

function ResultBody({ projectId }: { projectId: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const jobId = searchParams.get("job");
  const { job, error: jobError } = useJob(jobId);

  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [voices, setVoices] = useState<VoiceTable | null>(null);
  const [swapSceneId, setSwapSceneId] = useState<number | null>(null);
  const [postRenderJobId, setPostRenderJobId] = useState<string | null>(null);
  const { job: postRenderJob } = useJob(postRenderJobId);
  const [rerenderBusy, setRerenderBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getProject(projectId)
      .then((proj) => {
        if (!cancelled) setProject(proj);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof ApiRequestError ? err.hint ?? err.message : "Failed to load project");
      });
    return () => {
      cancelled = true;
    };
    // re-fetch once either job finishes, to pick up the (possibly new) output_path
  }, [projectId, job?.status, postRenderJob?.status]);

  useEffect(() => {
    getVoices()
      .then(setVoices)
      .catch(() => {
        // best-effort - the scene re-render voice picker just won't offer a choice
      });
  }, []);

  async function handleCancel() {
    if (!jobId) return;
    try {
      await cancelJob(jobId);
    } catch {
      // best-effort - the checklist will reflect whatever the job settles on
    }
  }

  function handlePostRenderJobStarted(startedJob: Job) {
    setPostRenderJobId(startedJob.id);
  }

  async function handleRerenderOtherMode() {
    if (!project) return;
    setRerenderBusy(true);
    setError(null);
    try {
      const result = await rerenderOtherMode(project.id, {});
      router.push(`/project/${result.project_id}/result?job=${result.job.id}`);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.hint ?? err.message : "Failed to re-render in the other mode");
      setRerenderBusy(false);
    }
  }

  if (error) {
    return (
      <main style={{ maxWidth: 640, margin: "0 auto", padding: "4rem 1.5rem" }}>
        <p style={{ color: "var(--bad)" }}>{error}</p>
      </main>
    );
  }

  if (!project) {
    return (
      <main style={{ maxWidth: 640, margin: "0 auto", padding: "4rem 1.5rem" }}>
        <p style={{ color: "var(--text-dim)" }}>Loading…</p>
      </main>
    );
  }

  const done = project.status === "done" && project.output_path;
  const inProgress = job && !["done", "failed", "cancelled"].includes(job.status);

  return (
    <main style={{ maxWidth: 640, margin: "0 auto", padding: "4rem 1.5rem" }}>
      <h1 style={{ fontSize: "1.5rem", fontWeight: 600 }}>{project.title ?? "Untitled"}</h1>

      {jobError && <p style={{ color: "var(--text-dim)", marginTop: "1rem" }}>{jobError}</p>}

      {job && !done && (
        <div style={{ marginTop: "2rem" }}>
          <QueuePosition job={job} />
          <StageChecklist job={job} />
          {inProgress && (
            <button
              type="button"
              onClick={handleCancel}
              style={{
                marginTop: "1rem",
                padding: "0.5rem 1rem",
                borderRadius: 6,
                border: "1px solid var(--bad)",
                background: "transparent",
                color: "var(--bad)",
                cursor: "pointer",
              }}
            >
              Cancel
            </button>
          )}
          {job.status === "failed" && (
            <p style={{ marginTop: "1rem" }}>
              <Link href={`/project/${project.id}/generate`}>Try again</Link>
            </p>
          )}
        </div>
      )}

      {!job && !done && (
        <p style={{ color: "var(--text-dim)", marginTop: "2rem" }}>
          No active render. <Link href={`/project/${project.id}/generate`}>Generate a video</Link>.
        </p>
      )}

      {done && (
        <div style={{ marginTop: "2rem" }}>
          <video
            controls
            src={videoStreamUrl(project.id)}
            crossOrigin="use-credentials"
            style={{ width: "100%", borderRadius: 8, background: "#000" }}
          />
          <div style={{ display: "flex", gap: "0.75rem", marginTop: "1rem" }}>
            <a
              href={videoDownloadUrl(project.id)}
              style={{
                padding: "0.6rem 1.2rem",
                borderRadius: 6,
                border: "none",
                background: "var(--accent)",
                color: "#0b0c0f",
                fontWeight: 600,
              }}
            >
              Download MP4 + credits
            </a>
            <Link
              href="/create"
              style={{
                padding: "0.6rem 1.2rem",
                borderRadius: 6,
                border: "1px solid var(--border)",
                color: "var(--text)",
              }}
            >
              Make another
            </Link>
            <button
              type="button"
              disabled={rerenderBusy}
              onClick={handleRerenderOtherMode}
              style={{
                padding: "0.6rem 1.2rem",
                borderRadius: 6,
                border: "1px solid var(--border)",
                background: "transparent",
                color: "var(--text)",
                cursor: rerenderBusy ? "not-allowed" : "pointer",
              }}
            >
              {rerenderBusy
                ? "Starting…"
                : project.mode === "a"
                  ? "Re-render as Image Video"
                  : "Re-render as My Avatar"}
            </button>
          </div>

          {postRenderJobId && postRenderJob && !["done", "failed", "cancelled"].includes(postRenderJob.status) && (
            <div style={{ marginTop: "1.5rem" }}>
              <p style={{ color: "var(--text-dim)", fontSize: "0.85rem", marginBottom: "0.5rem" }}>
                Updating this video…
              </p>
              <StageChecklist job={postRenderJob} />
            </div>
          )}

          {project.mode === "b" && project.latest_script_version && (
            <div style={{ marginTop: "2rem" }}>
              <h3 style={{ fontSize: "0.95rem", fontWeight: 600, marginBottom: "0.75rem" }}>Scenes</h3>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                {project.latest_script_version.scenes.map((scene) => (
                  <div
                    key={scene.id}
                    style={{
                      display: "flex", gap: "0.75rem", alignItems: "flex-start",
                      padding: "0.75rem", borderRadius: 8, border: "1px solid var(--border)",
                    }}
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={sceneImageUrl(project.id, scene.id)}
                      alt={`Scene ${scene.id}`}
                      crossOrigin="use-credentials"
                      style={{ width: 60, height: 106, objectFit: "cover", borderRadius: 6, flexShrink: 0 }}
                    />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <p
                        style={{
                          fontSize: "0.85rem", color: "var(--text)", marginBottom: "0.5rem",
                          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                        }}
                      >
                        {scene.text}
                      </p>
                      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "flex-start" }}>
                        <button
                          type="button"
                          onClick={() => setSwapSceneId(scene.id)}
                          style={{
                            fontSize: "0.75rem", padding: "0.3rem 0.6rem", borderRadius: 6,
                            border: "1px solid var(--border)", background: "transparent",
                            color: "var(--text-dim)", cursor: "pointer",
                          }}
                        >
                          Swap image
                        </button>
                        {voices && (
                          <SceneRerender
                            projectId={project.id}
                            sceneId={scene.id}
                            language={project.language}
                            voices={voices}
                            onJobStarted={handlePostRenderJobStarted}
                          />
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {swapSceneId !== null && (
        <SwapImagePicker
          projectId={project.id}
          sceneId={swapSceneId}
          onClose={() => setSwapSceneId(null)}
          onJobStarted={handlePostRenderJobStarted}
        />
      )}
    </main>
  );
}
