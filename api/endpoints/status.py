"""endpoints de status do bot, player e fila atual."""

import logging

from fastapi import APIRouter, HTTPException, Request

from api.endpoints.common import get_voice_client
from utils.i18n import I18n

router = APIRouter()


def _resolve_status_voice_client(bot, guild_id: int | None):
    if guild_id is not None:
        return get_voice_client(bot, guild_id)
    if len(bot.voice_clients) <= 1:
        return get_voice_client(bot)
    raise HTTPException(
        status_code=400,
        detail="guild_id é obrigatório quando o bot está conectado em múltiplos servidores.",
    )


def _serialize_song(song):
    if not isinstance(song, dict):
        return {"title": str(song)}

    payload = dict(song)
    user_obj = payload.get("user")
    if hasattr(user_obj, "display_name"):
        payload["user"] = user_obj.display_name
    elif user_obj is None:
        payload["user"] = None
    else:
        payload["user"] = str(user_obj)
    return payload


@router.get("/api/guilds")
async def get_guilds(request: Request):
    """Return guild list and connection state for multi-server control."""
    bot = request.app.state.bot
    connected_by_guild = {vc.guild.id: vc for vc in bot.voice_clients}

    guilds = []
    for guild in bot.guilds:
        vc = connected_by_guild.get(guild.id)
        guilds.append(
            {
                "id": str(guild.id),
                "name": guild.name,
                "connected": vc is not None and vc.is_connected(),
                "voice_channel": vc.channel.name
                if vc and vc.channel
                else None,
                "member_count": guild.member_count,
            }
        )

    guilds.sort(
        key=lambda item: (not item["connected"], item["name"].casefold())
    )
    active_guild_id = next(
        (item["id"] for item in guilds if item["connected"]),
        guilds[0]["id"] if guilds else None,
    )

    return {
        "guilds": guilds,
        "active_guild_id": active_guild_id,
        "connected_guilds": sum(1 for item in guilds if item["connected"]),
    }


@router.get("/api/status")
async def get_status(request: Request, guild_id: int | None = None):
    """Return current bot status for dashboard."""
    bot = request.app.state.bot

    player = None
    vc = _resolve_status_voice_client(bot, guild_id)
    if vc and vc.guild.id in bot.players:
        player = bot.players[vc.guild.id]

    stat_current_song = None
    stat_queue = []
    stat_volume = 0.5
    stat_paused = False
    stat_loop = False
    stat_shuffle = False

    if player:
        stat_current_song = player.current_song
        stat_queue = player.queue
        stat_volume = player.volume
        stat_paused = player.is_paused
        stat_loop = player.is_looping
        stat_shuffle = player.is_shuffling

    current_song_info = None
    if stat_current_song:
        try:
            if isinstance(stat_current_song, dict):
                current_song_info = {
                    "title": stat_current_song.get("title", "Desconhecido"),
                    "thumbnail": stat_current_song.get("thumbnail", ""),
                    "user": str(stat_current_song.get("user", "Desconhecido")),
                    "duration": stat_current_song.get(
                        "duration", "Desconhecida"
                    ),
                    "channel": stat_current_song.get(
                        "channel", "Desconhecido"
                    ),
                }
                user_obj = stat_current_song.get("user")
                if hasattr(user_obj, "display_name"):
                    current_song_info["user"] = user_obj.display_name
        except Exception as exc:
            logging.error(f"Erro ao processar current_song: {exc}")
            current_song_info = {"title": "Erro ao ler música"}

    queue_info = []
    display_queue = list(stat_queue)[:10]
    for song in display_queue:
        try:
            if isinstance(song, dict):
                user_obj = song.get("user")
                user_name = (
                    user_obj.display_name
                    if hasattr(user_obj, "display_name")
                    else str(user_obj)
                )
                queue_info.append(
                    {
                        "title": song.get("title", "Desconhecido"),
                        "user": user_name,
                        "duration": song.get("duration", "?"),
                    }
                )
        except Exception:
            queue_info.append({"title": "Erro na fila"})

    return {
        "bot_user": str(bot.user),
        "is_ready": bot.is_ready(),
        "guilds": len(bot.guilds),
        "guild_id": str(vc.guild.id) if vc else None,
        "current_song": current_song_info,
        "queue": queue_info,
        "volume": stat_volume,
        "is_looping": stat_loop,
        "is_shuffling": stat_shuffle,
        "is_paused": stat_paused,
        "voice_connections": len(bot.voice_clients),
        "progress": player.get_progress()
        if player
        else {"current": 0, "duration": 0, "percent": 0},
        "language": I18n.get_instance().language,
    }


@router.get("/api/queue")
async def get_queue(request: Request, guild_id: int | None = None):
    """Return current queue."""
    bot = request.app.state.bot
    vc = _resolve_status_voice_client(bot, guild_id)
    if vc and vc.guild.id in bot.players:
        player = bot.players[vc.guild.id]
        return {
            "queue": [_serialize_song(song) for song in list(player.queue)]
        }
    return {"queue": []}
