"""Testes do fallback de URLs de mídia recusadas pelo YouTube."""

import unittest
from unittest.mock import patch

from utils.player_modules.playback import PlaybackMixin


class FakeYDL:
    def __init__(self, info):
        self.info = info
        self.params = {}

    def extract_info(self, _url, download=False):
        return self.info


class FakePlayer(PlaybackMixin):
    def __init__(self, primary_info):
        self.ydl = FakeYDL(primary_info)


class StreamResolutionTests(unittest.TestCase):
    def test_rejects_primary_403_and_uses_fallback(self):
        player = FakePlayer({"url": "https://bad.example/audio"})
        fallback = {
            "url": "https://good.example/audio",
            "http_headers": {"User-Agent": "test"},
        }

        def probe(url, _headers):
            if "bad.example" in url:
                raise OSError("HTTP Error 403: Forbidden")

        with (
            patch.object(player, "_probe_stream_url", side_effect=probe),
            patch(
                "utils.player_modules.playback._try_extract_with_clients",
                return_value=fallback,
            ) as fallback_extract,
        ):
            url, headers, info = player._resolve_stream_url("video-url")

        self.assertEqual(url, fallback["url"])
        self.assertEqual(headers, fallback["http_headers"])
        self.assertIs(info, fallback)
        fallback_extract.assert_called_once()

    def test_retry_offset_skips_primary_strategy(self):
        player = FakePlayer({"url": "https://bad.example/audio"})
        fallback = {"url": "https://good.example/audio"}

        with (
            patch.object(player, "_probe_stream_url"),
            patch(
                "utils.player_modules.playback._try_extract_with_clients",
                return_value=fallback,
            ),
        ):
            url, _headers, _info = player._resolve_stream_url(
                "video-url", strategy_offset=1
            )

        self.assertEqual(url, fallback["url"])


if __name__ == "__main__":
    unittest.main()
