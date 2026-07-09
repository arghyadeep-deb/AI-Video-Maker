"use client";

// Avatar management — not yet linked from a real nav (there's no library
// home page/navbar yet); Mode A itself isn't selectable in /generate until
// task-12 wires up render_mode_a. This page lets avatars be created and
// approved ahead of that, so task-10's own work is actually usable/testable.
import { useEffect, useState } from "react";
import AvatarSetup from "@/components/AvatarSetup";
import { ApiRequestError, avatarPortraitUrl, listApprovedAvatars, type Avatar } from "@/lib/api";

export default function AvatarsPage() {
  const [avatars, setAvatars] = useState<Avatar[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);

  function refresh() {
    listApprovedAvatars()
      .then(setAvatars)
      .catch((err: unknown) =>
        setError(err instanceof ApiRequestError ? err.hint ?? err.message : "Failed to load avatars")
      );
  }

  useEffect(refresh, []);

  return (
    <main style={{ maxWidth: 640, margin: "0 auto", padding: "4rem 1.5rem" }}>
      <h1 style={{ fontSize: "1.5rem", fontWeight: 600 }}>Your avatars</h1>
      <p style={{ color: "var(--text-dim)", marginTop: "0.5rem" }}>
        Approved avatars are reusable across projects without re-styling.
      </p>

      {error && <p style={{ color: "var(--bad)", marginTop: "1rem" }}>{error}</p>}

      {avatars.length > 0 && (
        <div style={{ display: "flex", gap: "1rem", marginTop: "2rem", flexWrap: "wrap" }}>
          {avatars.map((a) => (
            <div key={a.id} style={{ textAlign: "center" }}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={avatarPortraitUrl(a.id)}
                alt={a.name ?? "Avatar"}
                crossOrigin="use-credentials"
                style={{ width: 120, height: 120, objectFit: "cover", borderRadius: 8 }}
              />
              <p style={{ fontSize: "0.85rem", marginTop: "0.4rem" }}>{a.name}</p>
            </div>
          ))}
        </div>
      )}

      {!showForm ? (
        <button
          type="button"
          onClick={() => setShowForm(true)}
          style={{
            marginTop: "2rem",
            padding: "0.6rem 1.2rem",
            borderRadius: 8,
            border: "none",
            background: "var(--accent)",
            color: "#0b0c0f",
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          New avatar
        </button>
      ) : (
        <div style={{ marginTop: "2rem" }}>
          <AvatarSetup
            onApproved={() => {
              refresh();
              setShowForm(false);
            }}
          />
        </div>
      )}
    </main>
  );
}
