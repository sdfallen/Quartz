import unittest

from advanced_controller import _extract_youtube_video_id


class YouTubeTests(unittest.TestCase):
    def test_extracts_first_video_id(self):
        page = (
            '{"videoId":"abcdefghijk"}'
            '{"videoId":"12345678901"}'
        )
        self.assertEqual(_extract_youtube_video_id(page), "abcdefghijk")

    def test_returns_none_when_results_are_absent(self):
        self.assertIsNone(_extract_youtube_video_id("no videos here"))


if __name__ == "__main__":
    unittest.main()
