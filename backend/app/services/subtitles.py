"""Phrase grouping + ASS/SRT writers — specs/03-design/06-subtitle-timing.md.

Input is mode-agnostic absolute-timed word cues `[(word, abs_start_ms,
abs_end_ms)]`; offsetting per scene happens in callers (Mode A: one
whole-script TTS call already gives absolute times; Mode B offsets each
scene's relative timings by the scene's cumulative start before calling in).
"""
from dataclasses import dataclass
from pathlib import Path

from app.engines.tts.base import WordTiming

MAX_CHARS_PER_LINE = 42
MAX_LINES = 2
MAX_PHRASE_CHARS = MAX_CHARS_PER_LINE * MAX_LINES
MIN_DURATION_MS = 800
HANG_MS = 120

# Devanagari danda (।, ।।) + common Latin/Devanagari sentence punctuation.
SENTENCE_END_CHARS = ("।", ".", ",", "?", "!")

FONT_BY_LANGUAGE = {"hi": "Noto Sans Devanagari", "en": "Noto Sans"}

# 9:16 gets a larger font than 16:9 (mobile viewing) — specs/03-design/06-subtitle-timing.md.
FORMAT_STYLE = {
    "9x16": {"play_res_x": 1080, "play_res_y": 1920, "font_size": 64, "margin_v": 230, "margin_h": 60, "outline": 3, "shadow": 2},
    "16x9": {"play_res_x": 1920, "play_res_y": 1080, "font_size": 48, "margin_v": 130, "margin_h": 80, "outline": 2, "shadow": 1},
}

TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "assets" / "subtitle_template.ass"


@dataclass(frozen=True)
class WordCue:
    word: str
    start_ms: int
    end_ms: int


@dataclass(frozen=True)
class Phrase:
    text: str
    start_ms: int
    end_ms: int
    words: tuple[WordCue, ...]


def realign_with_source_text(
    source_text: str, timings: list[WordTiming], scene_offset_ms: int = 0
) -> list[WordCue]:
    """edge-tts's WordBoundary events strip punctuation from each word's
    `text` — confirmed by direct probe against the live service: a scene
    "...दोस्तों, आज..." comes back as WordBoundary text "दोस्तों" with the
    comma silently gone. The *source script text* (task-02's validated
    contract) is the real source of truth for punctuation, and phrase
    grouping's sentence-boundary splitting needs it back.

    Positional (whitespace-split) realignment is reliable here: token count
    and order match the TTS word stream one-to-one for validated script
    text, since task-02 already forbids the things that could desync it
    (digits, emoji, markdown, wrong-language fallback).

    `scene_offset_ms` shifts a per-scene-relative timing stream (Mode B)
    into the whole-render absolute timeline; Mode A's single whole-script
    TTS call already produces absolute times, so it passes 0 (default).
    """
    tokens = source_text.split()
    if len(tokens) != len(timings):
        # Fall back to the TTS-provided (punctuation-stripped) words rather
        # than raising - phrase grouping still works via the char-budget
        # path, just without punctuation-aware splits for this one scene.
        tokens = [t.word for t in timings]
    return [
        WordCue(
            word=token,
            start_ms=scene_offset_ms + t.offset_ms,
            end_ms=scene_offset_ms + t.offset_ms + t.duration_ms,
        )
        for token, t in zip(tokens, timings)
    ]


def group_into_phrases(words: list[WordCue]) -> list[Phrase]:
    if not words:
        return []

    groups = _split_at_punctuation(words)
    groups = _enforce_max_chars(groups)
    groups = _merge_short_groups(groups)

    phrases = [
        Phrase(text=" ".join(w.word for w in g), start_ms=g[0].start_ms, end_ms=g[-1].end_ms, words=tuple(g))
        for g in groups
    ]
    return _apply_hang_without_overlap(phrases)


def _split_at_punctuation(words: list[WordCue]) -> list[list[WordCue]]:
    groups: list[list[WordCue]] = []
    current: list[WordCue] = []
    for w in words:
        current.append(w)
        if w.word.rstrip().endswith(SENTENCE_END_CHARS):
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def _enforce_max_chars(groups: list[list[WordCue]]) -> list[list[WordCue]]:
    result: list[list[WordCue]] = []
    for group in groups:
        current: list[WordCue] = []
        for w in group:
            candidate_len = len(" ".join(x.word for x in [*current, w]))
            if current and candidate_len > MAX_PHRASE_CHARS:
                result.append(current)
                current = [w]
            else:
                current.append(w)
        if current:
            result.append(current)
    return result


def _merge_short_groups(groups: list[list[WordCue]]) -> list[list[WordCue]]:
    if len(groups) <= 1:
        return groups

    merged = [list(g) for g in groups]
    i = 0
    while i < len(merged) - 1:
        duration = merged[i][-1].end_ms - merged[i][0].start_ms
        if duration < MIN_DURATION_MS:
            merged[i + 1] = merged[i] + merged[i + 1]
            del merged[i]
            continue  # re-examine the newly merged group at this index
        i += 1

    if len(merged) > 1:
        last_duration = merged[-1][-1].end_ms - merged[-1][0].start_ms
        if last_duration < MIN_DURATION_MS:
            merged[-2] = merged[-2] + merged[-1]
            merged.pop()

    return merged


def _apply_hang_without_overlap(phrases: list[Phrase]) -> list[Phrase]:
    adjusted: list[Phrase] = []
    for i, p in enumerate(phrases):
        end = p.end_ms + HANG_MS
        if i + 1 < len(phrases):
            end = min(end, phrases[i + 1].start_ms)
        adjusted.append(Phrase(text=p.text, start_ms=p.start_ms, end_ms=end, words=p.words))
    return adjusted


# --- SRT -------------------------------------------------------------------


def _srt_timestamp(ms: int) -> str:
    hours, rem = divmod(max(ms, 0), 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def write_srt(phrases: list[Phrase]) -> str:
    blocks = [
        f"{i}\n{_srt_timestamp(p.start_ms)} --> {_srt_timestamp(p.end_ms)}\n{p.text}"
        for i, p in enumerate(phrases, start=1)
    ]
    return "\n\n".join(blocks) + "\n"


# --- ASS -------------------------------------------------------------------


def _ass_timestamp(ms: int) -> str:
    total_cs = round(max(ms, 0) / 10)
    hours, rem = divmod(total_cs, 360_000)
    minutes, rem = divmod(rem, 6_000)
    seconds, centiseconds = divmod(rem, 100)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"


def _ass_escape(text: str) -> str:
    # Guard against stray braces being read as override tags; our validated
    # script text (task-02) never contains markdown, but belt-and-braces.
    return text.replace("{", "").replace("}", "").replace("\n", "\\N")


def _dialogue_text(phrase: Phrase, karaoke: bool) -> str:
    if not karaoke:
        return _ass_escape(phrase.text)
    parts = []
    for w in phrase.words:
        centiseconds = max(1, round((w.end_ms - w.start_ms) / 10))
        parts.append(f"{{\\k{centiseconds}}}{_ass_escape(w.word)} ")
    return "".join(parts).strip()


def write_ass(
    phrases: list[Phrase], language: str, video_format: str, karaoke: bool = False
) -> str:
    """karaoke=True emits per-word `\\k` timing tags (open decision #3:
    off by default; phrase-at-a-time is the shipped default)."""
    style = FORMAT_STYLE[video_format]
    font = FONT_BY_LANGUAGE[language]

    events = "\n".join(
        f"Dialogue: 0,{_ass_timestamp(p.start_ms)},{_ass_timestamp(p.end_ms)},Default,,0,0,0,,{_dialogue_text(p, karaoke)}"
        for p in phrases
    )

    out = TEMPLATE_PATH.read_text(encoding="utf-8")
    tokens = {
        "PLAY_RES_X": style["play_res_x"],
        "PLAY_RES_Y": style["play_res_y"],
        "FONT_NAME": font,
        "FONT_SIZE": style["font_size"],
        "MARGIN_H": style["margin_h"],
        "MARGIN_V": style["margin_v"],
        "OUTLINE": style["outline"],
        "SHADOW": style["shadow"],
        "EVENTS": events,
    }
    for token, value in tokens.items():
        out = out.replace(f"%{token}%", str(value))
    return out
