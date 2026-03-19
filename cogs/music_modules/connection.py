"""Comandos de conexao e gerenciamento de playlist no cog de musica."""

import logging

import discord
from discord import app_commands
from discord.ext import commands

from services.playback import remove_playlist_entries
from utils.embeds import EmbedBuilder
from utils.helpers import ensure_voice
from utils.i18n import t


class MusicConnectionMixin:
    """Mixin de comandos de musica."""

    async def _do_join(self, ctx_or_interaction):
        """Lógica interna de join."""
        # Se for interação, deferir se ainda não foi
        if isinstance(ctx_or_interaction, discord.Interaction):
            if not ctx_or_interaction.response.is_done():
                await ctx_or_interaction.response.defer(ephemeral=False)

        vc = await ensure_voice(ctx_or_interaction)
        if vc:
            embed = discord.Embed(
                title=t("connected"),
                description=t("joined_channel", channel=vc.channel.name),
                color=discord.Color.green(),
            )

            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.followup.send(embed=embed)
            else:
                await ctx_or_interaction.send(embed=embed)
        return vc

    @commands.command()
    async def join(self, ctx: commands.Context):
        """Executa a rotina de join."""
        await self._do_join(ctx)

    @app_commands.command(name="join", description="Joins the voice channel")
    async def join_slash(self, interaction: discord.Interaction):
        """Executa o comando slash de join."""
        await self._do_join(interaction)

    async def _do_leave(self, ctx_or_interaction):
        """Lógica interna de leave."""
        # Obter voice client
        guild = ctx_or_interaction.guild
        vc = guild.voice_client if guild else None

        if isinstance(ctx_or_interaction, discord.Interaction):
            if not ctx_or_interaction.response.is_done():
                await ctx_or_interaction.response.defer(ephemeral=False)

        if vc:
            await vc.disconnect()
            embed = discord.Embed(
                title=t("disconnected"),
                description=t("left_channel"),
                color=discord.Color.orange(),
            )
        else:
            embed = discord.Embed(
                title=t("error"),
                description=t("not_in_voice"),
                color=discord.Color.red(),
            )

        if isinstance(ctx_or_interaction, discord.Interaction):
            await ctx_or_interaction.followup.send(embed=embed)
        else:
            await ctx_or_interaction.send(embed=embed)

    @commands.command()
    async def leave(self, ctx: commands.Context):
        """Executa a rotina de leave."""
        await self._do_leave(ctx)

    @app_commands.command(name="leave", description="Leaves the voice channel")
    async def leave_slash(self, interaction: discord.Interaction):
        """Executa o comando slash de leave."""
        await self._do_leave(interaction)

    @commands.command(name="sair_todos")
    async def sair_todos(self, ctx: commands.Context):
        """Comando para sair de todos os canais de voz em todos os servidores"""
        count = 0
        for guild in self.bot.guilds:
            voice_client = guild.voice_client
            if voice_client and voice_client.is_connected():
                try:
                    if guild.id in self.bot.players:
                        self.bot.players[guild.id].stop()
                    await voice_client.disconnect(force=True)
                    count += 1
                except Exception as e:
                    logging.error(f"Erro ao desconectar de {guild.name}: {e}")

        if count > 0:
            await ctx.send(
                embed=discord.Embed(
                    title=t("disconnected"),
                    description=t("left_all_channels", count=count),
                    color=discord.Color.orange(),
                )
            )
        else:
            await ctx.send(
                embed=discord.Embed(
                    title=t("info"),
                    description=t("not_in_voice"),
                    color=discord.Color.blue(),
                )
            )

    async def _do_removeplaylist(self, ctx_or_interaction):
        guild_id = ctx_or_interaction.guild.id
        player = self.get_player(guild_id)
        removed, _ = remove_playlist_entries(
            player,
            include_lazy=True,
            skip_current=False,
        )

        embed = EmbedBuilder.create_success_embed(
            "Playlist removida", f"Removidas {removed} músicas da fila."
        )

        if isinstance(ctx_or_interaction, discord.Interaction):
            await ctx_or_interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await ctx_or_interaction.send(embed=embed)

    @commands.command(name="removeplaylist")
    async def removeplaylist(self, ctx: commands.Context):
        """Remove todas as músicas de playlists (adicionadas via playlist) da fila sem parar a música atual."""
        await self._do_removeplaylist(ctx)

    @app_commands.command(
        name="removeplaylist",
        description="Removes queued songs added from playlists",
    )
    async def removeplaylist_slash(self, interaction: discord.Interaction):
        """Executa o comando slash de removeplaylist."""
        await interaction.response.defer(ephemeral=True)
        await self._do_removeplaylist(interaction)
