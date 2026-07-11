"""implementa comandos de musica, fila, radios e controle de playback."""

import discord
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

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        """Agenda a saida quando o bot fica sozinho no canal de voz."""
        if member.bot:
            return

        guild = member.guild
        vc = guild.voice_client
        if not vc or not vc.is_connected() or not vc.channel:
            return

        player = self.bot.players.get(guild.id)
        if not player:
            return

        humans = [
            voice_member
            for voice_member in vc.channel.members
            if not voice_member.bot
        ]
        if humans:
            player.cancel_alone_disconnect()
        else:
            player.schedule_alone_disconnect()


async def setup(bot):
    """Configura recursos necessarios para inicializacao."""
    await bot.add_cog(MusicCog(bot))
