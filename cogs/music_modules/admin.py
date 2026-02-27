"""Comandos administrativos do cog de musica."""

import logging

import discord
from discord.ext import commands

from utils.i18n import t

class MusicAdminMixin:
    """Mixin de comandos de musica."""

    @commands.command(name="sync")
    async def sync_commands(self, ctx: commands.Context):
        """ForÃ§a a sincronizaÃ§Ã£o dos comandos slash com o Discord"""
        try:
            if not ctx.author.guild_permissions.administrator:
                await ctx.send(embed=discord.Embed(title=t('error'), description=t('need_admin'), color=discord.Color.red()))
                return
                
            await ctx.send(embed=discord.Embed(title=t('syncing'), description=t('syncing'), color=discord.Color.blue()))
            synced = await self.bot.tree.sync()
            await ctx.send(embed=discord.Embed(title=t('success'), description=t('synced_commands', count=len(synced)), color=discord.Color.green()))
                
        except Exception as e:
            logging.error(f"Erro ao sincronizar: {e}")
            await ctx.send(embed=discord.Embed(title=t('error'), description=f"{t('error')}: {str(e)}", color=discord.Color.red()))
