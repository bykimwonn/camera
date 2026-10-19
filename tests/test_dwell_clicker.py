import unittest

from core.dwell_clicker import DwellClicker


class DwellClickerTests(unittest.TestCase):
    def test_clicks_once_after_dwell_and_requires_rearm_motion(self):
        dwell = DwellClicker(dwell_seconds=1.0, radius_px=30, rearm_distance_px=70)
        self.assertFalse(dwell.update((100, 100), 0.0)[0])
        self.assertFalse(dwell.update((110, 105), .5)[0])
        clicked, progress, status = dwell.update((108, 103), 1.01)
        self.assertTrue(clicked)
        self.assertEqual(progress, 1.0)
        self.assertIn("LEFT CLICK", status)

        clicked, _, _ = dwell.update((110, 105), 2.2)
        self.assertFalse(clicked)
        clicked, _, _ = dwell.update((180, 103), 2.3)
        self.assertFalse(clicked)
        clicked, _, _ = dwell.update((180, 103), 3.31)
        self.assertTrue(clicked)

    def test_head_motion_resets_timer(self):
        dwell = DwellClicker(dwell_seconds=1.0, radius_px=25)
        dwell.update((0, 0), 0.0)
        dwell.update((0, 0), .7)
        clicked, progress, _ = dwell.update((40, 0), .8)
        self.assertFalse(clicked)
        self.assertEqual(progress, 0.0)
        clicked, _, _ = dwell.update((40, 0), 1.79)
        self.assertFalse(clicked)
        clicked, _, _ = dwell.update((40, 0), 1.81)
        self.assertTrue(clicked)

    def test_losing_face_cancels_in_progress_dwell(self):
        dwell = DwellClicker(dwell_seconds=1.0)
        dwell.update((0, 0), 0.0)
        dwell.update((0, 0), .7)
        dwell.face_lost()
        clicked, progress, _ = dwell.update((0, 0), 1.2)
        self.assertFalse(clicked)
        self.assertEqual(progress, 0.0)


if __name__ == "__main__":
    unittest.main()
