"""Testes da extração leve usada antes da resolução do stream."""

import asyncio
import unittest

from utils.player_modules.extraction import ExtractionMixin


class FakeYDL:
    def __init__(self):
        self.calls = []

    def extract_info(self, search, **kwargs):
        self.calls.append((search, kwargs))
        return {
            "entries": [
                {
                    "title": "Faixa",
                    "url": "https://www.youtube.com/watch?v=video123",
                    "ie_key": "Youtube",
                    "duration": 120,
                }
            ]
        }


class FakePlayer(ExtractionMixin):
    def __init__(self):
        self.loop = asyncio.get_running_loop()
        self.ydl = FakeYDL()

    @staticmethod
    def _is_direct_stream_url(_url):
        return False


class ExtractionMetadataTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_skips_format_selection(self):
        player = FakePlayer()

        results = await player.extract_info("nome da música", max_entries=1)

        search, kwargs = player.ydl.calls[0]
        self.assertEqual(search, "ytsearch:nome da música")
        self.assertFalse(kwargs["download"])
        self.assertFalse(kwargs["process"])
        self.assertEqual(results[0][0], "Faixa")
        self.assertEqual(
            results[0][1], "https://www.youtube.com/watch?v=video123"
        )


if __name__ == "__main__":
    unittest.main()
