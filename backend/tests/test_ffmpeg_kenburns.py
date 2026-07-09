import re

import pytest

from app.engines.ffmpeg.kenburns import (
    XFADE_S,
    SceneClip,
    build_audio_concat_filter,
    build_kenburns_filter_complex,
    clip_render_duration,
    total_timeline_duration_s,
)


class TestClipRenderDuration:
    def test_single_scene_has_no_padding(self):
        assert clip_render_duration(0, 1, 10.0) == 10.0

    def test_first_scene_gets_half_crossfade_padding(self):
        assert clip_render_duration(0, 3, 10.0) == pytest.approx(10.0 + XFADE_S / 2)

    def test_last_scene_gets_half_crossfade_padding(self):
        assert clip_render_duration(2, 3, 10.0) == pytest.approx(10.0 + XFADE_S / 2)

    def test_middle_scene_gets_full_crossfade_padding(self):
        assert clip_render_duration(1, 3, 10.0) == pytest.approx(10.0 + XFADE_S)

    def test_two_scene_case_each_gets_half_padding(self):
        assert clip_render_duration(0, 2, 5.0) == pytest.approx(5.0 + XFADE_S / 2)
        assert clip_render_duration(1, 2, 8.0) == pytest.approx(8.0 + XFADE_S / 2)


class TestTimelineMathAddsUpExactly:
    """The headline claim from specs/03-design/05-mode-b-pipeline.md: 'no
    drift possible because there is no second clock.' Verify the algebra:
    sum of padded clip durations minus all crossfade overlaps must equal
    exactly the sum of the original (unpadded) scene audio durations.
    """

    @pytest.mark.parametrize(
        "durations",
        [
            [10.0],
            [5.0, 7.0],
            [8.0, 6.0, 9.0],
            [3.2, 4.8, 2.1, 6.6, 5.0],
            [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
        ],
    )
    def test_padded_clips_minus_crossfades_equals_original_sum(self, durations):
        n = len(durations)
        padded_total = sum(clip_render_duration(i, n, d) for i, d in enumerate(durations))
        n_transitions = max(0, n - 1)
        assembled_length = padded_total - n_transitions * XFADE_S
        assert assembled_length == pytest.approx(sum(durations), abs=1e-9)

    @pytest.mark.parametrize(
        "durations", [[10.0], [5.0, 7.0], [8.0, 6.0, 9.0], [3.2, 4.8, 2.1, 6.6, 5.0]]
    )
    def test_total_timeline_duration_matches_audio_sum(self, durations):
        assert total_timeline_duration_s(durations) == pytest.approx(sum(durations))


class TestKenBurnsFilterComplex:
    def test_single_scene_uses_null_passthrough_no_xfade(self):
        clips = [SceneClip(index=0, image_path="scene-0.jpg", duration_s=10.0)]
        filter_complex, out_label = build_kenburns_filter_complex(clips, 1080, 1920)
        assert out_label == "vout"
        assert "xfade" not in filter_complex
        assert "[v0]null[vout]" in filter_complex

    def test_multi_scene_chains_xfade_with_correct_offsets(self):
        durations = [5.0, 7.0, 4.0]
        clips = [
            SceneClip(index=i, image_path=f"scene-{i}.jpg", duration_s=d)
            for i, d in enumerate(durations)
        ]
        filter_complex, out_label = build_kenburns_filter_complex(clips, 1080, 1920)
        assert out_label == "vout"

        xfade_calls = re.findall(r"xfade=transition=fade:duration=([\d.]+):offset=([\d.]+)", filter_complex)
        assert len(xfade_calls) == 2  # 3 scenes -> 2 transitions

        # First transition offset = clip 0's padded render duration - xfade.
        expected_offset_1 = clip_render_duration(0, 3, durations[0]) - XFADE_S
        assert float(xfade_calls[0][1]) == pytest.approx(expected_offset_1, abs=1e-2)

        # Second transition offset = cumulative timeline after first xfade, minus xfade.
        cumulative_after_first = (
            clip_render_duration(0, 3, durations[0])
            + clip_render_duration(1, 3, durations[1])
            - XFADE_S
        )
        expected_offset_2 = cumulative_after_first - XFADE_S
        assert float(xfade_calls[1][1]) == pytest.approx(expected_offset_2, abs=1e-2)

    def test_alternates_zoom_direction_per_scene(self):
        clips = [SceneClip(index=i, image_path=f"s{i}.jpg", duration_s=5.0) for i in range(4)]
        filter_complex, _ = build_kenburns_filter_complex(clips, 1080, 1920)
        # Even scenes zoom in (1+range*on/frames), odd scenes zoom out (MAX-range*on/frames).
        assert filter_complex.count("1+") >= 2  # scenes 0, 2
        assert "1.5-" in filter_complex  # scenes 1, 3 zoom-out form

    def test_rejects_empty_scene_list(self):
        with pytest.raises(ValueError):
            build_kenburns_filter_complex([], 1080, 1920)

    def test_resolution_baked_into_zoompan(self):
        clips = [SceneClip(index=0, image_path="s0.jpg", duration_s=5.0)]
        filter_complex, _ = build_kenburns_filter_complex(clips, 1080, 1920)
        assert "s=1080x1920" in filter_complex


class TestAudioConcatFilter:
    def test_concats_all_scene_audio_inputs_in_order(self):
        filter_str, label = build_audio_concat_filter(3, audio_input_start_index=3)
        assert label == "aout"
        assert filter_str == "[3:a][4:a][5:a]concat=n=3:v=0:a=1[aout]"

    def test_single_scene(self):
        filter_str, label = build_audio_concat_filter(1, audio_input_start_index=1)
        assert filter_str == "[1:a]concat=n=1:v=0:a=1[aout]"
