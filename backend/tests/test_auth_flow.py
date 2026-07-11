import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.auth.passwords import hash_password
from app.core.config import get_settings
from app.core.ids import new_id
from app.db.connection import get_connection
from app.main import create_app


@pytest.fixture
def client(monkeypatch, tmp_path):
    # app.core.limiter.limiter is a module-level singleton (shared across
    # every test in this process, not per-app) - without resetting it, a
    # rate-limit-exhausting test poisons every later test's ability to log
    # in at all. Found by running the suite, not by reading slowapi's docs.
    from app.core.limiter import limiter

    limiter.reset()
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path / "media"))
    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as c:
        yield app, c
    limiter.reset()
    get_settings.cache_clear()


def _create_user(email: str, password: str, role: str = "user") -> str:
    settings = get_settings()
    conn = get_connection(settings.db_path)
    user_id = new_id()
    conn.execute(
        "INSERT INTO users (id, email, password_hash, verified, role) VALUES (?, ?, ?, 1, ?)",
        (user_id, email, hash_password(password), role),
    )
    conn.commit()
    conn.close()
    return user_id


def test_unauthenticated_request_is_rejected(client):
    _, c = client
    resp = c.get("/api/projects")
    assert resp.status_code == 401


def test_health_stays_public_without_a_session(client):
    _, c = client
    resp = c.get("/api/meta/health")
    assert resp.status_code == 200


def test_login_with_correct_credentials_sets_a_session_cookie_and_unlocks_routes(client):
    _, c = client
    _create_user("owner@example.com", "correct horse battery staple")

    resp = c.post("/api/auth/login", json={"email": "owner@example.com", "password": "correct horse battery staple"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "owner@example.com"
    assert "session" in resp.cookies

    resp2 = c.get("/api/projects")
    assert resp2.status_code == 200


def test_session_cookie_is_none_and_secure_for_a_cross_origin_deploy(client, monkeypatch):
    """A frontend hosted elsewhere (Vercel) than the backend (task-20's
    ad-hoc PC-hosted deploy) needs SameSite=None - Lax would get set on
    login but never sent back on the next cross-site fetch(), which is
    exactly the bug this test guards (found live: login "succeeded", then
    every following request 401'd)."""
    _, c = client
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://example-frontend.vercel.app")
    get_settings.cache_clear()
    _create_user("cross@example.com", "correct horse battery staple")

    resp = c.post("/api/auth/login", json={"email": "cross@example.com", "password": "correct horse battery staple"})
    assert resp.status_code == 200
    set_cookie = resp.headers.get("set-cookie", "")
    assert "samesite=none" in set_cookie.lower()
    assert "secure" in set_cookie.lower()


def test_session_cookie_is_lax_for_localhost_dev(client):
    """The default dev setup (frontend and backend both on localhost) keeps
    the friendlier Lax/non-Secure cookie - no reason to require HTTPS
    locally, and this is also what makes the TestClient's own plain-http
    requests work at all (see conftest.py's FRONTEND_ORIGIN pin)."""
    _, c = client
    _create_user("local@example.com", "correct horse battery staple")

    resp = c.post("/api/auth/login", json={"email": "local@example.com", "password": "correct horse battery staple"})
    assert resp.status_code == 200
    set_cookie = resp.headers.get("set-cookie", "")
    assert "samesite=lax" in set_cookie.lower()
    assert "secure" not in set_cookie.lower()


def test_logout_cookie_deletion_matches_the_original_attributes(client, monkeypatch):
    """Mismatched SameSite/Secure between set and delete can leave a stale
    cookie the browser never actually clears - logout must use the exact
    same attributes login used."""
    _, c = client
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://example-frontend.vercel.app")
    get_settings.cache_clear()
    _create_user("logout-cross@example.com", "correct horse battery staple")
    c.post("/api/auth/login", json={"email": "logout-cross@example.com", "password": "correct horse battery staple"})

    resp = c.post("/api/auth/logout")
    set_cookie = resp.headers.get("set-cookie", "")
    assert "samesite=none" in set_cookie.lower()
    assert "secure" in set_cookie.lower()


def test_login_with_wrong_password_is_rejected(client):
    _, c = client
    _create_user("owner@example.com", "correct horse battery staple")

    resp = c.post("/api/auth/login", json={"email": "owner@example.com", "password": "wrong password"})
    assert resp.status_code == 400
    assert "invalid" in resp.json()["error"]["message"].lower()
    assert "session" not in resp.cookies


def test_login_with_unknown_email_gives_the_same_honest_message(client):
    """Doesn't leak which emails have accounts - same message either way."""
    _, c = client
    resp = c.post("/api/auth/login", json={"email": "nobody@example.com", "password": "whatever12345"})
    assert resp.status_code == 400
    assert resp.json()["error"]["message"] == "Invalid email or password"


def test_logout_clears_the_session(client):
    _, c = client
    _create_user("owner@example.com", "correct horse battery staple")
    c.post("/api/auth/login", json={"email": "owner@example.com", "password": "correct horse battery staple"})
    assert c.get("/api/projects").status_code == 200

    logout_resp = c.post("/api/auth/logout")
    assert logout_resp.status_code == 204

    assert c.get("/api/projects").status_code == 401


def test_no_public_registration_endpoint_exists(client):
    """specs/04-tasks/task-14-auth-accounts.md: no open registration -
    accounts only via scripts/create_user.py."""
    _, c = client
    resp = c.post("/api/auth/register", json={"email": "x@example.com", "password": "whatever12345"})
    assert resp.status_code == 404


def test_deleted_user_session_is_rejected(client):
    """A stale cookie for an account that no longer exists must fail
    cleanly, not 500."""
    _, c = client
    _create_user("owner@example.com", "correct horse battery staple")
    c.post("/api/auth/login", json={"email": "owner@example.com", "password": "correct horse battery staple"})
    assert c.get("/api/projects").status_code == 200

    settings = get_settings()
    conn = get_connection(settings.db_path)
    conn.execute("DELETE FROM users WHERE email = ?", ("owner@example.com",))
    conn.commit()
    conn.close()

    resp = c.get("/api/projects")
    assert resp.status_code == 401


def test_cross_user_project_access_returns_404_not_403(client):
    """specs/04-tasks/task-14-auth-accounts.md Acceptance: cross-user access
    returns 404 (not 403) - existing users shouldn't even learn a resource
    exists."""
    app, c = client
    user_a = _create_user("alice@example.com", "alice-password-123")
    _create_user("bob@example.com", "bob-password-123")

    from app.core.deps import get_current_user_id

    app.dependency_overrides[get_current_user_id] = lambda: user_a
    project = c.post(
        "/api/projects", json={"description": "d", "language": "hi", "duration_s": 30, "format": "9x16"}
    ).json()

    c.post("/api/auth/login", json={"email": "bob@example.com", "password": "bob-password-123"})
    del app.dependency_overrides[get_current_user_id]

    resp = c.get(f"/api/projects/{project['id']}")
    assert resp.status_code == 404


def test_cross_user_avatar_access_returns_404_not_403(client):
    app, c = client
    user_a = _create_user("alice@example.com", "alice-password-123")
    _create_user("bob@example.com", "bob-password-123")

    from app.core.deps import get_current_user_id

    settings = get_settings()
    conn = get_connection(settings.db_path)
    avatar_id = new_id()
    conn.execute(
        "INSERT INTO avatars (id, user_id, name, approved, consented) VALUES (?, ?, 'A', 1, 1)",
        (avatar_id, user_a),
    )
    conn.commit()
    conn.close()

    c.post("/api/auth/login", json={"email": "bob@example.com", "password": "bob-password-123"})
    resp = c.get(f"/api/avatars/{avatar_id}")
    assert resp.status_code == 404


def test_cross_user_job_access_returns_404_not_403(client):
    app, c = client
    user_a = _create_user("alice@example.com", "alice-password-123")
    _create_user("bob@example.com", "bob-password-123")

    from app.core.deps import get_current_user_id

    settings = get_settings()
    conn = get_connection(settings.db_path)
    job_id = new_id()
    conn.execute(
        "INSERT INTO jobs (id, user_id, type, status, payload_json) VALUES (?, ?, 'noop_render', 'queued', '{}')",
        (job_id, user_a),
    )
    conn.commit()
    conn.close()

    c.post("/api/auth/login", json={"email": "bob@example.com", "password": "bob-password-123"})
    resp = c.get(f"/api/jobs/{job_id}")
    assert resp.status_code == 404


def test_login_rate_limit_kicks_in_after_repeated_attempts(client):
    """specs/04-tasks/task-14-auth-accounts.md: "basic rate-limit on the
    login endpoint... it's still on the public internet." Doesn't assert an
    exact threshold (that's an implementation constant, not a contract) -
    just that hammering login eventually gets throttled rather than
    accepting unlimited guesses."""
    _, c = client
    _create_user("owner@example.com", "correct horse battery staple")

    statuses = [
        c.post("/api/auth/login", json={"email": "owner@example.com", "password": "wrong"}).status_code
        for _ in range(15)
    ]
    assert 429 in statuses


def test_delete_account_removes_everything_and_leaves_other_accounts_untouched(client):
    app, c = client
    user_a = _create_user("alice@example.com", "alice-password-123")
    user_b = _create_user("bob@example.com", "bob-password-123")

    from app.core.deps import get_current_user_id

    app.dependency_overrides[get_current_user_id] = lambda: user_a
    project_a = c.post(
        "/api/projects", json={"description": "d", "language": "hi", "duration_s": 30, "format": "9x16"}
    ).json()
    del app.dependency_overrides[get_current_user_id]

    app.dependency_overrides[get_current_user_id] = lambda: user_b
    project_b = c.post(
        "/api/projects", json={"description": "d", "language": "hi", "duration_s": 30, "format": "9x16"}
    ).json()
    del app.dependency_overrides[get_current_user_id]

    c.post("/api/auth/login", json={"email": "alice@example.com", "password": "alice-password-123"})
    delete_resp = c.delete("/api/me")
    assert delete_resp.status_code == 204

    settings = get_settings()
    conn = get_connection(settings.db_path)
    assert conn.execute("SELECT id FROM users WHERE id = ?", (user_a,)).fetchone() is None
    assert conn.execute("SELECT id FROM projects WHERE id = ?", (project_a["id"],)).fetchone() is None
    # Bob's account and project must survive untouched.
    assert conn.execute("SELECT id FROM users WHERE id = ?", (user_b,)).fetchone() is not None
    assert conn.execute("SELECT id FROM projects WHERE id = ?", (project_b["id"],)).fetchone() is not None
    conn.close()

    # The session cookie itself must be cleared - a request "as alice" now
    # fails rather than somehow still resolving.
    assert c.get("/api/projects").status_code == 401


def test_delete_account_removes_the_media_folder(client):
    app, c = client
    user_a = _create_user("alice@example.com", "alice-password-123")

    from app.core.deps import get_current_user_id
    from app.pipelines.common import project_dir

    app.dependency_overrides[get_current_user_id] = lambda: user_a
    project = c.post(
        "/api/projects", json={"description": "d", "language": "hi", "duration_s": 30, "format": "9x16"}
    ).json()
    del app.dependency_overrides[get_current_user_id]

    settings = get_settings()
    p_dir = project_dir(settings.media_root, user_a, project["id"])
    p_dir.mkdir(parents=True, exist_ok=True)
    (p_dir / "output.mp4").write_bytes(b"fake")

    c.post("/api/auth/login", json={"email": "alice@example.com", "password": "alice-password-123"})
    c.delete("/api/me")

    assert not (settings.media_root / "users" / user_a).exists()
