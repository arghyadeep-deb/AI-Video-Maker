"use client";

// specs/03-design/10-frontend-pages.md's "/" library grid card.
import Link from "next/link";
import { useJob } from "@/hooks/useJob";
import { projectThumbnailUrl, type ProjectSummary } from "@/lib/api";

const STATUS_LABEL: Record<string, string> = {
  drafting: "Draft",
  accepted: "Ready to generate",
  generating: "Generating…",
  done: "Done",
  failed: "Failed",
  cancelled: "Cancelled",
};

const STATUS_COLOR: Record<string, string> = {
  drafting: "var(--text-dim)",
  accepted: "var(--accent)",
  generating: "var(--accent)",
  done: "var(--ok)",
  failed: "var(--bad)",
  cancelled: "var(--text-dim)",
};

function hrefFor(project: ProjectSummary): string {
  switch (project.status) {
    case "drafting":
      return `/project/${project.id}/script`;
    case "accepted":
      return `/project/${project.id}/generate`;
    case "generating":
      return project.active_job_id
        ? `/project/${project.id}/result?job=${project.active_job_id}`
        : `/project/${project.id}/result`;
    case "done":
      return `/project/${project.id}/result`;
    default:
      return `/project/${project.id}/generate`;
  }
}

export default function ProjectCard({
  project,
  onDelete,
}: {
  project: ProjectSummary;
  onDelete: (project: ProjectSummary) => void;
}) {
  const { job } = useJob(project.status === "generating" ? project.active_job_id : null);
  const label =
    project.status === "generating" && job
      ? `Generating… ${Math.round(job.progress)}%`
      : STATUS_LABEL[project.status] ?? project.status;

  return (
    <div style={{ position: "relative" }}>
      <Link
        href={hrefFor(project)}
        style={{
          display: "block",
          borderRadius: 8,
          border: "1px solid var(--border)",
          overflow: "hidden",
          background: "var(--surface)",
        }}
      >
        <div
          style={{
            aspectRatio: project.format === "9x16" ? "9/16" : "16/9",
            background: "#000",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          {project.has_thumbnail ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={projectThumbnailUrl(project.id)}
              alt={project.title ?? "Untitled"}
              crossOrigin="use-credentials"
              style={{ width: "100%", height: "100%", objectFit: "cover" }}
            />
          ) : (
            <span style={{ color: "var(--text-dim)", fontSize: "0.8rem" }}>No preview yet</span>
          )}
        </div>
        <div style={{ padding: "0.75rem" }}>
          <p style={{ fontWeight: 600, fontSize: "0.95rem" }}>{project.title ?? "Untitled"}</p>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginTop: "0.4rem",
            }}
          >
            <span
              style={{
                fontSize: "0.7rem",
                padding: "0.15rem 0.5rem",
                borderRadius: 999,
                border: "1px solid var(--border)",
                color: "var(--text-dim)",
                textTransform: "uppercase",
              }}
            >
              {project.language}
            </span>
            <span style={{ fontSize: "0.75rem", color: STATUS_COLOR[project.status] ?? "var(--text-dim)" }}>
              {label}
            </span>
          </div>
        </div>
      </Link>
      <button
        type="button"
        onClick={(e) => {
          e.preventDefault();
          onDelete(project);
        }}
        aria-label="Delete project"
        style={{
          position: "absolute",
          top: "0.5rem",
          right: "0.5rem",
          width: 28,
          height: 28,
          borderRadius: 999,
          border: "none",
          background: "rgba(0,0,0,0.6)",
          color: "#fff",
          cursor: "pointer",
        }}
      >
        ×
      </button>
    </div>
  );
}
