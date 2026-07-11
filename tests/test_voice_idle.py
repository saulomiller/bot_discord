"""Testes dos temporizadores de desconexao de voz."""

import asyncio
import unittest

from utils.player_modules.dashboard import DashboardMixin


class FakeMember:
    def __init__(self, *, bot=False):
        self.bot = bot


class FakeChannel:
    def __init__(self, members=None):
        self.members = members or []


class FakeVoiceClient:
    def __init__(self, members=None):
        self.channel = FakeChannel(members)
        self.connected = True
        self.disconnect_calls = 0

    def is_connected(self):
        return self.connected

    def is_playing(self):
        return False

    def is_paused(self):
        return False

    async def disconnect(self, *, force=False):
        self.disconnect_calls += 1
        self.connected = False


class FakePlayer(DashboardMixin):
    def __init__(self, voice_client):
        self.guild_id = 1
        self._voice_client = voice_client
        self.loop = asyncio.get_running_loop()
        self.queue = []
        self.current_song = None
        self.is_paused = False
        self.sfx_playing = False
        self._play_lock = asyncio.Lock()
        self._idle_disconnect_task = None
        self._alone_disconnect_task = None
        self._queue_empty_cleanup_task = None
        self._voice_idle_timeout_seconds = 0.01
        self.dashboard_task = None
        self.dashboard_message = None

    @property
    def voice_client(self):
        return self._voice_client

    @property
    def is_voice_busy(self):
        return False

    async def clear_music_dashboard(self):
        return None


class VoiceIdleTests(unittest.IsolatedAsyncioTestCase):
    async def test_disconnects_after_playback_inactivity(self):
        vc = FakeVoiceClient([FakeMember()])
        player = FakePlayer(vc)
        player._schedule_idle_disconnect()
        await asyncio.sleep(0.03)
        self.assertEqual(vc.disconnect_calls, 1)

    async def test_new_activity_cancels_idle_disconnect(self):
        vc = FakeVoiceClient([FakeMember()])
        player = FakePlayer(vc)
        player._schedule_idle_disconnect()
        player._cancel_idle_disconnect()
        await asyncio.sleep(0.03)
        self.assertEqual(vc.disconnect_calls, 0)

    async def test_disconnects_when_only_bots_remain(self):
        vc = FakeVoiceClient([FakeMember(bot=True)])
        player = FakePlayer(vc)
        player.schedule_alone_disconnect()
        await asyncio.sleep(0.03)
        self.assertEqual(vc.disconnect_calls, 1)

    async def test_does_not_disconnect_when_human_returns(self):
        vc = FakeVoiceClient([FakeMember()])
        player = FakePlayer(vc)
        player.schedule_alone_disconnect()
        await asyncio.sleep(0.03)
        self.assertEqual(vc.disconnect_calls, 0)


if __name__ == "__main__":
    unittest.main()
