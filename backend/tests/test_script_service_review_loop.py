import pytest

from app.core.errors import NotFoundError
from app.db.connection import get_connection, run_migrations
from app.models.script import Scene
from app.services.script_service import (
    apply_manual_edit,
    estimate_duration_s,
    prune_old_versions,
)


def _scenes():
    return [
        Scene(id=1, text="one two three", visual_hint="a"),
        Scene(id=2, text="four five six seven", visual_hint="b"),
    ]


def test_estimate_duration_s_english():
    scenes = [Scene(id=1, text=" ".join(["word"] * 140), visual_hint="x")]
    assert estimate_duration_s(scenes, "en") == pytest.approx(60.0)


def test_estimate_duration_s_hindi():
    scenes = [Scene(id=1, text=" ".join(["शब्द"] * 120), visual_hint="x")]
    assert estimate_duration_s(scenes, "hi") == pytest.approx(60.0)


def test_apply_manual_edit_replaces_only_target_scene():
    scenes = _scenes()
    updated = apply_manual_edit(scenes, 2, "new text here")

    assert updated[0].text == "one two three"
    assert updated[0].visual_hint_stale is False
    assert updated[1].text == "new text here"
    assert updated[1].visual_hint_stale is True
    # Original list is untouched (scenes are copied, not mutated in place).
    assert scenes[1].text == "four five six seven"


def test_apply_manual_edit_unknown_scene_raises_not_found():
    with pytest.raises(NotFoundError):
        apply_manual_edit(_scenes(), 99, "x")


def test_prune_old_versions_keeps_most_recent(tmp_path):
    db_path = tmp_path / "app.db"
    run_migrations(db_path)
    conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT INTO users (id, email, password_hash) VALUES ('u1', 'a@b.com', 'x')"
        )
        conn.execute(
            "INSERT INTO projects (id, user_id, description, language, duration_s, format) "
            "VALUES ('p1', 'u1', 'd', 'en', 60, '9x16')"
        )
        for n in range(1, 16):  # 15 versions
            conn.execute(
                "INSERT INTO script_versions (id, project_id, n, scenes_json, origin) "
                "VALUES (?, 'p1', ?, '[]', 'edited')",
                (f"v{n}", n),
            )
        conn.commit()

        prune_old_versions(conn, "p1", keep=10)
        conn.commit()

        remaining = conn.execute(
            "SELECT n FROM script_versions WHERE project_id = 'p1' ORDER BY n"
        ).fetchall()
        assert [r["n"] for r in remaining] == list(range(6, 16))
    finally:
        conn.close()
