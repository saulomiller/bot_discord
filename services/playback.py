from __future__ import annotations

from typing import Any


PLAYLIST_INDICATORS = (
    "/playlist",
    "/playlist/",
    "/sets/",
    "list=",
    "/album/",
)


def is_playlist_query(search: str) -> bool:
    if not search:
        return False
    if not search.startswith(("http://", "https://")):
        return False
    lowered = search.lower()
    return any(indicator in lowered for indicator in PLAYLIST_INDICATORS)


def get_or_create_player(bot: Any, guild_id: int):
    if guild_id in bot.players:
        return bot.players[guild_id]

    music_cog = bot.get_cog("MusicCog")
    if not music_cog:
        raise RuntimeError("MusicCog não carregado.")
    return music_cog.get_player(guild_id)


async def enqueue_search(player: Any, search: str, user: Any, voice_client: Any = None) -> dict:
    is_playlist = is_playlist_query(search)
    if is_playlist:
        song = await player.add_playlist_async(search, user)
        return {"is_playlist": True, "song": song}

    song = await player.add_to_queue(search, user)
    vc = voice_client or getattr(player, "voice_client", None)
    if vc and not vc.is_playing() and not player.is_paused:
        await player.play_next()
    return {"is_playlist": False, "song": song}


def remove_playlist_entries(player: Any, *, include_lazy: bool, skip_current: bool) -> tuple[int, bool]:
    skipped_current = False
    if skip_current and isinstance(player.current_song, dict):
        current_is_playlist = player.current_song.get("channel") == "Playlist"
        current_is_lazy = bool(player.current_song.get("is_lazy", False)) if include_lazy else False
        if current_is_playlist or current_is_lazy:
            player.skip()
            skipped_current = True

    retained = []
    removed = 0
    for song in list(player.queue):
        is_playlist_item = False
        if isinstance(song, dict):
            is_playlist_item = song.get("channel") == "Playlist"
            if include_lazy:
                is_playlist_item = is_playlist_item or bool(song.get("is_lazy", False))
        if is_playlist_item:
            removed += 1
        else:
            retained.append(song)

    if removed:
        player.queue.clear()
        for item in retained:
            player.queue.append(item)

    return removed, skipped_current

