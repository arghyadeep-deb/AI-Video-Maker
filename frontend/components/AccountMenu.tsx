"use client";

// specs/03-design/10-frontend-pages.md's "/" route: "account menu (delete
// account)". Also the only logout affordance in the app.
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import DeleteConfirm from "@/components/DeleteConfirm";
import { ApiRequestError, deleteAccount, getMe, logout, type User } from "@/lib/api";

export default function AccountMenu() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [open, setOpen] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getMe()
      .then(setUser)
      .catch(() => {
        // handleResponse already redirects to /login on 401 - nothing
        // else to do here.
      });
  }, []);

  async function handleLogout() {
    await logout().catch(() => {});
    router.push("/login");
  }

  async function handleDeleteAccount() {
    setDeleting(true);
    setError(null);
    try {
      await deleteAccount();
      router.push("/login");
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.hint ?? err.message : "Failed to delete account");
      setDeleting(false);
    }
  }

  if (!user) return null;

  return (
    <div style={{ position: "relative" }}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        style={{
          padding: "0.4rem 0.75rem",
          borderRadius: 6,
          border: "1px solid var(--border)",
          background: "transparent",
          color: "var(--text-dim)",
          fontSize: "0.85rem",
          cursor: "pointer",
        }}
      >
        {user.email}
      </button>
      {open && (
        <div
          style={{
            position: "absolute",
            right: 0,
            top: "calc(100% + 0.4rem)",
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            padding: "0.5rem",
            minWidth: 160,
            zIndex: 10,
          }}
        >
          <Link
            href="/privacy"
            style={{
              display: "block",
              width: "100%",
              textAlign: "left",
              padding: "0.5rem 0.75rem",
              color: "var(--text-dim)",
              fontSize: "0.85rem",
              borderRadius: 6,
            }}
          >
            Privacy & data
          </Link>
          <Link
            href="/licenses"
            style={{
              display: "block",
              width: "100%",
              textAlign: "left",
              padding: "0.5rem 0.75rem",
              color: "var(--text-dim)",
              fontSize: "0.85rem",
              borderRadius: 6,
            }}
          >
            Licenses
          </Link>
          <div style={{ borderTop: "1px solid var(--border)", margin: "0.4rem 0" }} />
          <button
            type="button"
            onClick={handleLogout}
            style={{
              display: "block",
              width: "100%",
              textAlign: "left",
              padding: "0.5rem 0.75rem",
              border: "none",
              background: "transparent",
              color: "var(--text)",
              cursor: "pointer",
              borderRadius: 6,
            }}
          >
            Log out
          </button>
          <button
            type="button"
            onClick={() => setConfirmingDelete(true)}
            style={{
              display: "block",
              width: "100%",
              textAlign: "left",
              padding: "0.5rem 0.75rem",
              border: "none",
              background: "transparent",
              color: "var(--bad)",
              cursor: "pointer",
              borderRadius: 6,
            }}
          >
            Delete account
          </button>
        </div>
      )}

      {error && <p style={{ color: "var(--bad)", fontSize: "0.8rem", marginTop: "0.5rem" }}>{error}</p>}

      {confirmingDelete && (
        <DeleteConfirm
          title="Delete your account?"
          message="Every video, avatar, and script you've made will be permanently deleted. This cannot be undone."
          busy={deleting}
          onConfirm={handleDeleteAccount}
          onCancel={() => setConfirmingDelete(false)}
        />
      )}
    </div>
  );
}
