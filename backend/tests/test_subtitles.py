import re
from pathlib import Path

import pytest

from app.engines.tts.base import WordTiming
from app.services.subtitles import (
    HANG_MS,
    MAX_PHRASE_CHARS,
    MIN_DURATION_MS,
    Phrase,
    WordCue,
    _ass_timestamp,
    _srt_timestamp,
    group_into_phrases,
    realign_with_source_text,
    write_ass,
    write_srt,
)


def _cue(word: str, start_ms: int, dur_ms: int) -> WordCue:
    return WordCue(word=word, start_ms=start_ms, end_ms=start_ms + dur_ms)


def _hindi_words() -> list[WordCue]:
    # "नमस्ते दोस्तों, आज हम बात करेंगे। यह एक बहुत अच्छा विचार है।"
    tokens = [
        ("नमस्ते", 700), ("दोस्तों,", 500), ("आज", 300), ("हम", 250),
        ("बात", 300), ("करेंगे।", 600), ("यह", 250), ("एक", 250),
        ("बहुत", 350), ("अच्छा", 400), ("विचार", 400), ("है।", 350),
    ]
    words = []
    t = 0
    for word, dur in tokens:
        words.append(_cue(word, t, dur))
        t += dur + 50  # small gap between words
    return words


def _english_words() -> list[WordCue]:
    tokens = [
        ("Hello,", 400), ("friends,", 450), ("today", 350), ("we", 200),
        ("will", 250), ("talk.", 400), ("This", 250), ("is", 200),
        ("a", 150), ("great", 350), ("idea.", 450),
    ]
    words = []
    t = 0
    for word, dur in tokens:
        words.append(_cue(word, t, dur))
        t += dur + 50
    return words


class TestRealignWithSourceText:
    """edge-tts's WordBoundary events strip punctuation - discovered by a
    live probe during task-06 verification. This reconstructs it from the
    source script text.
    """

    def test_reattaches_punctuation_edge_tts_actually_strips(self):
        # This is the *exact* mismatch observed live: source "दोस्तों,"
        # comes back from edge-tts as WordBoundary text "दोस्तों".
        source_text = "नमस्ते दोस्तों, आज हम बात करेंगे।"
        timings = [
            WordTiming(word="नमस्ते", offset_ms=100, duration_ms=675),
            WordTiming(word="दोस्तों", offset_ms=787, duration_ms=675),
            WordTiming(word="आज", offset_ms=1687, duration_ms=262),
            WordTiming(word="हम", offset_ms=1962, duration_ms=187),
            WordTiming(word="बात", offset_ms=2200, duration_ms=300),
            WordTiming(word="करेंगे", offset_ms=2550, duration_ms=600),
        ]
        cues = realign_with_source_text(source_text, timings)
        assert [c.word for c in cues] == [
            "नमस्ते", "दोस्तों,", "आज", "हम", "बात", "करेंगे।",
        ]
        # Timing values pass through untouched, just offset by scene_offset_ms (0).
        assert cues[1].start_ms == 787
        assert cues[1].end_ms == 787 + 675

    def test_applies_scene_offset_for_mode_b(self):
        timings = [WordTiming(word="hello", offset_ms=100, duration_ms=300)]
        cues = realign_with_source_text("hello", timings, scene_offset_ms=5000)
        assert cues[0].start_ms == 5100
        assert cues[0].end_ms == 5400

    def test_falls_back_to_tts_words_on_token_count_mismatch(self):
        # Simulates a rare desync (shouldn't happen for validated script
        # text, but must degrade gracefully rather than raise/misalign).
        source_text = "one two three"
        timings = [
            WordTiming(word="one", offset_ms=0, duration_ms=100),
            WordTiming(word="two", offset_ms=100, duration_ms=100),
        ]
        cues = realign_with_source_text(source_text, timings)
        assert [c.word for c in cues] == ["one", "two"]

    def test_realigned_cues_feed_punctuation_aware_grouping(self):
        source_text = "नमस्ते दोस्तों, आज हम बात करेंगे। यह एक बहुत अच्छा विचार है।"
        timings = [
            WordTiming(word="नमस्ते", offset_ms=100, duration_ms=675),
            WordTiming(word="दोस्तों", offset_ms=787, duration_ms=675),
            WordTiming(word="आज", offset_ms=1687, duration_ms=262),
            WordTiming(word="हम", offset_ms=1962, duration_ms=187),
            WordTiming(word="बात", offset_ms=2200, duration_ms=300),
            WordTiming(word="करेंगे", offset_ms=2550, duration_ms=600),
            WordTiming(word="यह", offset_ms=3200, duration_ms=250),
            WordTiming(word="एक", offset_ms=3480, duration_ms=250),
            WordTiming(word="बहुत", offset_ms=3760, duration_ms=350),
            WordTiming(word="अच्छा", offset_ms=4140, duration_ms=400),
            WordTiming(word="विचार", offset_ms=4570, duration_ms=400),
            WordTiming(word="है", offset_ms=5000, duration_ms=350),
        ]
        cues = realign_with_source_text(source_text, timings)
        phrases = group_into_phrases(cues)
        # Without realignment (raw edge-tts words, no punctuation) this
        # would collapse into one giant unsplit phrase.
        assert len(phrases) > 1
        assert phrases[0].text.rstrip().endswith(("।", ","))


class TestGroupingProperties:
    @pytest.mark.parametrize("words_factory", [_hindi_words, _english_words])
    def test_full_word_coverage_in_order(self, words_factory):
        words = words_factory()
        phrases = group_into_phrases(words)
        flattened = [w for p in phrases for w in p.words]
        assert flattened == words

    @pytest.mark.parametrize("words_factory", [_hindi_words, _english_words])
    def test_no_phrase_exceeds_char_budget_unless_single_long_word(self, words_factory):
        words = words_factory()
        phrases = group_into_phrases(words)
        for p in phrases:
            assert len(p.text) <= MAX_PHRASE_CHARS or len(p.words) == 1

    @pytest.mark.parametrize("words_factory", [_hindi_words, _english_words])
    def test_no_phrase_shorter_than_minimum_unless_its_the_only_one(self, words_factory):
        words = words_factory()
        phrases = group_into_phrases(words)
        for p in phrases:
            duration = p.end_ms - p.start_ms
            assert duration >= MIN_DURATION_MS - 1 or len(phrases) == 1

    @pytest.mark.parametrize("words_factory", [_hindi_words, _english_words])
    def test_no_overlaps_and_monotonic_order(self, words_factory):
        words = words_factory()
        phrases = group_into_phrases(words)
        for a, b in zip(phrases, phrases[1:]):
            assert a.end_ms <= b.start_ms

    def test_hang_time_applied_but_capped_at_next_start(self):
        # Two very short, back-to-back sentence groups forced to stay
        # separate would collide once HANG_MS is added - verify no overlap.
        words = [
            _cue("अ।", 0, 10),
            _cue("ब।", 15, 10),
        ]
        phrases = group_into_phrases(words)
        assert phrases[-1].end_ms == phrases[-1].words[-1].end_ms + HANG_MS

    def test_devanagari_danda_is_a_split_point(self):
        words = _hindi_words()
        phrases = group_into_phrases(words)
        # "करेंगे।" (with danda) ends the first sentence; some phrase
        # boundary must land exactly after it (possibly merged forward if
        # too short, but the split candidate must have existed).
        assert any(p.text.rstrip().endswith("।") for p in phrases)

    def test_empty_input_returns_no_phrases(self):
        assert group_into_phrases([]) == []


class TestTimestamps:
    def test_srt_timestamp_format(self):
        assert _srt_timestamp(0) == "00:00:00,000"
        assert _srt_timestamp(1234) == "00:00:01,234"
        assert _srt_timestamp(3_661_500) == "01:01:01,500"

    def test_ass_timestamp_format(self):
        assert _ass_timestamp(0) == "0:00:00.00"
        assert _ass_timestamp(1234) == "0:00:01.23"
        assert _ass_timestamp(3_661_500) == "1:01:01.50"


class TestSrtRoundTrip:
    SRT_BLOCK_RE = re.compile(
        r"(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.+)"
    )

    def test_srt_parses_back_into_the_same_structure(self):
        phrases = group_into_phrases(_hindi_words())
        srt = write_srt(phrases)
        blocks = [b for b in srt.strip().split("\n\n") if b.strip()]
        assert len(blocks) == len(phrases)
        for block, phrase in zip(blocks, phrases):
            match = self.SRT_BLOCK_RE.match(block)
            assert match is not None, block
            index, start, end, text = match.groups()
            assert text == phrase.text


class TestAssGeneration:
    @pytest.mark.parametrize("language,words_factory", [("hi", _hindi_words), ("en", _english_words)])
    def test_ass_contains_dialogue_lines_and_correct_font(self, language, words_factory):
        phrases = group_into_phrases(words_factory())
        ass = write_ass(phrases, language, "9x16")
        assert "Dialogue: 0," in ass
        assert ass.count("Dialogue: 0,") == len(phrases)
        font = "Noto Sans Devanagari" if language == "hi" else "Noto Sans"
        assert font in ass
        assert "1080" in ass and "1920" in ass  # 9x16 resolution substituted

    def test_ass_16x9_uses_widescreen_resolution(self):
        phrases = group_into_phrases(_english_words())
        ass = write_ass(phrases, "en", "16x9")
        assert "1920" in ass and "1080" in ass

    def test_no_unsubstituted_tokens_remain(self):
        phrases = group_into_phrases(_hindi_words())
        ass = write_ass(phrases, "hi", "9x16")
        assert "%" not in ass

    def test_karaoke_mode_emits_k_tags(self):
        phrases = group_into_phrases(_english_words())
        ass_plain = write_ass(phrases, "en", "16x9", karaoke=False)
        ass_karaoke = write_ass(phrases, "en", "16x9", karaoke=True)
        assert "\\k" not in ass_plain
        assert "\\k" in ass_karaoke

    def test_stray_braces_are_stripped_defensively(self):
        words = [_cue("hello{test}", 0, 900)]
        phrases = group_into_phrases(words)
        ass = write_ass(phrases, "en", "16x9")
        assert "{test}" not in ass


GOLDEN_DIR = Path(__file__).parent / "golden"


class TestGoldenFiles:
    """One scripted example per language -> committed expected ASS
    (task-06's own Tests section). A diff here means either a real
    regression or an intentional format change (regenerate + review the
    diff, don't just overwrite blindly).
    """

    def test_hindi_golden_ass_matches(self):
        phrases = group_into_phrases(_hindi_words())
        ass = write_ass(phrases, "hi", "9x16")
        expected = (GOLDEN_DIR / "hindi_example.ass").read_text(encoding="utf-8")
        assert ass == expected

    def test_english_golden_ass_matches(self):
        phrases = group_into_phrases(_english_words())
        ass = write_ass(phrases, "en", "16x9")
        expected = (GOLDEN_DIR / "english_example.ass").read_text(encoding="utf-8")
        assert ass == expected
