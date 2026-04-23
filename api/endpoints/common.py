"""funcoes compartilhadas para resolver voice client e player."""

from fastapi import HTTPException

from services.playback import get_or_create_player


def get_voice_client(bot, guild_id: int | None = None):
    """Retorna voice client."""
    if guild_id is None:
        return bot.voice_clients[0] if len(bot.voice_clients) == 1 else None

    for vc in bot.voice_clients:
        if vc.guild.id == guild_id:
            return vc
    return None


def require_voice_client(bot, guild_id: int | None = None):
    """Exige voice client."""
    if guild_id is None:
        if not bot.voice_clients:
            raise HTTPException(
                status_code=400, detail="Bot não está em um canal de voz."
            )
        if len(bot.voice_clients) > 1:
            raise HTTPException(
                status_code=400,
                detail=(
                    "guild_id é obrigatório quando o bot está conectado em "
                    "múltiplos servidores."
                ),
            )

    vc = get_voice_client(bot, guild_id)
    if not vc:
        raise HTTPException(
            status_code=400, detail="Bot não está em um canal de voz."
        )
    return vc


def get_player_for_guild(bot, guild_id: int):
    """Retorna player for guild."""
    try:
        return get_or_create_player(bot, guild_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
