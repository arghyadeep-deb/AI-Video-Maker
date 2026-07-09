import json

import pytest

from app.db.connection import get_connection, run_migrations
from app.models.image import ImageCandidate
from app.models.script import Scene
from app.services.image_service import (
    ImageSourcingError,
    build_stale_hint_prompt,
    parse_hint_updates,
    refresh_stale_hints,
    source_project_images,
    source_scene_image,
    source_scene_image_with_alternates,
)


class StubEngine:
    """Simulates a recorded fixture: returns canned candidates and records
    every query it was asked (so tests can assert the fallback chain order).
    """

    def __init__(self, name: str, candidates: list[ImageCandidate] | None = None):
        self.name = name
        self._candidates = candidates or []
        self.queries: list[str] = []

    async def search(self, query, orientation, per_page=5):
        self.queries.append(query)
        return list(self._candidates)


def _candidate(source: str, source_id: str, w=1920, h=1200) -> ImageCandidate:
    # image_bytes (not a real url) so download_candidate never makes a real
    # network call in these tests - "recorded fixture" style per task-08's
    # own Tests section, not a live integration test.
    return ImageCandidate(
        source=source, source_id=source_id, width=w, height=h, image_bytes=b"fake-image-bytes"
    )


def _scene(scene_id=1, hint="business meeting", stale=False) -> Scene:
    return Scene(id=scene_id, text="कुछ पाठ", visual_hint=hint, visual_hint_stale=stale)


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "app.db"
    run_migrations(db_path)
    connection = get_connection(db_path)
    yield connection
    connection.close()


class TestFallbackChain:
    async def test_pexels_hit_stops_the_chain(self, conn):
        pexels = StubEngine("pexels", [_candidate("pexels", "p1")])
        pixabay = StubEngine("pixabay")
        genai = StubEngine("genai")

        chosen, engine_used = await source_scene_image(conn, _scene(), "9x16", set(), pexels, pixabay, genai)

        assert engine_used == "pexels"
        assert chosen.source_id == "p1"
        assert pixabay.queries == []  # never consulted

    async def test_pexels_empty_falls_to_pixabay(self, conn):
        pexels = StubEngine("pexels", [])
        pixabay = StubEngine("pixabay", [_candidate("pixabay", "px1")])
        genai = StubEngine("genai")

        chosen, engine_used = await source_scene_image(conn, _scene(), "9x16", set(), pexels, pixabay, genai)

        assert engine_used == "pixabay"
        assert chosen.source_id == "px1"
        assert pexels.queries == [_scene().visual_hint]

    async def test_both_stocks_empty_falls_to_genai(self, conn):
        pexels = StubEngine("pexels", [])
        pixabay = StubEngine("pixabay", [])
        genai = StubEngine("genai", [_candidate("genai", "g1")])

        chosen, engine_used = await source_scene_image(conn, _scene(), "9x16", set(), pexels, pixabay, genai)

        assert engine_used == "genai"
        assert chosen.source_id == "g1"

    async def test_low_resolution_candidates_are_treated_as_no_hit(self, conn):
        pexels = StubEngine("pexels", [_candidate("pexels", "small", w=400, h=600)])
        pixabay = StubEngine("pixabay", [_candidate("pixabay", "big", w=1920, h=1200)])
        genai = StubEngine("genai")

        chosen, engine_used = await source_scene_image(conn, _scene(), "9x16", set(), pexels, pixabay, genai)
        assert engine_used == "pixabay"

    async def test_provider_exception_falls_through_to_next(self, conn):
        class BoomEngine:
            async def search(self, *a, **kw):
                raise RuntimeError("provider is down")

        pixabay = StubEngine("pixabay", [_candidate("pixabay", "px1")])
        genai = StubEngine("genai")

        chosen, engine_used = await source_scene_image(conn, _scene(), "9x16", set(), BoomEngine(), pixabay, genai)
        assert engine_used == "pixabay"

    async def test_genai_producing_nothing_raises(self, conn):
        pexels = StubEngine("pexels", [])
        pixabay = StubEngine("pixabay", [])
        genai = StubEngine("genai", [])

        with pytest.raises(ImageSourcingError):
            await source_scene_image(conn, _scene(), "9x16", set(), pexels, pixabay, genai)

    async def test_genai_cap_blocks_the_fallback_without_touching_stock_attempts(self, conn, monkeypatch):
        """specs/04-tasks/task-15-quotas-fairness.md: only the genai
        fallback is capped - guarding up-front would incorrectly block
        stock-image attempts too, which aren't capped at all."""
        from app.core.config import get_settings
        from app.engines.script_llm import QuotaExhaustedError
        from app.quota import guards

        monkeypatch.setattr(get_settings(), "genai_image_daily_cap", 1)
        guards.increment_usage(conn, "genai_image", n=1)

        pexels = StubEngine("pexels", [_candidate("pexels", "p1")])
        pixabay = StubEngine("pixabay")
        genai = StubEngine("genai", [_candidate("genai", "g1")])

        # Stock hit still works fine even with the genai cap exhausted.
        chosen, engine_used = await source_scene_image(conn, _scene(), "9x16", set(), pexels, pixabay, genai)
        assert engine_used == "pexels"

        # But actually needing the genai fallback is blocked.
        pexels_empty = StubEngine("pexels", [])
        pixabay_empty = StubEngine("pixabay", [])
        with pytest.raises(QuotaExhaustedError):
            await source_scene_image(conn, _scene(), "9x16", set(), pexels_empty, pixabay_empty, genai)


class TestAlternatesForSwapPicker:
    """task-17-post-render-tools.md's swap-image picker needs the other
    scored candidates, not just the winner - specs/03-design/05-mode-b-pipeline.md:
    "the 5 scored candidates are cached for exactly this"."""

    async def test_stock_hit_returns_other_usable_candidates_as_alternates(self, conn):
        pexels = StubEngine(
            "pexels",
            [_candidate("pexels", "p1"), _candidate("pexels", "p2"), _candidate("pexels", "p3")],
        )
        pixabay = StubEngine("pixabay")
        genai = StubEngine("genai")

        chosen, engine_used, alternates = await source_scene_image_with_alternates(
            conn, _scene(), "9x16", set(), pexels, pixabay, genai
        )

        assert engine_used == "pexels"
        alt_ids = {c.source_id for c in alternates}
        assert chosen.source_id not in alt_ids
        assert alt_ids == {"p1", "p2", "p3"} - {chosen.source_id}

    async def test_low_resolution_candidates_never_become_alternates(self, conn):
        pexels = StubEngine(
            "pexels",
            [_candidate("pexels", "big", w=1920, h=1200), _candidate("pexels", "small", w=400, h=600)],
        )
        pixabay = StubEngine("pixabay")
        genai = StubEngine("genai")

        _, _, alternates = await source_scene_image_with_alternates(
            conn, _scene(), "9x16", set(), pexels, pixabay, genai
        )
        assert all(c.source_id != "small" for c in alternates)

    async def test_genai_fallback_has_no_alternates(self, conn):
        pexels = StubEngine("pexels", [])
        pixabay = StubEngine("pixabay", [])
        genai = StubEngine("genai", [_candidate("genai", "g1")])

        _, engine_used, alternates = await source_scene_image_with_alternates(
            conn, _scene(), "9x16", set(), pexels, pixabay, genai
        )
        assert engine_used == "genai"
        assert alternates == []

    async def test_source_scene_image_still_returns_a_plain_two_tuple(self, conn):
        """Existing callers (and 15 pre-existing tests in this file) rely on
        this exact signature - the alternates-returning variant is additive,
        not a breaking change."""
        pexels = StubEngine("pexels", [_candidate("pexels", "p1")])
        pixabay = StubEngine("pixabay")
        genai = StubEngine("genai")

        result = await source_scene_image(conn, _scene(), "9x16", set(), pexels, pixabay, genai)
        assert len(result) == 2


class TestProjectSourcingAndCaching:
    async def test_persists_alternates_alongside_the_winner(self, tmp_path):
        db_path = tmp_path / "app.db"
        run_migrations(db_path)
        conn = get_connection(db_path)
        conn.execute("INSERT INTO users (id, email, password_hash) VALUES ('u1', 'a@b.com', 'x')")
        conn.execute(
            "INSERT INTO projects (id, user_id, description, language, duration_s, format) "
            "VALUES ('p1', 'u1', 'd', 'hi', 60, '9x16')"
        )
        conn.commit()

        pexels = StubEngine(
            "pexels", [_candidate("pexels", "p1"), _candidate("pexels", "p2"), _candidate("pexels", "p3")]
        )
        pixabay = StubEngine("pixabay")
        genai = StubEngine("genai")

        rows = await source_project_images(
            conn, "p1", [_scene(1)], "9x16", tmp_path / "images", pexels, pixabay, genai
        )
        meta = json.loads(rows[0]["meta_json"])
        alt_ids = {a["source_id"] for a in meta["alternates"]}
        assert alt_ids == {"p1", "p2", "p3"} - {meta["source_id"]}
        conn.close()

    async def test_sources_and_persists_credit_metadata(self, tmp_path):
        db_path = tmp_path / "app.db"
        run_migrations(db_path)
        conn = get_connection(db_path)
        conn.execute(
            "INSERT INTO users (id, email, password_hash) VALUES ('u1', 'a@b.com', 'x')"
        )
        conn.execute(
            "INSERT INTO projects (id, user_id, description, language, duration_s, format) "
            "VALUES ('p1', 'u1', 'd', 'hi', 60, '9x16')"
        )
        conn.commit()

        pexels = StubEngine("pexels", [_candidate("pexels", "p1")])
        pexels_candidate = pexels._candidates[0]
        pexels_candidate.photographer = "Jane Doe"
        pixabay = StubEngine("pixabay")
        genai = StubEngine("genai")

        images_dir = tmp_path / "images"
        rows = await source_project_images(
            conn, "p1", [_scene(1)], "9x16", images_dir, pexels, pixabay, genai
        )

        assert len(rows) == 1
        meta = json.loads(rows[0]["meta_json"])
        assert meta["engine"] == "pexels"
        assert meta["photographer"] == "Jane Doe"
        assert (images_dir / "scene-1.jpg").exists()
        conn.close()

    async def test_rerun_with_unchanged_scene_downloads_nothing(self, tmp_path):
        db_path = tmp_path / "app.db"
        run_migrations(db_path)
        conn = get_connection(db_path)
        conn.execute("INSERT INTO users (id, email, password_hash) VALUES ('u1', 'a@b.com', 'x')")
        conn.execute(
            "INSERT INTO projects (id, user_id, description, language, duration_s, format) "
            "VALUES ('p1', 'u1', 'd', 'hi', 60, '9x16')"
        )
        conn.commit()

        pexels = StubEngine("pexels", [_candidate("pexels", "p1")])
        pixabay = StubEngine("pixabay")
        genai = StubEngine("genai")
        images_dir = tmp_path / "images"

        await source_project_images(conn, "p1", [_scene(1)], "9x16", images_dir, pexels, pixabay, genai)
        assert len(pexels.queries) == 1

        # Second run, same non-stale scene: no engine should be queried again.
        await source_project_images(conn, "p1", [_scene(1)], "9x16", images_dir, pexels, pixabay, genai)
        assert len(pexels.queries) == 1  # unchanged - cache hit, no new call
        conn.close()

    async def test_stale_scene_is_resourced_even_if_cached(self, tmp_path):
        db_path = tmp_path / "app.db"
        run_migrations(db_path)
        conn = get_connection(db_path)
        conn.execute("INSERT INTO users (id, email, password_hash) VALUES ('u1', 'a@b.com', 'x')")
        conn.execute(
            "INSERT INTO projects (id, user_id, description, language, duration_s, format) "
            "VALUES ('p1', 'u1', 'd', 'hi', 60, '9x16')"
        )
        conn.commit()

        pexels = StubEngine("pexels", [_candidate("pexels", "p1")])
        pixabay = StubEngine("pixabay")
        genai = StubEngine("genai")
        images_dir = tmp_path / "images"

        await source_project_images(conn, "p1", [_scene(1)], "9x16", images_dir, pexels, pixabay, genai)
        assert len(pexels.queries) == 1

        await source_project_images(
            conn, "p1", [_scene(1, stale=True)], "9x16", images_dir, pexels, pixabay, genai
        )
        assert len(pexels.queries) == 2  # stale -> re-sourced despite existing row
        conn.close()


class TestStaleHintRefresh:
    def test_prompt_includes_only_stale_scenes(self):
        stale = [Scene(id=2, text="x", visual_hint="old hint", visual_hint_stale=True)]
        prompt = build_stale_hint_prompt(stale)
        assert '"id": 2' in prompt
        assert "old hint" not in prompt  # we don't need the stale hint itself, just the text

    def test_parse_hint_updates_handles_valid_json(self):
        raw = '{"1": "sunrise over mountains", "2": "busy city street"}'
        updates = parse_hint_updates(raw)
        assert updates == {1: "sunrise over mountains", 2: "busy city street"}

    def test_parse_hint_updates_handles_malformed_json_gracefully(self):
        assert parse_hint_updates("not json") == {}

    async def test_refresh_only_calls_llm_when_something_is_stale(self):
        class FakeLLM:
            def __init__(self):
                self.called = False

            def generate_text(self, prompt):
                self.called = True
                return "{}"

        llm = FakeLLM()
        scenes = [Scene(id=1, text="x", visual_hint="fresh", visual_hint_stale=False)]
        result = await refresh_stale_hints(llm, scenes)
        assert result == scenes
        assert llm.called is False

    async def test_refresh_updates_only_stale_scenes(self):
        class FakeLLM:
            def generate_text(self, prompt):
                return json.dumps({"2": "new hint for scene two"})

        scenes = [
            Scene(id=1, text="a", visual_hint="hint one", visual_hint_stale=False),
            Scene(id=2, text="b", visual_hint="old hint two", visual_hint_stale=True),
        ]
        result = await refresh_stale_hints(FakeLLM(), scenes)

        assert result[0].visual_hint == "hint one"  # untouched
        assert result[1].visual_hint == "new hint for scene two"
        assert result[1].visual_hint_stale is False
