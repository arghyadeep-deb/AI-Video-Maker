"use client";

// specs/03-design/10-frontend-pages.md's /login route. No /register page:
// this is an invite-only site (specs/04-tasks/task-14-auth-accounts.md) -
// accounts are created only via backend/scripts/create_user.py.
import { useState } from "react";
import { useRouter } from "next/navigation";
import { ApiRequestError, login } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      router.push("/");
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.hint ?? err.message : "Failed to log in");
      setBusy(false);
    }
  }

  return (
    <main
      style={{
        maxWidth: 360,
        margin: "0 auto",
        padding: "6rem 1.5rem",
      }}
    >
      <h1 style={{ fontSize: "1.5rem", fontWeight: 600 }}>AI Video Maker</h1>
      <p style={{ color: "var(--text-dim)", marginTop: "0.5rem" }}>Sign in to your account.</p>

      <form onSubmit={handleSubmit} style={{ marginTop: "2rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
        <div>
          <label style={{ display: "block", marginBottom: "0.4rem", fontSize: "0.85rem", color: "var(--text-dim)" }}>
            Email
          </label>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            style={{
              width: "100%",
              padding: "0.6rem",
              borderRadius: 6,
              border: "1px solid var(--border)",
              background: "var(--bg)",
              color: "var(--text)",
            }}
          />
        </div>
        <div>
          <label style={{ display: "block", marginBottom: "0.4rem", fontSize: "0.85rem", color: "var(--text-dim)" }}>
            Password
          </label>
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            style={{
              width: "100%",
              padding: "0.6rem",
              borderRadius: 6,
              border: "1px solid var(--border)",
              background: "var(--bg)",
              color: "var(--text)",
            }}
          />
        </div>

        {error && <p style={{ color: "var(--bad)", fontSize: "0.9rem" }}>{error}</p>}

        <button
          type="submit"
          disabled={busy}
          style={{
            padding: "0.7rem",
            borderRadius: 8,
            border: "none",
            background: "var(--accent)",
            color: "#0b0c0f",
            fontWeight: 600,
            cursor: busy ? "not-allowed" : "pointer",
          }}
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>

      <p style={{ color: "var(--text-dim)", fontSize: "0.8rem", marginTop: "1.5rem" }}>
        This is an invite-only site — accounts are created by the owner.
      </p>
    </main>
  );
}
