"""Run the gesture tests without installing Home Assistant."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "custom_components" / "pawprint_light"))
from gesture import Gesture, decode


def play(samples):
    gesture = Gesture()
    return [
        action
        for time, pressed, x in samples
        if (action := gesture.feed(time, pressed, (x, 0, 0))) is not None
    ]


class GestureTests(unittest.TestCase):
    def test_decodes_signed_sensor_counts(self):
        self.assertEqual(
            decode(bytes([0xD0, 1, 2, 1, 0, 255, 0, 127, 0])),
            (True, (-1, 0, 127)),
        )

    def test_short_stationary_press_changes_color(self):
        self.assertEqual(play([(0, 0, 0), (0.1, 1, 0), (0.3, 0, 0)]), [("color", None)])

    def test_long_stationary_press_turns_off(self):
        self.assertEqual(
            play([(0, 0, 0), (0.1, 1, 0), (0.4, 1, 1), (0.7, 0, 1)]),
            [("off", None)],
        )

    def test_motion_after_hold_dims_without_a_second_action_on_release(self):
        self.assertEqual(
            play([
                (0, 0, 0), (0.1, 1, 0), (0.4, 1, -20), (0.7, 1, -60),
                (1, 1, 0), (1.3, 1, 60), (1.4, 0, 60),
            ]),
            [("brightness", 0), ("brightness", 50), ("brightness", 100)],
        )

    def test_ignores_press_already_in_progress_at_connect(self):
        self.assertEqual(play([(0, 1, 0), (0.3, 1, 0), (0.6, 0, 0)]), [])

    def test_discards_incomplete_press_after_interruption(self):
        self.assertEqual(play([(0, 0, 0), (0.1, 1, 0), (1.1, 0, 0)]), [])

    def test_ignores_short_press_with_large_movement(self):
        self.assertEqual(play([(0, 0, 0), (0.1, 1, 0), (0.3, 1, 20), (0.4, 0, 20)]), [])


if __name__ == "__main__":
    unittest.main()
