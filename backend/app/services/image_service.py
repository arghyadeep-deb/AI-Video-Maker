"""Per-project image sourcing orchestration — specs/04-tasks/task-08-image-sourcing.md,
revised task-23-quality-and-ops.md.

Fallback chain: FLUX (generated to match the scene exactly) -> Pexels ->
Pixabay -> nano banana generation, the last three only reached when the
tier(s) before them fail or (for the stock providers) return zero usable
(resolution-qualified) candidates. FLUX moved to the front in task-23:
scoring.py's stock-photo picking has zero semantic relevance check
(resolution/orientation/dedupe only), which was the root cause of images
not matching their scene's text - generating the image directly from the
scene fixes that at the source rather than better-ranking keyword-search
results. Caches per scene in `media_assets`; a re-run with unchanged
(non-stale) scenes downloads nothing.
"""
import json
import sqlite3
from pathlib import Path

import httpx

from app.core.config import get_settings
from app.core.ids import new_id
from app.engines.images.base import StockImageEngine
from app.engines.images.scoring import pick_best, usable_candidates
from app.engines.script_llm import ScriptLLM
from app.models.image import ImageCandidate
from app.models.script import Scene
from app.quota import guards


class ImageSourcingError(Exception):
    pass


async def source_scene_image_with_alternates(
    conn: sqlite3.Connection,
    scene: Scene,
    target_format: str,
    already_used: set[str],
    flux: StockImageEngine,
    pexels: StockImageEngine,
    pixabay: StockImageEngine,
    genai: StockImageEngine,
) -> tuple[ImageCandidate, str, list[ImageCandidate]]:
    """Same fallback chain as `source_scene_image`, but also returns the
    other resolution-qualified candidates from whichever provider won -
    specs/03-design/05-mode-b-pipeline.md: "the 5 scored candidates are
    cached for exactly this" (task-17's swap-image picker). FLUX and the
    genai fallback only ever produce one image each (`per_page=1`), so
    neither has alternates.
    """
    settings = get_settings()
    try:
        # The quota guard lives inside this try too: a FLUX cap already hit
        # must degrade to stock photos exactly like a network failure would,
        # never abort scene sourcing outright (guard() raises on purpose so
        # the cap "can never be blown past" - that's about spending, not
        # about this being a fatal error for the whole scene).
        guards.guard(conn, "flux_image", settings.flux_image_daily_cap)
        generated = await flux.search(scene.visual_hint, target_format, per_page=1)
    except Exception:  # noqa: BLE001 - FLUX failure/quota falls through to stock photos
        generated = []
    if generated:
        guards.increment_usage(conn, "flux_image")
        return generated[0], "flux", []

    for name, engine in (("pexels", pexels), ("pixabay", pixabay)):
        try:
            candidates = await engine.search(scene.visual_hint, target_format, per_page=5)
        except Exception:  # noqa: BLE001 - provider failure falls through, doesn't abort sourcing
            candidates = []
        usable = usable_candidates(candidates)
        chosen = pick_best(usable, target_format, already_used)
        if chosen is not None:
            alternates = [c for c in usable if c.source_id != chosen.source_id]
            return chosen, name, alternates

    # Only the genai fallback is capped (specs/04-tasks/task-15-quotas-fairness.md)
    # - guarding here, not up-front, means stock-image attempts are never
    # blocked by this cap, only the genai path they'd otherwise fall
    # through to.
    guards.guard(conn, "genai_image", settings.genai_image_daily_cap)

    generated = await genai.search(scene.visual_hint, target_format, per_page=1)
    if not generated:
        raise ImageSourcingError(f"genai fallback produced no image for scene {scene.id}")
    guards.increment_usage(conn, "genai_image")
    return generated[0], "genai", []


async def source_scene_image(
    conn: sqlite3.Connection,
    scene: Scene,
    target_format: str,
    already_used: set[str],
    flux: StockImageEngine,
    pexels: StockImageEngine,
    pixabay: StockImageEngine,
    genai: StockImageEngine,
) -> tuple[ImageCandidate, str]:
    """Returns (chosen candidate, name of the engine that provided it)."""
    chosen, engine_used, _alternates = await source_scene_image_with_alternates(
        conn, scene, target_format, already_used, flux, pexels, pixabay, genai
    )
    return chosen, engine_used


async def download_candidate(candidate: ImageCandidate, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if candidate.image_bytes is not None:
        out_path.write_bytes(candidate.image_bytes)
        return
    if not candidate.url:
        raise ImageSourcingError("candidate has neither url nor image_bytes")
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(candidate.url)
        response.raise_for_status()
        out_path.write_bytes(response.content)


def _alternate_meta(candidates: list[ImageCandidate]) -> list[dict]:
    return [
        {
            "source": c.source,
            "source_id": c.source_id,
            "width": c.width,
            "height": c.height,
            "url": c.url,
            "photographer": c.photographer,
            "photographer_url": c.photographer_url,
        }
        for c in candidates
    ]


def _credit_meta(candidate: ImageCandidate, engine_used: str, alternates: list[ImageCandidate] | None = None) -> dict:
    return {
        "engine": engine_used,
        "source": candidate.source,
        "source_id": candidate.source_id,
        "width": candidate.width,
        "height": candidate.height,
        "url": candidate.url,
        "photographer": candidate.photographer,
        "photographer_url": candidate.photographer_url,
        "alternates": _alternate_meta(alternates or []),
    }


async def source_project_images(
    conn: sqlite3.Connection,
    project_id: str,
    scenes: list[Scene],
    target_format: str,
    images_dir: Path,
    flux: StockImageEngine,
    pexels: StockImageEngine,
    pixabay: StockImageEngine,
    genai: StockImageEngine,
) -> list[sqlite3.Row]:
    already_used: set[str] = set()
    results: list[sqlite3.Row] = []

    for scene in scenes:
        existing = conn.execute(
            "SELECT * FROM media_assets WHERE project_id = ? AND kind = 'image' AND scene_id = ?",
            (project_id, scene.id),
        ).fetchone()

        if existing is not None and not scene.visual_hint_stale:
            existing_meta = json.loads(existing["meta_json"] or "{}")
            already_used.add(existing_meta.get("source_id", ""))
            results.append(existing)
            continue

        candidate, engine_used, alternates = await source_scene_image_with_alternates(
            conn, scene, target_format, already_used, flux, pexels, pixabay, genai
        )
        already_used.add(candidate.source_id)

        out_path = images_dir / f"scene-{scene.id}.jpg"
        await download_candidate(candidate, out_path)
        meta_json = json.dumps(_credit_meta(candidate, engine_used, alternates), ensure_ascii=False)

        if existing is not None:
            conn.execute(
                "UPDATE media_assets SET path = ?, meta_json = ? WHERE id = ?",
                (str(out_path), meta_json, existing["id"]),
            )
            asset_id = existing["id"]
        else:
            asset_id = new_id()
            conn.execute(
                "INSERT INTO media_assets (id, project_id, kind, scene_id, path, meta_json) "
                "VALUES (?, ?, 'image', ?, ?, ?)",
                (asset_id, project_id, scene.id, str(out_path), meta_json),
            )
        conn.commit()
        results.append(conn.execute("SELECT * FROM media_assets WHERE id = ?", (asset_id,)).fetchone())

    return results


# --- Stale visual_hint batch refresh ---------------------------------------


def build_stale_hint_prompt(stale_scenes: list[Scene]) -> str:
    scenes_json = json.dumps(
        [{"id": s.id, "text": s.text} for s in stale_scenes], ensure_ascii=False, indent=2
    )
    return f"""For each scene below, write a concrete, photographable English visual_hint (2-5 words) describing what a stock photo search should show for this narration text. Respond with ONLY a JSON object mapping each scene id (as a string) to its visual_hint string, nothing else - no markdown, no explanation.

Scenes:
{scenes_json}
"""


def parse_hint_updates(raw: str) -> dict[int, str]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    updates = {}
    for key, value in data.items():
        if isinstance(value, str):
            try:
                updates[int(key)] = value
            except (TypeError, ValueError):
                continue
    return updates


async def refresh_stale_hints(llm: ScriptLLM, scenes: list[Scene]) -> list[Scene]:
    """One batch LLM call covering only stale scenes - cheap, and never
    touches scenes whose hint is already fresh.
    """
    stale = [s for s in scenes if s.visual_hint_stale]
    if not stale:
        return scenes

    raw = llm.generate_text(build_stale_hint_prompt(stale))
    updates = parse_hint_updates(raw)

    return [
        scene.model_copy(update={"visual_hint": updates[scene.id], "visual_hint_stale": False})
        if scene.id in updates
        else scene
        for scene in scenes
    ]
