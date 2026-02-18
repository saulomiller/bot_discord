import discord
from discord.ext import commands
from discord import app_commands
import logging
import asyncio
import os
import json
from utils.player import MusicPlayer
from config import RADIOS_FILE, PLAYLIST_DIR, DATA_DIR, FFMPEG_PATH
from utils.embeds import EmbedBuilder
from utils.helpers import ensure_voice, check_system_resources, load_radios
from utils.image import get_dominant_color, create_now_playing_card
from utils.i18n import t
from io import BytesIO

class MusicCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.RADIOS = load_radios()
        self.playlist_processing_task = None
        self.playlist_cancel_flag = False

    def get_player(self, guild_id) -> MusicPlayer:
        if guild_id not in self.bot.players:
            self.bot.players[guild_id] = MusicPlayer(guild_id, self.bot)
        return self.bot.players[guild_id]

    # --- Comandos de Conexão ---

    async def _do_join(self, ctx_or_interaction):
        """Lógica interna de join."""
        # Se for interação, deferir se ainda não foi
        if isinstance(ctx_or_interaction, discord.Interaction):
            if not ctx_or_interaction.response.is_done():
                 await ctx_or_interaction.response.defer(ephemeral=False)
            
        vc = await ensure_voice(ctx_or_interaction)
        if vc:
            embed = discord.Embed(
                title=t('connected'),
                description=t('joined_channel', channel=vc.channel.name),
                color=discord.Color.green()
            )
            
            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.followup.send(embed=embed)
            else:
                await ctx_or_interaction.send(embed=embed)
        return vc

    @commands.command()
    async def join(self, ctx: commands.Context):
        await self._do_join(ctx)

    @app_commands.command(name="join", description="Joins the voice channel")
    async def join_slash(self, interaction: discord.Interaction):
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
                title=t('disconnected'),
                description=t('left_channel'),
                color=discord.Color.orange()
            )
        else:
            embed = discord.Embed(
                title=t('error'),
                description=t('not_in_voice'),
                color=discord.Color.red()
            )
        
        if isinstance(ctx_or_interaction, discord.Interaction):
            await ctx_or_interaction.followup.send(embed=embed)
        else:
            await ctx_or_interaction.send(embed=embed)

    @commands.command()
    async def leave(self, ctx: commands.Context):
        await self._do_leave(ctx)

    @app_commands.command(name="leave", description="Leaves the voice channel")
    async def leave_slash(self, interaction: discord.Interaction):
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
            await ctx.send(embed=discord.Embed(
                title=t('disconnected'),
                description=t('left_all_channels', count=count),
                color=discord.Color.orange()))
        else:
            await ctx.send(embed=discord.Embed(
                title=t('info'),
                description=t('not_in_voice'),
                color=discord.Color.blue()))

    async def _do_removeplaylist(self, ctx_or_interaction):
        guild_id = ctx_or_interaction.guild.id
        player = self.get_player(guild_id)
        
        retained = []
        removed = 0
        for song in list(player.queue):
            if song.get('channel') == 'Playlist':
                removed += 1
            else:
                retained.append(song)

        player.queue.clear()
        for s in retained:
            player.queue.append(s)

        embed = EmbedBuilder.create_success_embed(
            "Playlist removida",
            f"Removidas {removed} músicas da fila."
        )
        
        if isinstance(ctx_or_interaction, discord.Interaction):
            await ctx_or_interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await ctx_or_interaction.send(embed=embed)

    @commands.command(name="removeplaylist")
    async def removeplaylist(self, ctx: commands.Context):
        """Remove todas as músicas de playlists (adicionadas via playlist) da fila sem parar a música atual."""
        await self._do_removeplaylist(ctx)
    
    @app_commands.command(name="removeplaylist", description="Removes queued songs added from playlists")
    async def removeplaylist_slash(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self._do_removeplaylist(interaction)

    # --- Comandos de Reprodução ---

    async def _do_play(self, ctx_or_interaction, search: str):
        # 1. Obter User e Guild
        if isinstance(ctx_or_interaction, discord.Interaction):
            user = ctx_or_interaction.user
            guild = ctx_or_interaction.guild
            # Defer se necessário
            if not ctx_or_interaction.response.is_done():
                 await ctx_or_interaction.response.defer(ephemeral=False)
        else:
            user = ctx_or_interaction.author
            guild = ctx_or_interaction.guild

        # 2. Verificar Voz
        if not user.voice:
            msg = t('user_must_be_in_voice')
            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.followup.send(msg, ephemeral=True)
            else:
                await ctx_or_interaction.send(msg)
            return

        try:
            vc = await ensure_voice(ctx_or_interaction)
            if not vc: return
        except Exception as e:
            embed = EmbedBuilder.create_error_embed(t('error'), f"Erro de conexão: {str(e)}")
            if isinstance(ctx_or_interaction, discord.Interaction):
                 await ctx_or_interaction.followup.send(embed=embed)
            else:
                 await ctx_or_interaction.send(embed=embed)
            return

        # 3. Obter Player
        player = self.get_player(guild.id)
        player.dashboard_context = ctx_or_interaction # Vincular canal
        
        # 4. Verificar Playlist
        is_playlist = False
        if 'list=' in search or '/sets/' in search or '/album/' in search or '/playlist/' in search:
            is_playlist = True

        if is_playlist:
            if self.playlist_processing_task and not self.playlist_processing_task.done():
                embed = EmbedBuilder.create_error_embed(t('error'), "Já existe uma playlist sendo processada. Aguarde.")
                if isinstance(ctx_or_interaction, discord.Interaction):
                    await ctx_or_interaction.followup.send(embed=embed)
                else:
                    await ctx_or_interaction.send(embed=embed)
                return

            embed_info = EmbedBuilder.create_info_embed(t('processing_playlist'), t('extracting_playlist'))
            if isinstance(ctx_or_interaction, discord.Interaction):
                status_msg = await ctx_or_interaction.followup.send(embed=embed_info)
            else:
                status_msg = await ctx_or_interaction.send(embed=embed_info)
            
            try:
                await player.add_playlist_async(search, user)
                embed_success = EmbedBuilder.create_success_embed(t('playlist_added'), t('processing_background', title="Playlist"))
                if isinstance(ctx_or_interaction, discord.Interaction):
                    await ctx_or_interaction.followup.send(embed=embed_success)
                else:
                    await status_msg.edit(embed=embed_success)
            except Exception as e:
                embed_err = EmbedBuilder.create_error_embed(t('error'), str(e))
                if isinstance(ctx_or_interaction, discord.Interaction):
                     await ctx_or_interaction.followup.send(embed=embed_err)
                else:
                     await status_msg.edit(embed=embed_err)
            return

        # 5. Busca Normal
        searches = search.split(";")
        if len(searches) > 1:
            embed_multi = EmbedBuilder.create_info_embed(t('adding_songs', count=len(searches)))
            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.followup.send(embed=embed_multi)
            else:
                await ctx_or_interaction.send(embed=embed_multi)
        
        for query in searches:
            query = query.strip()
            if not query: continue
            
            try:
                await player.add_to_queue(query, user)
                
                if not player.is_playing:
                    await player.play_next()
                else:
                    # Notificar adição à fila (apenas se for 1 música para não spammar)
                    if len(searches) == 1:
                         pos = len(player.queue)
                         last_song = player.queue[-1]
                         embed_added = EmbedBuilder.create_info_embed(
                             t('added_to_queue'), 
                             f"🎵 **{last_song.get('title')}**\n{t('position_in_queue', position=pos)}"
                         )
                         if isinstance(ctx_or_interaction, discord.Interaction):
                             await ctx_or_interaction.followup.send(embed=embed_added)
                         else:
                             await ctx_or_interaction.send(embed=embed_added)

            except Exception as e:
                logging.error(f"Erro no play: {e}")
                embed_err = EmbedBuilder.create_error_embed(t('error'), f"Erro ao adicionar: {query} - {str(e)}")
                if isinstance(ctx_or_interaction, discord.Interaction):
                    await ctx_or_interaction.followup.send(embed=embed_err)
                else:
                    await ctx_or_interaction.send(embed=embed_err)

        if len(searches) > 1:
            embed_final = EmbedBuilder.create_success_embed(t('success'), t('added_songs_queue', count=len(searches)))
            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.followup.send(embed=embed_final)
            else:
                await ctx_or_interaction.send(embed=embed_final)

    @commands.command()
    async def play(self, ctx: commands.Context, *, search: str):
        await self._do_play(ctx, search)

    @app_commands.command(name="play", description="Plays music from YouTube or SoundCloud")
    @app_commands.describe(search="Name, URL or 'scsearch: term' for SoundCloud")
    async def play_slash(self, interaction: discord.Interaction, search: str):
        await self._do_play(interaction, search)

    async def _do_skip(self, ctx_or_interaction):
        guild_id = ctx_or_interaction.guild.id
        player = self.get_player(guild_id)
        player.skip()
        
        msg = t('song_skipped')
        if isinstance(ctx_or_interaction, discord.Interaction):
            if not ctx_or_interaction.response.is_done():
                await ctx_or_interaction.response.send_message(msg)
            else:
                await ctx_or_interaction.followup.send(msg)
        else:
            await ctx_or_interaction.send(msg)

    @commands.command()
    async def skip(self, ctx: commands.Context):
        await self._do_skip(ctx)

    @app_commands.command(name="skip", description="Skips to the next song")
    async def skip_slash(self, interaction: discord.Interaction):
        await self._do_skip(interaction)

    async def _do_stop(self, ctx_or_interaction):
        guild_id = ctx_or_interaction.guild.id
        player = self.get_player(guild_id)
        player.stop()
        
        msg = t('music_stopped_queue_cleared')
        if isinstance(ctx_or_interaction, discord.Interaction):
            if not ctx_or_interaction.response.is_done():
                await ctx_or_interaction.response.send_message(msg)
            else:
                await ctx_or_interaction.followup.send(msg)
        else:
            await ctx_or_interaction.send(msg)

    @commands.command()
    async def stop(self, ctx: commands.Context):
        await self._do_stop(ctx)

    @app_commands.command(name="stop", description="Stops playback and clears the queue")
    async def stop_slash(self, interaction: discord.Interaction):
        await self._do_stop(interaction)

    async def _do_resume(self, ctx_or_interaction):
        guild_id = ctx_or_interaction.guild.id
        player = self.get_player(guild_id)
        player.resume()
        
        msg = t('playback')
        if isinstance(ctx_or_interaction, discord.Interaction):
            if not ctx_or_interaction.response.is_done():
                await ctx_or_interaction.response.send_message(t('playback'), ephemeral=True)
            else:
                await ctx_or_interaction.followup.send(t('playback'), ephemeral=True)
        else:
            await ctx_or_interaction.send(msg)

    @commands.command()
    async def resume(self, ctx: commands.Context):
        """Retoma a reprodução (prefix command)."""
        await self._do_resume(ctx)

    @app_commands.command(name="resume", description="Resumes playback")
    async def resume_slash(self, interaction: discord.Interaction):
        await self._do_resume(interaction)

    async def _do_pause(self, ctx_or_interaction):
        guild_id = ctx_or_interaction.guild.id
        player = self.get_player(guild_id)
        player.pause()
        msg = t('playback')
        if isinstance(ctx_or_interaction, discord.Interaction):
            if not ctx_or_interaction.response.is_done():
                await ctx_or_interaction.response.send_message(msg, ephemeral=True)
            else:
                await ctx_or_interaction.followup.send(msg, ephemeral=True)
        else:
            await ctx_or_interaction.send(msg)

    @commands.command()
    async def pause(self, ctx: commands.Context):
        """Pausa a reprodução."""
        await self._do_pause(ctx)

    @app_commands.command(name="pause", description="Pauses playback")
    async def pause_slash(self, interaction: discord.Interaction):
        await self._do_pause(interaction)

    async def _do_nowplaying(self, ctx_or_interaction):
        guild_id = ctx_or_interaction.guild.id
        
        # Se for interação, deferir
        if isinstance(ctx_or_interaction, discord.Interaction):
            if not ctx_or_interaction.response.is_done():
                 await ctx_or_interaction.response.defer(ephemeral=False)
        
        # Obter VC e Player
        guild = ctx_or_interaction.guild
        vc = guild.voice_client if guild else None

        if not vc or (not vc.is_playing() and not vc.is_paused()):
                embed = EmbedBuilder.create_error_embed(
                    t('not_playing'),
                    t('not_playing')
                )
                if isinstance(ctx_or_interaction, discord.Interaction):
                    await ctx_or_interaction.followup.send(embed=embed)
                else:
                    await ctx_or_interaction.send(embed=embed)
                return

        if guild_id in self.bot.players:
            player_instance = self.bot.players[guild_id]
            
            if not player_instance.current_song:
                embed = EmbedBuilder.create_error_embed(
                    "Nada tocando",
                    "A fila está vazia."
                )
                if isinstance(ctx_or_interaction, discord.Interaction):
                    await ctx_or_interaction.followup.send(embed=embed)
                else:
                    await ctx_or_interaction.send(embed=embed)
                return

            progress = player_instance.get_progress()
            current_seconds = progress['current']
            total_seconds = progress['duration']

            # Extrair cor dominante
            thumb_url = player_instance.current_song.get('thumbnail')
            dominant_color = None
            if thumb_url:
                try:
                    loop = self.bot.loop
                    dominant_color = await loop.run_in_executor(None, get_dominant_color, thumb_url)
                except Exception as e:
                    logging.error(f"Erro ao extrair cor: {e}")

            embed = EmbedBuilder.create_now_playing_embed(
                player_instance.current_song, 
                list(player_instance.queue),
                current_seconds=current_seconds,
                total_seconds=total_seconds,
                color=dominant_color
            )
            
            loop = self.bot.loop

            # Card
            import functools
            card_buffer = await loop.run_in_executor(
                None,
                functools.partial(
                    create_now_playing_card,
                    player_instance.current_song,
                    next_songs=list(player_instance.queue)[:3],
                    progress_percent=(current_seconds / total_seconds) if total_seconds > 0 else None,
                )
            )
            
            file = None
            if card_buffer:
                file = discord.File(card_buffer, filename="nowplaying.png")
                embed.set_image(url="attachment://nowplaying.png")
            
            if thumb_url:
                 embed.set_thumbnail(url=thumb_url)

            if isinstance(ctx_or_interaction, discord.Interaction):
                if file:
                    await ctx_or_interaction.followup.send(embed=embed, file=file)
                else:
                    await ctx_or_interaction.followup.send(embed=embed)
            else:
                if file:
                    await ctx_or_interaction.send(embed=embed, file=file)
                else:
                    await ctx_or_interaction.send(embed=embed)

        else:
             embed = EmbedBuilder.create_error_embed(
                "Erro",
                "Player não encontrado para este servidor."
            )
             if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.followup.send(embed=embed)
             else:
                await ctx_or_interaction.send(embed=embed)

    @commands.command()
    async def agora(self, ctx: commands.Context):
        await self._do_nowplaying(ctx)

    @app_commands.command(name="agora", description="Shows the currently playing song")
    async def agora_slash(self, interaction: discord.Interaction):
        await self._do_nowplaying(interaction)

    async def _do_queue(self, ctx_or_interaction):
        guild_id = ctx_or_interaction.guild.id
        player = self.get_player(guild_id)
        
        if isinstance(ctx_or_interaction, discord.Interaction):
            if not ctx_or_interaction.response.is_done():
                await ctx_or_interaction.response.defer(ephemeral=True)

        if len(player.queue) == 0 and not player.current_song:
            embed = discord.Embed(
                title=t('queue_empty'),
                description=t('queue_no_songs'),
                color=discord.Color.blue()
            )
            if isinstance(ctx_or_interaction, discord.Interaction):
                 await ctx_or_interaction.followup.send(embed=embed, ephemeral=True)
            else:
                 await ctx_or_interaction.send(embed=embed)
            return

        total_seconds = sum(s.get('duration_seconds', 0) for s in player.queue)
        total_time_str = f"{int(total_seconds // 60)}{t('minutes_abbr')}"

        embed = discord.Embed(
            title=f"{t('queue')} ({len(player.queue)} {t('songs')} • {total_time_str})",
            color=discord.Color.blue()
        )

        if player.current_song:
             embed.add_field(
                name=t('playing_now'),
                value=f"**{player.current_song['title']}** \n`{player.current_song.get('duration', '?')}`",
                inline=False
            )

        songs_list = ""
        for i, song in enumerate(list(player.queue)[:10], 1):
            songs_list += f"`{i}.` **{song['title']}** | `{song.get('duration', '?')}`\n"
        
        if len(player.queue) > 10:
            songs_list += f"\n{t('and_more_songs', count=len(player.queue) - 10)}"
            
        if songs_list:
             embed.add_field(name=t('next_songs_in_queue', count=len(player.queue)), value=songs_list, inline=False)
             
        if isinstance(ctx_or_interaction, discord.Interaction):
            await ctx_or_interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await ctx_or_interaction.send(embed=embed)

    @commands.command(name="fila")
    async def fila(self, ctx: commands.Context):
        await self._do_queue(ctx)

    @app_commands.command(name="fila", description="Shows the music queue")
    async def fila_slash(self, interaction: discord.Interaction):
        await self._do_queue(interaction)

    async def _do_volume(self, ctx_or_interaction, vol: float):
        # Validar range
        if not 0.0 <= vol <= 1.5:
            err = EmbedBuilder.create_error_embed(t('error'), "Volume deve estar entre 0.0 e 1.5")
            if isinstance(ctx_or_interaction, discord.Interaction):
                if not ctx_or_interaction.response.is_done():
                    await ctx_or_interaction.response.send_message(embed=err, ephemeral=True)
                else:
                    await ctx_or_interaction.followup.send(embed=err, ephemeral=True)
            else:
                await ctx_or_interaction.send(embed=err)
            return

        guild_id = ctx_or_interaction.guild.id
        player = self.get_player(guild_id)
        player.set_volume(vol)
        embed = EmbedBuilder.create_success_embed(
            t('volume_adjusted'),
            t('volume_set_to', volume=int(player.volume * 100))
        )
        
        if isinstance(ctx_or_interaction, discord.Interaction):
            if not ctx_or_interaction.response.is_done():
                await ctx_or_interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await ctx_or_interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await ctx_or_interaction.send(embed=embed, delete_after=5)

    @commands.command()
    async def volume(self, ctx: commands.Context, vol: float):
        await self._do_volume(ctx, vol)

    @app_commands.command(name="volume", description="Adjusts the volume (0.0 to 1.0)")
    @app_commands.describe(vol="Volume between 0.0 and 1.0")
    async def volume_slash(self, interaction: discord.Interaction, vol: float):
        await self._do_volume(interaction, vol)

    @app_commands.command(name="nowplaying", description="Shows currently playing song with progress bar")
    async def nowplaying_slash(self, interaction: discord.Interaction):
         await self._do_nowplaying(interaction)

    # --- Comandos de Rádio ---

    async def _do_list_radios(self, ctx_or_interaction):
        if not self.RADIOS:
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
        
        for r_id, r_info in self.RADIOS.items():
            name = r_info.get('name', r_id)
            location = r_info.get('location', t('unknown'))
            embed.add_field(name=f"{name} ({r_id})", value=location, inline=True)
            
        if isinstance(ctx_or_interaction, discord.Interaction):
             await ctx_or_interaction.response.send_message(embed=embed)
        else:
             await ctx_or_interaction.send(embed=embed)

    @commands.command()
    async def radios(self, ctx: commands.Context):
        await self._do_list_radios(ctx)

    @app_commands.command(name="radios", description="Lists available radio stations")
    async def radios_slash(self, interaction: discord.Interaction):
        await self._do_list_radios(interaction)

    async def _do_play_radio(self, ctx_or_interaction, radio_id: str):
         # Obter user para check de voz
        if isinstance(ctx_or_interaction, discord.Interaction):
            user = ctx_or_interaction.user
             # Defer se necessário
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
        
        radio_info = self.RADIOS.get(radio_id.lower())
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
            # 1. Adicionar à fila ANTES de parar (evita estado sem música se falhar)
            await player.add_to_queue(url, user)
            
            # 2. Forçar update de metadados para parecer rádio
            if player.queue:
                player.queue[-1]['title'] = radio_info.get('name', radio_id)
                player.queue[-1]['is_radio'] = True
                player.queue[-1]['thumbnail'] = radio_info.get('favicon')
                player.queue[-1]['is_lazy'] = False 
                player.stream_cache.set(url, url)
            
            # 3. Parar música atual (agora seguro, rádio já está na fila)
            player.stop()
            
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
        await self._do_play_radio(ctx, radio_id)

    @app_commands.command(name="radio", description="Plays a specific radio station")
    @app_commands.describe(radio_id="Radio ID")
    async def radio_slash(self, interaction: discord.Interaction, radio_id: str):
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

        if id in self.RADIOS:
            embed = EmbedBuilder.create_error_embed(t('error'), t('radio_exists', name=nome))
            if isinstance(ctx_or_interaction, discord.Interaction):
                 await ctx_or_interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                 await ctx_or_interaction.send(embed=embed)
            return
            
        self.RADIOS[id] = {
            "name": nome,
            "url": url,
            "location": localizacao
        }
        
        try:
            with open(RADIOS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.RADIOS, f, indent=4)
            
            embed = EmbedBuilder.create_success_embed(t('radio_added'), t('radio_added_success', name=nome, id=id))
            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.response.send_message(embed=embed)
            else:
                await ctx_or_interaction.send(embed=embed)
                
        except Exception as e:
            logging.error(f"Erro ao salvar rádio: {e}")
            embed_err = EmbedBuilder.create_error_embed(t('error'), t('error_saving_radio'))
            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.response.send_message(embed=embed_err, ephemeral=True)
            else:
                await ctx_or_interaction.send(embed=embed_err)

    @app_commands.command(name="addradio", description="Adds a new custom radio (Admin)")
    @app_commands.describe(id="Unique ID for remote", nome="Radio Name", url="Stream URL", localizacao="Location (optional)")
    async def add_radio_slash(self, interaction: discord.Interaction, id: str, nome: str, url: str, localizacao: str = "Desconhecido"):
        await self._do_add_radio(interaction, id, nome, url, localizacao)
    
    # Adicionar comando de prefixo para addradio, se desejar (não existia antes, mas padronização é bom)
    # Por enquanto, manterei apenas o slash conforme original, mas a refatoração permitiu extensibilidade.
    # Se o usuário quiser !addradio futuramente, já está pronto.

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

        if id not in self.RADIOS:
            embed = EmbedBuilder.create_error_embed(t('error'), t('radio_not_found'))
            if isinstance(ctx_or_interaction, discord.Interaction):
                 await ctx_or_interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                 await ctx_or_interaction.send(embed=embed)
            return
            
        name = self.RADIOS[id].get('name', id)
        del self.RADIOS[id]
        
        try:
            with open(RADIOS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.RADIOS, f, indent=4)
            
            embed = EmbedBuilder.create_success_embed(t('radio_removed'), t('radio_removed_success', name=name))
            if isinstance(ctx_or_interaction, discord.Interaction):
                 await ctx_or_interaction.response.send_message(embed=embed)
            else:
                 await ctx_or_interaction.send(embed=embed)
        except Exception as e:
            logging.error(f"Erro ao remover rádio: {e}")
            embed_err = EmbedBuilder.create_error_embed(t('error'), t('error_removing_radio'))
            if isinstance(ctx_or_interaction, discord.Interaction):
                 await ctx_or_interaction.response.send_message(embed=embed_err, ephemeral=True)
            else:
                 await ctx_or_interaction.send(embed=embed_err)

    @app_commands.command(name="removeradio", description="Removes an existing radio (Admin)")
    @app_commands.describe(id="ID of the radio to remove")
    async def remove_radio_slash(self, interaction: discord.Interaction, id: str):
        await self._do_remove_radio(interaction, id)

    @commands.command(name="sync")
    async def sync_commands(self, ctx: commands.Context):
        """Força a sincronização dos comandos slash com o Discord"""
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

async def setup(bot):
    await bot.add_cog(MusicCog(bot))
