import pytest

from app.core.config import get_settings

DEV_USER_ID = "00000000-0000-7000-8000-000000000001"


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """Every test gets a fresh Settings() read from current env vars."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def authenticate(app, user_id: str = DEV_USER_ID) -> None:
    """Test helper for task-14's real cookie/JWT auth: seeds a user row and
    overrides `get_current_user_id` so the many existing test suites
    (written pre-auth, using TestClient directly rather than a real login
    round-trip) don't all need rewriting to go through POST /api/auth/login
    for every request. Call after the app's lifespan has run migrations
    (i.e. inside a `with TestClient(app) as c:` block), not before.
    """
    from app.core.deps import get_current_user_id
    from app.db.connection import get_connection

    settings = get_settings()
    conn = get_connection(settings.db_path)
    conn.execute(
        "INSERT OR IGNORE INTO users (id, email, password_hash) VALUES (?, ?, ?)",
        (user_id, "dev@local", "unset"),
    )
    conn.commit()
    conn.close()
    app.dependency_overrides[get_current_user_id] = lambda: user_id
