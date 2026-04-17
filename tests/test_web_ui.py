import unittest


class WebUiHelpersTests(unittest.TestCase):
    def test_elapsed_time_formatting_examples_documented(self) -> None:
        # This keeps a tiny sanity check around the timing feature expectations.
        samples = {
            0.123: "123 ms",
            1.234: "1.23 s",
        }
        self.assertEqual(samples[0.123], "123 ms")
        self.assertEqual(samples[1.234], "1.23 s")
