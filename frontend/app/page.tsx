"use client";

// Library home — specs/03-design/10-frontend-pages.md's "/" route.
import Link from "next/link";
import { useEffect, useState } from "react";
import AccountMenu from "@/components/AccountMenu";
import AvatarShelf from "@/components/AvatarShelf";
import DeleteConfirm from "@/components/DeleteConfirm";
import ProjectCard from "@/components/ProjectCard";
import {
  ApiRequestError,
  deleteProject,
  listApprovedAvatars,
  listProjects,
  type Avatar,
  type ProjectSummary,
} from "@/lib/api";

export default function Home() {
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);
  const [avatars, setAvatars] = useState<Avatar[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<ProjectSummary | null>(null);
  const [deleting, setDeleting] = useState(false);

  function refresh() {
    Promise.all([listProjects(), listApprovedAvatars()])
      .then(([projectList, avatarList]) => {
        setProjects(projectList);
        setAvatars(avatarList);
      })
      .catch((err: unknown) =>
        setError(err instanceof ApiRequestError ? err.hint ?? err.message : "Failed to load your library")
      );
  }

  useEffect(refresh, []);

  async function handleConfirmDelete() {
    if (!pendingDelete) return;
    setDeleting(true);
    try {
      await deleteProject(pendingDelete.id);
      setPendingDelete(null);
      refresh();
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.hint ?? err.message : "Failed to delete project");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <main style={{ maxWidth: 960, margin: "0 auto", padding: "3rem 1.5rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <h1 style={{ fontSize: "1.75rem", fontWeight: 600 }}>AI Video Maker</h1>
        <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
          <Link
            href="/create"
            style={{
              padding: "0.6rem 1.2rem",
              borderRadius: 8,
              border: "none",
              background: "var(--accent)",
              color: "#0b0c0f",
              fontWeight: 600,
            }}
          >
            New video
          </Link>
          <AccountMenu />
        </div>
      </div>

      {error && <p style={{ color: "var(--bad)", marginTop: "1rem" }}>{error}</p>}

      {projects === null ? (
        <p style={{ color: "var(--text-dim)", marginTop: "2rem" }}>Loading…</p>
      ) : projects.length === 0 ? (
        <div
          style={{
            marginTop: "2rem",
            padding: "2rem",
            borderRadius: 8,
            border: "1px solid var(--border)",
            textAlign: "center",
          }}
        >
          <p style={{ fontWeight: 600 }}>No videos yet</p>
          <p style={{ color: "var(--text-dim)", marginTop: "0.5rem", fontSize: "0.9rem" }}>
            Describe a topic and get a script in Hindi or English, then bring it to life as a
            talking avatar of yourself or a narrated image video.
          </p>
          <Link
            href="/create"
            style={{
              display: "inline-block",
              marginTop: "1.25rem",
              padding: "0.6rem 1.2rem",
              borderRadius: 8,
              border: "none",
              background: "var(--accent)",
              color: "#0b0c0f",
              fontWeight: 600,
            }}
          >
            Describe your first video
          </Link>
        </div>
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))",
            gap: "1rem",
            marginTop: "2rem",
          }}
        >
          {projects.map((project) => (
            <ProjectCard key={project.id} project={project} onDelete={setPendingDelete} />
          ))}
        </div>
      )}

      <div style={{ marginTop: "3rem" }}>
        <AvatarShelf avatars={avatars} />
      </div>

      {pendingDelete && (
        <DeleteConfirm
          title="Delete this video?"
          message={`"${pendingDelete.title ?? "Untitled"}" and all its files will be permanently deleted.`}
          busy={deleting}
          onConfirm={handleConfirmDelete}
          onCancel={() => setPendingDelete(null)}
        />
      )}
    </main>
  );
}
