"""implementa comandos de musica, fila, radios e controle de playback."""

from discord.ext import commands

from cogs.music_modules import (
    MusicAdminMixin,
    MusicBaseMixin,
    MusicConnectionMixin,
    MusicPlaybackMixin,
    MusicRadioMixin,
)

class MusicCog(
    MusicConnectionMixin,
    MusicPlaybackMixin,
    MusicRadioMixin,
    MusicAdminMixin,
    MusicBaseMixin,
    commands.Cog,
):
    """Cog principal que agrega comandos de musica por mixins."""

    FEEDBACK_DELETE_AFTER = 12

async def setup(bot):
    """Configura recursos necessarios para inicializacao."""
    await bot.add_cog(MusicCog(bot))
