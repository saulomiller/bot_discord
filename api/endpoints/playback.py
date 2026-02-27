import logging

from fastapi import APIRouter, HTTPException, Request

from api.endpoints.common import get_player_for_guild, require_voice_client
from api.endpoints.models import MusicRequest, VolumeRequest
from services.playback import enqueue_search, remove_playlist_entries

router = APIRouter()


@router.post("/api/play")
async def api_play(request: Request, body: MusicRequest, guild_id: int | None = None):
    """Add a track or playlist to queue and start playback when needed."""
    bot = request.app.state.bot
    vc = require_voice_client(bot, guild_id)
    player = get_player_for_guild(bot, vc.guild.id)

    try:
        result = await enqueue_search(player, body.search, bot.user, vc)
        song = result.get("song", {}) if isinstance(result, dict) else {}
        if result.get("is_playlist", False):
            song_title = song.get("title", "Playlist")
            return {
                "status": "success",
                "message": f"Playlist adicionada! Tocando: '{song_title}'. Processando resto em segundo plano...",
                "is_playlist": True,
            }

        return {
            "status": "success",
            "message": f"'{song.get('title', 'Música')}' adicionado à fila.",
            "is_playlist": False,
        }
    except Exception as exc:
        logging.error(f"API /play error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/skip")
async def api_skip(request: Request, guild_id: int | None = None):
    bot = request.app.state.bot
    vc = require_voice_client(bot, guild_id)
    player = get_player_for_guild(bot, vc.guild.id)
    player.skip()
    return {"status": "success", "message": "Música pulada."}


@router.post("/api/removeplaylist")
async def api_remove_playlist(request: Request, guild_id: int | None = None):
    """Remove playlist entries for one guild or all known players."""
    bot = request.app.state.bot
    if not getattr(bot, "players", None):
        return {"status": "success", "message": "Nenhum player encontrado."}

    if guild_id is not None:
        player = get_player_for_guild(bot, guild_id)
        removed, skipped_current = remove_playlist_entries(
            player,
            include_lazy=True,
            skip_current=True,
        )
        message_parts = []
        if skipped_current:
            message_parts.append("Pulei a música atual (era playlist).")
        if removed > 0:
            message_parts.append(f"Removidas {removed} músicas da fila.")
        if not message_parts:
            return {"status": "success", "message": "Nenhuma música de playlist encontrada para remover."}
        return {"status": "success", "message": " ".join(message_parts)}

    total_removed = 0
    skipped_current = False
    any_player = False

    for player in list(bot.players.values()):
        any_player = True
        removed, skipped = remove_playlist_entries(
            player,
            include_lazy=True,
            skip_current=True,
        )
        total_removed += removed
        skipped_current = skipped_current or skipped

    if not any_player:
        return {"status": "success", "message": "Nenhum player encontrado."}

    message_parts = []
    if skipped_current:
        message_parts.append("Pulei a música atual (era playlist).")
    if total_removed > 0:
        message_parts.append(f"Removidas {total_removed} músicas da fila.")

    if not message_parts:
        return {"status": "success", "message": "Nenhuma música de playlist encontrada para remover."}

    return {"status": "success", "message": " ".join(message_parts)}


@router.post("/api/pause")
async def api_pause(request: Request, guild_id: int | None = None):
    bot = request.app.state.bot
    vc = require_voice_client(bot, guild_id)
    player = get_player_for_guild(bot, vc.guild.id)
    player.pause()
    return {"status": "success", "message": "Música pausada."}


@router.post("/api/resume")
async def api_resume(request: Request, guild_id: int | None = None):
    bot = request.app.state.bot
    vc = require_voice_client(bot, guild_id)
    player = get_player_for_guild(bot, vc.guild.id)
    player.resume()
    return {"status": "success", "message": "Música retomada."}


@router.post("/api/volume")
async def api_volume(request: Request, body: VolumeRequest, guild_id: int | None = None):
    bot = request.app.state.bot

    if guild_id is not None:
        vc = require_voice_client(bot, guild_id)
        player = get_player_for_guild(bot, vc.guild.id)
        player.set_volume(body.level)
        return {
            "status": "success",
            "message": f"Volume ajustado para {int(body.level * 100)}%",
            "affected_players": 1,
        }

    count = 0
    for vc in bot.voice_clients:
        if vc.guild.id in bot.players:
            player = bot.players[vc.guild.id]
            player.set_volume(body.level)
            count += 1

    return {
        "status": "success",
        "message": f"Volume ajustado para {int(body.level * 100)}%",
        "affected_players": count,
    }
