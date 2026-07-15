"""Resets an existing account's password — run on the VM by the account owner.

Usage (from backend/):
    python scripts/reset_password.py owner@example.com

Prompts interactively for the new password (getpass) so it never appears in
shell history, logs, or any transcript.
"""
import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth.passwords import hash_password  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.db.connection import get_connection, run_migrations  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("email")
    args = parser.parse_args()

    password = getpass.getpass("New password: ")
    confirm = getpass.getpass("Confirm new password: ")
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
        if existing is None:
            print(f"No user with email {args.email!r} exists.", file=sys.stderr)
            sys.exit(1)

        conn.execute(
            "UPDATE users SET password_hash = ? WHERE email = ?",
            (hash_password(password), args.email),
        )
        conn.commit()
        print(f"Password updated for {args.email}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
