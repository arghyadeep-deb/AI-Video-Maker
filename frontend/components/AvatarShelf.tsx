"use client";

// Compact avatar shelf for the "/" library page —
// specs/03-design/10-frontend-pages.md: "Secondary: Avatars shelf".
import Link from "next/link";
import { avatarPortraitUrl, type Avatar } from "@/lib/api";

export default function AvatarShelf({ avatars }: { avatars: Avatar[] }) {
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <h2 style={{ fontSize: "1.05rem", fontWeight: 600 }}>Avatars</h2>
        <Link href="/avatars" style={{ fontSize: "0.85rem", color: "var(--accent)" }}>
          Manage
        </Link>
      </div>
      {avatars.length === 0 ? (
        <p style={{ color: "var(--text-dim)", fontSize: "0.85rem", marginTop: "0.5rem" }}>
          No approved avatars yet.
        </p>
      ) : (
        <div style={{ display: "flex", gap: "0.75rem", marginTop: "0.75rem", flexWrap: "wrap" }}>
          {avatars.map((avatar) => (
            <Link
              key={avatar.id}
              href="/avatars"
              style={{ textAlign: "center", width: 72 }}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={avatarPortraitUrl(avatar.id)}
                alt={avatar.name ?? "Avatar"}
                crossOrigin="use-credentials"
                style={{ width: 72, height: 72, objectFit: "cover", borderRadius: 8 }}
              />
              <p
                style={{
                  fontSize: "0.7rem",
                  marginTop: "0.3rem",
                  color: "var(--text)",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {avatar.name}
              </p>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
