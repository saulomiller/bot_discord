"""Comandos de radio do cog de musica."""

import logging
import re
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands

from utils.embeds import EmbedBuilder
from utils.helpers import ensure_voice, save_radios
from utils.i18n import t

RADIO_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")

class MusicRadioMixin:
    """Mixin de comandos de musica."""

    async def _do_list_radios(self, ctx_or_interaction):
        radios = self._radio_items()
        if not radios:
            msg = t('no_radios_found')
            if isinstance(ctx_or_interaction, discord.Interaction):
                 await ctx_or_interaction.response.send_message(msg)
            else:
                 await ctx_or_interaction.send(msg)
            return

        embed = discord.Embed(
            title=t('radios_available'),
            description=t('use_radio_command'),
            color=discord.Color.gold()
        )

        for radio in radios:
            radio_id = radio.get('id', '?')
            name = radio.get('name', radio_id)
            location = radio.get('location', t('unknown'))
            embed.add_field(name=f"{name} ({radio_id})", value=location, inline=True)

        if isinstance(ctx_or_interaction, discord.Interaction):
             await ctx_or_interaction.response.send_message(embed=embed)
        else:
             await ctx_or_interaction.send(embed=embed)

    @commands.command()
    async def radios(self, ctx: commands.Context):
        """Executa a rotina de radios."""
        await self._do_list_radios(ctx)

    @app_commands.command(name="radios", description="Lists available radio stations")
    async def radios_slash(self, interaction: discord.Interaction):
        """Executa o comando slash de radios."""
        await self._do_list_radios(interaction)

    async def _do_play_radio(self, ctx_or_interaction, radio_id: str):
         # Obter user para check de voz
        if isinstance(ctx_or_interaction, discord.Interaction):
            user = ctx_or_interaction.user
             # Defer se necessario
            if not ctx_or_interaction.response.is_done():
                 await ctx_or_interaction.response.defer(ephemeral=False)
        else:
             user = ctx_or_interaction.author

        if not user.voice:
             msg = t('user_must_be_in_voice')
             if isinstance(ctx_or_interaction, discord.Interaction):
                 await ctx_or_interaction.followup.send(msg, ephemeral=True)
             else:
                 await ctx_or_interaction.send(msg)
             return

        vc = await ensure_voice(ctx_or_interaction)
        if not vc: return

        radio_info = self._find_radio(radio_id)
        if not radio_info:
            embed = EmbedBuilder.create_error_embed(t('error'), t('radio_not_found'))
            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.followup.send(embed=embed)
            else:
                await ctx_or_interaction.send(embed=embed)
            return

        url = radio_info.get('url')
        if not url:
            embed = EmbedBuilder.create_error_embed(t('error'), t('invalid_url'))
            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.followup.send(embed=embed)
            else:
                await ctx_or_interaction.send(embed=embed)
            return

        guild_id = ctx_or_interaction.guild.id
        player = self.get_player(guild_id)

        try:
            # Trocar a fila atual para tocar a radio imediatamente.
            radio_song = {
                'title': radio_info.get('name', radio_id),
                'url': url,
                'thumbnail': radio_info.get('favicon'),
                'duration': t('live'),
                'duration_seconds': 0,
                'channel': 'Radio',
                'user': user,
                'is_radio': True,
                'is_lazy': False,
            }
            player.queue.clear()
            player.queue.append(radio_song)
            player.stream_cache.set(url, url)

            # Evita que callback de loop re-enfileire a musica anterior no switch.
            player.current_song = None

            # Se ja estiver tocando/pausado, stop dispara o callback after_play.
            # O callback chama play_next e inicia a radio que acabou de entrar na fila.
            if player.voice_client and (player.voice_client.is_playing() or player.voice_client.is_paused()):
                player.voice_client.stop()
            else:
                await player.play_next()

            embed_radio = EmbedBuilder.create_radio_embed(radio_info)
            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.followup.send(embed=embed_radio)
            else:
                await ctx_or_interaction.send(embed=embed_radio)

        except Exception as e:
             embed_err = EmbedBuilder.create_error_embed(t('error'), str(e))
             if isinstance(ctx_or_interaction, discord.Interaction):
                 await ctx_or_interaction.followup.send(embed=embed_err)
             else:
                 await ctx_or_interaction.send(embed=embed_err)

    @commands.command()
    async def radio(self, ctx: commands.Context, radio_id: str):
        """Executa a rotina de radio."""
        await self._do_play_radio(ctx, radio_id)

    @app_commands.command(name="radio", description="Plays a specific radio station")
    @app_commands.describe(radio_id="Radio ID")
    async def radio_slash(self, interaction: discord.Interaction, radio_id: str):
        """Executa o comando slash de radio."""
        await self._do_play_radio(interaction, radio_id)

    async def _do_add_radio(self, ctx_or_interaction, id: str, nome: str, url: str, localizacao: str = "Desconhecido"):
        # Check permissions
        if isinstance(ctx_or_interaction, discord.Interaction):
            user = ctx_or_interaction.user
        else:
            user = ctx_or_interaction.author

        if not user.guild_permissions.administrator:
            msg = t('need_admin')
            if isinstance(ctx_or_interaction, discord.Interaction):
                 await ctx_or_interaction.response.send_message(msg, ephemeral=True)
            else:
                 await ctx_or_interaction.send(msg)
            return

        radio_id = (id or '').strip().lower()
        nome = (nome or '').strip()
        url = (url or '').strip()
        localizacao = (localizacao or 'Desconhecido').strip() or 'Desconhecido'

        if not RADIO_ID_RE.fullmatch(radio_id):
            embed = EmbedBuilder.create_error_embed(
                t('error'),
                "ID invalido. Use apenas letras, numeros, '_' e '-', ate 64 caracteres.",
            )
            if isinstance(ctx_or_interaction, discord.Interaction):
                 await ctx_or_interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                 await ctx_or_interaction.send(embed=embed)
            return

        if len(nome.strip(" .-_")) < 2 or len(nome) > 80:
            embed = EmbedBuilder.create_error_embed(
                t('error'),
                "Nome invalido. Use de 2 a 80 caracteres.",
            )
            if isinstance(ctx_or_interaction, discord.Interaction):
                 await ctx_or_interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                 await ctx_or_interaction.send(embed=embed)
            return

        parsed = urlparse(url)
        if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
            embed = EmbedBuilder.create_error_embed(t('error'), t('invalid_url'))
            if isinstance(ctx_or_interaction, discord.Interaction):
                 await ctx_or_interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                 await ctx_or_interaction.send(embed=embed)
            return

        if len(localizacao) > 120:
            embed = EmbedBuilder.create_error_embed(
                t('error'),
                "Localizacao invalida. Maximo de 120 caracteres.",
            )
            if isinstance(ctx_or_interaction, discord.Interaction):
                 await ctx_or_interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                 await ctx_or_interaction.send(embed=embed)
            return

        if self._find_radio(radio_id):
            embed = EmbedBuilder.create_error_embed(t('error'), t('radio_exists', name=nome))
            if isinstance(ctx_or_interaction, discord.Interaction):
                 await ctx_or_interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                 await ctx_or_interaction.send(embed=embed)
            return

        duplicate = next(
            (
                radio for radio in self._radio_items()
                if str(radio.get('name', '')).casefold() == nome.casefold()
                or str(radio.get('url', '')).strip() == url
            ),
            None,
        )
        if duplicate:
            embed = EmbedBuilder.create_error_embed(
                t('error'),
                "Ja existe uma radio com o mesmo nome ou URL.",
            )
            if isinstance(ctx_or_interaction, discord.Interaction):
                 await ctx_or_interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                 await ctx_or_interaction.send(embed=embed)
            return

        radios = self._radio_items()
        radios.append({
            'id': radio_id,
            'name': nome,
            'url': url,
            'location': localizacao,
            'description': 'Radio personalizada',
            'custom': True,
        })
        self.RADIOS['radios'] = radios

        try:
            if not save_radios(self.RADIOS):
                raise RuntimeError('Falha ao persistir radios.')

            embed = EmbedBuilder.create_success_embed(t('radio_added'), t('radio_added_success', name=nome, id=radio_id))
            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.response.send_message(embed=embed)
            else:
                await ctx_or_interaction.send(embed=embed)

        except Exception as e:
            logging.error(f'Erro ao salvar radio: {e}')
            embed_err = EmbedBuilder.create_error_embed(t('error'), t('error_saving_radio'))
            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.response.send_message(embed=embed_err, ephemeral=True)
            else:
                await ctx_or_interaction.send(embed=embed_err)

    @app_commands.command(name="addradio", description="Adds a new custom radio (Admin)")
    @app_commands.describe(id="Unique ID for remote", nome="Radio Name", url="Stream URL", localizacao="Location (optional)")
    async def add_radio_slash(self, interaction: discord.Interaction, id: str, nome: str, url: str, localizacao: str = "Desconhecido"):
        """Executa o comando slash de add radio."""
        await self._do_add_radio(interaction, id, nome, url, localizacao)

    async def _do_remove_radio(self, ctx_or_interaction, id: str):
         # Check permissions
        if isinstance(ctx_or_interaction, discord.Interaction):
            user = ctx_or_interaction.user
        else:
            user = ctx_or_interaction.author

        if not user.guild_permissions.administrator:
            msg = t('need_admin')
            if isinstance(ctx_or_interaction, discord.Interaction):
                 await ctx_or_interaction.response.send_message(msg, ephemeral=True)
            else:
                 await ctx_or_interaction.send(msg)
            return

        radio_id = (id or '').strip().lower()
        if not RADIO_ID_RE.fullmatch(radio_id):
            embed = EmbedBuilder.create_error_embed(
                t('error'),
                "ID invalido. Use apenas letras, numeros, '_' e '-', ate 64 caracteres.",
            )
            if isinstance(ctx_or_interaction, discord.Interaction):
                 await ctx_or_interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                 await ctx_or_interaction.send(embed=embed)
            return
        radios = self._radio_items()
        target_radio = None
        for radio in radios:
            if str(radio.get('id', '')).strip().lower() == radio_id:
                target_radio = radio
                break

        if not target_radio:
            embed = EmbedBuilder.create_error_embed(t('error'), t('radio_not_found'))
            if isinstance(ctx_or_interaction, discord.Interaction):
                 await ctx_or_interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                 await ctx_or_interaction.send(embed=embed)
            return

        name = target_radio.get('name', radio_id)
        self.RADIOS['radios'] = [
            radio for radio in radios
            if str(radio.get('id', '')).strip().lower() != radio_id
        ]

        try:
            if not save_radios(self.RADIOS):
                raise RuntimeError('Falha ao persistir radios.')

            embed = EmbedBuilder.create_success_embed(t('radio_removed'), t('radio_removed_success', name=name))
            if isinstance(ctx_or_interaction, discord.Interaction):
                 await ctx_or_interaction.response.send_message(embed=embed)
            else:
                 await ctx_or_interaction.send(embed=embed)
        except Exception as e:
            logging.error(f'Erro ao remover radio: {e}')
            embed_err = EmbedBuilder.create_error_embed(t('error'), t('error_removing_radio'))
            if isinstance(ctx_or_interaction, discord.Interaction):
                 await ctx_or_interaction.response.send_message(embed=embed_err, ephemeral=True)
            else:
                 await ctx_or_interaction.send(embed=embed_err)

    @app_commands.command(name="removeradio", description="Removes an existing radio (Admin)")
    @app_commands.describe(id="ID of the radio to remove")
    async def remove_radio_slash(self, interaction: discord.Interaction, id: str):
        """Executa o comando slash de remove radio."""
        await self._do_remove_radio(interaction, id)
