import sys
import unittest
from pathlib import Path


GAMES_DIR = Path(__file__).resolve().parents[1] / "games"
sys.path.insert(0, str(GAMES_DIR))

# game_manager headless setup may have mocked `led` in sys.modules during
# collection of other tests; clear those so the real parser can import.
for _name in list(sys.modules):
    if _name == "led" or _name.startswith("led."):
        del sys.modules[_name]

from led.sensor_protocol import extract_frames, reversed_position_values  # noqa: E402


class SensorProtocolTests(unittest.TestCase):
    def test_complete_frame(self):
        frames, remainder, dropped = extract_frames(
            bytes([0xFC, 3, 5, 10, 5]),
            3,
        )
        self.assertEqual(frames, [bytes([5, 10, 5])])
        self.assertEqual(remainder, b"")
        self.assertEqual(dropped, 0)

    def test_split_frame_is_retained(self):
        frames, remainder, dropped = extract_frames(bytes([0xFC, 3, 5]), 3)
        self.assertEqual(frames, [])
        self.assertEqual(remainder, bytes([0xFC, 3, 5]))
        self.assertEqual(dropped, 0)

        frames, remainder, dropped = extract_frames(
            remainder + bytes([10, 5]),
            3,
        )
        self.assertEqual(frames, [bytes([5, 10, 5])])
        self.assertEqual(remainder, b"")
        self.assertEqual(dropped, 0)

    def test_concatenated_frames(self):
        frame = bytes([0xFC, 2, 5, 10])
        frames, remainder, dropped = extract_frames(frame + frame, 2)
        self.assertEqual(frames, [bytes([5, 10]), bytes([5, 10])])
        self.assertEqual(remainder, b"")
        self.assertEqual(dropped, 0)

    def test_garbage_and_wrong_length_resynchronize(self):
        data = bytes([1, 2, 0xFC, 9, 4, 0xFC, 2, 10, 5])
        frames, remainder, dropped = extract_frames(data, 2)
        self.assertEqual(frames, [bytes([10, 5])])
        self.assertEqual(remainder, b"")
        self.assertGreaterEqual(dropped, 4)

    def test_real_com_segment_lengths(self):
        for size in (52, 48, 32):
            payload = bytes([10 if i % 2 else 5 for i in range(size)])
            frames, remainder, dropped = extract_frames(
                bytes([0xFC, size]) + payload,
                size,
            )
            self.assertEqual(frames, [payload])
            self.assertEqual(remainder, b"")
            self.assertEqual(dropped, 0)

    def test_real_com_ranges_stay_within_132_tiles(self):
        configured_ranges = ((80, 52), (0, 48), (48, 32))
        decoded = []
        for start, size in configured_ranges:
            decoded.extend(
                index
                for index, _ in reversed_position_values(
                    bytes([5] * size),
                    start,
                    132,
                )
            )
        self.assertEqual(len(decoded), 132)
        self.assertEqual(set(decoded), set(range(132)))
        self.assertNotIn(132, decoded)

    def test_invalid_configured_range_is_rejected(self):
        with self.assertRaises(IndexError):
            list(reversed_position_values(bytes([5] * 53), 80, 132))


if __name__ == "__main__":
    unittest.main()
