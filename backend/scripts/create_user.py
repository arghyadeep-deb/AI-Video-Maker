"""Creates an invite-only account — the ONLY way to create a user.

specs/04-tasks/task-14-auth-accounts.md: "No open registration and no email
verification: scripts/create_user.py (or an owner-only invite code) creates
the 1-2 accounts." No public POST /register endpoint exists by design.

Usage (from backend/):
    python scripts/create_user.py owner@example.com --admin
    python scripts/create_user.py second-user@example.com
"""
import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth.passwords import hash_password  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.ids import new_id  # noqa: E402
from app.db.connection import get_connection, run_migrations  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("email")
    parser.add_argument("--admin", action="store_true", help="grant the admin role")
    args = parser.parse_args()

    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords don't match.", file=sys.stderr)
        sys.exit(1)
    if len(password) < 8:
        print("Password must be at least 8 characters.", file=sys.stderr)
        sys.exit(1)

    settings = get_settings()
    run_migrations(settings.db_path)
    conn = get_connection(settings.db_path)
    try:
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (args.email,)).fetchone()
        if existing is not None:
            print(f"A user with email {args.email!r} already exists.", file=sys.stderr)
            sys.exit(1)

        user_id = new_id()
        role = "admin" if args.admin else "user"
        conn.execute(
            "INSERT INTO users (id, email, password_hash, verified, role) VALUES (?, ?, ?, 1, ?)",
            (user_id, args.email, hash_password(password), role),
        )
        conn.commit()
        print(f"Created user {args.email} (role={role}, id={user_id})")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
