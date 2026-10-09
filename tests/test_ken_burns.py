import unittest

from video.ken_burns_generator import (
    MOTION_CAP,
    MOTION_VERSION,
    OPTIMAL_SHOT_SECONDS,
    SLEEPY_ZOOM_END,
    SLEEPY_ZOOM_START,
    ZOOM_END,
    ZOOM_PRESCALE,
    ZOOM_START,
    interpolated_crop,
    ken_burns_frame_count,
    ken_burns_vf,
    motion_cache_key,
    pan_direction,
    required_shot_count,
)


def _center_x(img_w, img_h, t, clip_index):
    src_w, _src_h, x0, _y0 = interpolated_crop(img_w, img_h, t, clip_index)
    return x0 + src_w / 2.0


class KenBurnsPanTests(unittest.TestCase):
    def test_even_clips_pan_right_odd_clips_pan_left(self):
        self.assertEqual(pan_direction(0), "right")
        self.assertEqual(pan_direction(1), "left")
        self.assertEqual(pan_direction(2), "right")
        self.assertEqual(pan_direction(7), "left")

    def test_consecutive_clips_alternate_direction(self):
        for index in range(12):
            this_way = pan_direction(index)
            next_way = pan_direction(index + 1)
            self.assertNotEqual(this_way, next_way)
            self.assertEqual({this_way, next_way}, {"left", "right"})

    def test_crop_center_moves_only_one_way(self):
        img_w, img_h = 1344.0, 768.0
        samples = 48
        for clip_index, expected in ((0, "right"), (1, "left")):
            centers = [
                _center_x(img_w, img_h, i / (samples - 1), clip_index)
                for i in range(samples)
            ]
            deltas = [centers[i] - centers[i - 1] for i in range(1, len(centers))]
            self.assertTrue(all(d != 0 for d in deltas), clip_index)
            if expected == "right":
                self.assertTrue(all(d > 0 for d in deltas), deltas[:5])
                self.assertGreater(centers[-1], centers[0])
            else:
                self.assertTrue(all(d < 0 for d in deltas), deltas[:5])
                self.assertLess(centers[-1], centers[0])

    def test_adjacent_clips_pan_opposite_ways_on_the_image(self):
        img_w, img_h = 1344.0, 768.0
        right_delta = _center_x(img_w, img_h, 1.0, 0) - _center_x(img_w, img_h, 0.0, 0)
        left_delta = _center_x(img_w, img_h, 1.0, 1) - _center_x(img_w, img_h, 0.0, 1)
        self.assertGreater(right_delta, 0)
        self.assertLess(left_delta, 0)

    def test_vertical_center_stays_put(self):
        img_w, img_h = 1344.0, 768.0
        for clip_index in (0, 1):
            for t in (0.0, 0.5, 1.0):
                src_w, src_h, x0, y0 = interpolated_crop(img_w, img_h, t, clip_index)
                self.assertAlmostEqual(y0 + src_h / 2.0, img_h / 2.0, places=6)

    def test_window_stays_inside_the_image(self):
        img_w, img_h = 1344.0, 768.0
        for clip_index in (0, 1):
            for t in (0.0, 0.25, 0.5, 0.75, 1.0):
                src_w, src_h, x0, y0 = interpolated_crop(img_w, img_h, t, clip_index)
                self.assertGreaterEqual(x0, -1e-9)
                self.assertGreaterEqual(y0, -1e-9)
                self.assertLessEqual(x0 + src_w, img_w + 1e-9)
                self.assertLessEqual(y0 + src_h, img_h + 1e-9)

    def test_ffmpeg_filter_holds_end_crop_after_motion_cap(self):
        # 18s clip, motion finishes at OPTIMAL_SHOT_SECONDS and then holds.
        frames = ken_burns_frame_count(18.0, 24)
        vf = ken_burns_vf(1344, 768, 1280, 720, duration=18.0, clip_index=0)
        self.assertIn("zoompan=", vf)
        self.assertIn(f"iw*{ZOOM_PRESCALE}", vf)
        self.assertIn("s=1280x720", vf)
        self.assertIn(f"d={frames}:", vf)
        self.assertIn(f"min(1\\,on/{MOTION_CAP * 24:.6f})", vf)
        self.assertGreater(frames, int(MOTION_CAP * 24))

    def test_ffmpeg_filter_endpoints_match_interpolated_crop(self):
        img_w, img_h = 1344.0, 768.0
        sw0, _sh0, _x0, _y0 = interpolated_crop(img_w, img_h, 0.0, 0)
        sw1, _sh1, _x1, _y1 = interpolated_crop(img_w, img_h, 1.0, 0)
        vf = ken_burns_vf(img_w, img_h, 1920, 1080, duration=4.0, clip_index=0)
        self.assertIn(f"{ZOOM_START:.6f}", vf)
        self.assertIn(f"{ZOOM_END - ZOOM_START:.6f}", vf)
        self.assertIn("d=96:", vf)
        # Short clips share the shot-length timebase, so they do not finish the move.
        self.assertIn(f"min(1\\,on/{MOTION_CAP * 24:.6f})", vf)
        self.assertIn("(iw-iw/1.050000)*0.250000", vf)
        self.assertIn("(iw-iw/1.120000)*0.750000", vf)
        self.assertNotIn("(iw-iw/zoom)*min(1\\,on/", vf)
        vf_left = ken_burns_vf(img_w, img_h, 1920, 1080, duration=4.0, clip_index=1)
        self.assertIn("(iw-iw/1.050000)*0.750000", vf_left)
        self.assertIn("(iw-iw/1.120000)*0.250000", vf_left)
        self.assertGreater(sw0, sw1)

    def test_required_shots_follow_dubbed_audio(self):
        self.assertEqual(OPTIMAL_SHOT_SECONDS, 12.0)
        self.assertEqual(required_shot_count(0), 0)
        self.assertEqual(required_shot_count(12), 1)
        self.assertEqual(required_shot_count(12.1), 2)
        self.assertEqual(required_shot_count(60), 5)
        self.assertEqual(required_shot_count(90), 8)
        self.assertEqual(required_shot_count(5), 1)

    def test_frame_count_rounds_duration_to_fps(self):
        self.assertEqual(ken_burns_frame_count(4.0, 24), 96)
        self.assertEqual(ken_burns_frame_count(0.04, 24), 1)

    def test_motion_cache_key_tracks_math_version(self):
        key = motion_cache_key("auto", 24)
        self.assertEqual(key["motion_version"], MOTION_VERSION)
        self.assertEqual(key["motion_style"], "auto")
        self.assertNotEqual(key, motion_cache_key("static", 24))

    def test_sleepy_drift_is_three_to_five_percent_for_the_whole_clip(self):
        img_w, img_h = 1344.0, 768.0
        frames = ken_burns_frame_count(80.0, 24)
        vf = ken_burns_vf(
            img_w, img_h, 1920, 1080, duration=80.0, clip_index=0,
            nframes=frames, motion_style="sleepy",
        )
        self.assertIn(f"{SLEEPY_ZOOM_START:.6f}", vf)
        self.assertIn(f"{SLEEPY_ZOOM_END - SLEEPY_ZOOM_START:.6f}", vf)
        self.assertIn(f"min(1\\,on/{frames - 1:.6f})", vf)
        self.assertNotIn(f"min(1\\,on/{MOTION_CAP * 24:.6f})", vf)
        self.assertIn("(iw-iw/1.030000)*0.050000", vf)
        self.assertIn("(iw-iw/1.050000)*0.950000", vf)
        self.assertNotIn("1.120000", vf)
        vf_left = ken_burns_vf(
            img_w, img_h, 1920, 1080, duration=80.0, clip_index=1,
            motion_style="sleepy",
        )
        self.assertIn("(iw-iw/1.030000)*0.950000", vf_left)
        self.assertIn("(iw-iw/1.050000)*0.050000", vf_left)
        for clip_index, sign in ((0, 1.0), (1, -1.0)):
            start = interpolated_crop(img_w, img_h, 0.0, clip_index, motion_style="sleepy")
            mid = interpolated_crop(img_w, img_h, 0.5, clip_index, motion_style="sleepy")
            end = interpolated_crop(img_w, img_h, 1.0, clip_index, motion_style="sleepy")
            def center(crop):
                return crop[2] + crop[0] / 2.0
            travel = (center(end) - center(start)) / img_w
            self.assertGreater(sign * travel, 0.03)
            self.assertLess(sign * travel, 0.05)
            if sign > 0:
                self.assertLess(center(start), center(mid))
                self.assertLess(center(mid), center(end))
            else:
                self.assertGreater(center(start), center(mid))
                self.assertGreater(center(mid), center(end))
            self.assertGreaterEqual(start[2], -1e-6)
            self.assertLessEqual(start[2] + start[0], img_w + 1e-6)
            self.assertLessEqual(end[2] + end[0], img_w + 1e-6)
            self.assertAlmostEqual(start[3] + start[1] / 2.0, img_h / 2.0, places=6)
