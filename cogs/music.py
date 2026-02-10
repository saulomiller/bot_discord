import discord
from discord.ext import commands
from discord import app_commands
import logging
import asyncio
import os
import json
import aiofiles
from utils.player import MusicPlayer
from config import RADIOS_FILE, PLAYLIST_DIR, DATA_DIR, FFMPEG_PATH
from utils.embeds import EmbedBuilder
from utils.helpers import ensure_voice, check_system_resources, load_radios, extract_info, playlist_cache
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

    @commands.command()
    async def join(self, ctx: commands.Context):
        vc = await ensure_voice(ctx)
        if vc:
            await ctx.send(embed=discord.Embed(
                title=t('connected'),
                description=t('joined_channel', channel=vc.channel.name),
                color=discord.Color.green()))

    @app_commands.command(name="join", description="Joins the voice channel")
    async def join_slash(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        vc = await ensure_voice(interaction)
        if vc:
            await interaction.followup.send(embed=discord.Embed(
                title=t('connected'),
                description=t('joined_channel', channel=vc.channel.name),
                color=discord.Color.green()))

    @commands.command()
    async def leave(self, ctx: commands.Context):
        vc = ctx.voice_client
        if vc:
            await vc.disconnect()
            await ctx.send(embed=discord.Embed(
                title=t('disconnected'),
                description=t('left_channel'),
                color=discord.Color.orange()))
        else:
            await ctx.send(embed=discord.Embed(
                title=t('error'),
                description=t('not_in_voice'),
                color=discord.Color.red()))

    @app_commands.command(name="leave", description="Leaves the voice channel")
    async def leave_slash(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        vc = interaction.guild.voice_client
        if vc:
            await vc.disconnect()
            await interaction.followup.send(embed=discord.Embed(
                title=t('disconnected'),
                description=t('left_channel'),
                color=discord.Color.orange()))
        else:
            await interaction.followup.send(embed=discord.Embed(
                title=t('error'),
                description=t('not_in_voice'),
                color=discord.Color.red()))

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
    
    @app_commands.command(name="sair_todos", description="Disconnects from all voice channels in all servers")
    async def sair_todos_slash(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        count = 0
        for guild in self.bot.guilds:
            voice_client = guild.voice_client
            if voice_client and voice_client.is_connected():
                try:
                    if guild.id in self.bot.players:
                        self.bot.players[guild.id].stop()
                    await voice_client.disconnect(force=True)
                    count += 1
                    logging.info(f"Desconectado de {guild.name} via comando sair_todos")
                except Exception as e:
                    logging.error(f"Erro ao desconectar de {guild.name}: {e}")
        
        if count > 0:
            await interaction.followup.send(embed=discord.Embed(
                title=t('disconnected'),
                description=t('left_all_channels', count=count),
                color=discord.Color.orange()))
        else:
            await interaction.followup.send(embed=discord.Embed(
                title=t('info'),
                description=t('not_in_voice'),
                color=discord.Color.blue()))

    # --- Comandos de Reprodução ---

    @commands.command()
    async def play(self, ctx: commands.Context, *, search: str):
        vc = await ensure_voice(ctx)
        if not vc: return
        
        if not vc: 
            return
        
        player = self.get_player(ctx.guild.id)
        player.dashboard_context = ctx # Vincular canal de texto para dashboard
        
        # Verificar se é playlist
        if 'list=' in search:
            if self.playlist_processing_task and not self.playlist_processing_task.done():
                await ctx.send(embed=EmbedBuilder.create_error_embed(t('error'), "Já existe uma playlist sendo processada. Aguarde."))
                return

            status_msg = await ctx.send(embed=EmbedBuilder.create_info_embed(t('processing_playlist'), t('extracting_playlist')))
            
            try:
                loop = asyncio.get_event_loop()
                data = await loop.run_in_executor(None, lambda: extract_info(search, download=False))
                
                if 'entries' in data:
                    songs = [entry for entry in data['entries'] if entry]
                    for song in songs:
                        player.queue.append(song)
                    
                    if not player.is_playing:
                        await player.play_next()
                    
                    await status_msg.edit(embed=EmbedBuilder.create_success_embed(t('playlist_added'), t('added_songs_queue', count=len(songs))))
                else:
                    await status_msg.edit(embed=EmbedBuilder.create_error_embed(t('error'), "Não foi possível extrair a playlist."))
            except Exception as e:
                await status_msg.edit(embed=EmbedBuilder.create_error_embed(t('error'), str(e)))
            return

        # Busca normal (YouTube/SoundCloud)
        searches = search.split(";")
        if len(searches) > 1:
            await ctx.send(embed=EmbedBuilder.create_info_embed(t('adding_songs', count=len(searches))))
        
        for query in searches:
            query = query.strip()
            if not query: continue
            
            try:
                info = extract_info(query, download=False)
                if not info: continue
                
                entries = info.get('entries', [info])
                for entry in entries:
                    player.queue.append(entry)
                    if not player.is_playing:
                        await player.play_next()
                    else:
                        # Se já estiver tocando, avisa que adicionou à fila (se for apenas 1 música)
                        if len(searches) == 1 and len(entries) == 1:
                             pos = len(player.queue)
                             await ctx.send(embed=EmbedBuilder.create_info_embed(
                                 t('added_to_queue'), 
                                 f"🎵 **{entry.get('title')}**\n{t('position_in_queue', position=pos)}"
                             ))

            except Exception as e:
                await ctx.send(embed=EmbedBuilder.create_error_embed(t('error'), f"Erro ao adicionar: {query}"))
                logging.error(f"Erro no play: {e}")

        if len(searches) > 1:
            await ctx.send(embed=EmbedBuilder.create_success_embed(t('success'), t('added_songs_queue', count=len(searches))))

    @app_commands.command(name="play", description="Plays music from YouTube or SoundCloud")
    @app_commands.describe(search="Name, URL or 'scsearch: term' for SoundCloud")
    async def play_slash(self, interaction: discord.Interaction, search: str):
        if not interaction.user.voice:
            await interaction.response.send_message(t('user_must_be_in_voice'), ephemeral=True)
            return

        await interaction.response.defer()
        vc = await ensure_voice(interaction)
        if not vc: return

        player = self.get_player(interaction.guild_id)
        player.dashboard_context = interaction # Vincular canal de texto para dashboard

         # Verificar se é playlist
        if 'list=' in search:
             if self.playlist_processing_task and not self.playlist_processing_task.done():
                await interaction.followup.send(embed=EmbedBuilder.create_error_embed(t('error'), "Já existe uma playlist sendo processada."))
                return
             
             msg = await interaction.followup.send(embed=EmbedBuilder.create_info_embed(t('processing_playlist'), t('extracting_playlist')))
             try:
                loop = asyncio.get_event_loop()
                data = await loop.run_in_executor(None, lambda: extract_info(search, download=False))
                
                if 'entries' in data:
                    songs = [entry for entry in data['entries'] if entry]
                    for song in songs:
                        player.queue.append(song)
                    
                    if not player.is_playing:
                        await player.play_next()
                    
                    await interaction.followup.send(embed=EmbedBuilder.create_success_embed(t('playlist_added'), t('added_songs_queue', count=len(songs))))
                else:
                    await interaction.followup.send(embed=EmbedBuilder.create_error_embed(t('error'), "Falha ao extrair playlist."))

             except Exception as e:
                 await interaction.followup.send(embed=EmbedBuilder.create_error_embed(t('error'), str(e)))
             return

        # Busca normal
        searches = search.split(";")
        
        for query in searches:
            query = query.strip()
            if not query: continue

            try:
                info = extract_info(query, download=False)
                if not info: continue

                entries = info.get('entries', [info])
                for entry in entries:
                    player.queue.append(entry)
                    if not player.is_playing:
                        await player.play_next()
                    else:
                        if len(searches) == 1 and len(entries) == 1:
                            pos = len(player.queue)
                            await interaction.followup.send(embed=EmbedBuilder.create_info_embed(
                                t('added_to_queue'), 
                                f"🎵 **{entry.get('title')}**\n{t('position_in_queue', position=pos)}"
                            ))
            except Exception as e:
                logging.error(f"Erro no play_slash: {e}")
                await interaction.followup.send(embed=EmbedBuilder.create_error_embed(t('error'), str(e)))
        
        if len(searches) > 1:
             await interaction.followup.send(embed=discord.Embed(title=t('success'), description=t('added_songs_queue', count=len(searches)), color=discord.Color.green()))
                

    @commands.command()
    async def skip(self, ctx: commands.Context):
        player = self.get_player(ctx.guild.id)
        player.skip()
        await ctx.send("Música pulada.")

    @app_commands.command(name="skip", description="Skips to the next song")
    async def skip_slash(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild_id)
        player.skip()
        await interaction.response.send_message("Música pulada.")

    @commands.command()
    async def stop(self, ctx: commands.Context):
        player = self.get_player(ctx.guild.id)
        player.stop()
        await ctx.send("Música parada e fila limpa.")

    @app_commands.command(name="stop", description="Stops playback and clears the queue")
    async def stop_slash(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild_id)
        player.stop()
        await interaction.response.send_message("Música parada e fila limpa.")

    @commands.command()
    async def agora(self, ctx: commands.Context):
        player = self.get_player(ctx.guild.id)
        if not player.current_song:
            await ctx.send(embed=discord.Embed(
                title=t('playback'),
                description=t('not_playing'),
                color=discord.Color.blue()))
            return

        song = player.current_song
        title = song['title']
        user = song['user']
        duration = song.get('duration', t('unknown'))
        channel = song.get('channel', t('unknown'))
            
        embed = discord.Embed(
            title=t('now_playing'),
            description=f"**{title}**",
            color=discord.Color.from_rgb(57, 255, 20)
        )
        
        embed.add_field(name=t('channel'), value=channel, inline=True)
        embed.add_field(name=t('duration'), value=duration, inline=True)
        if hasattr(user, 'mention'):
            embed.add_field(name=t('added_by'), value=user.mention, inline=False)
        else:
            embed.add_field(name=t('added_by'), value=str(user), inline=False)
        
        if len(player.queue) > 0:
            embed.set_footer(text=t('next_songs_in_queue', count=len(player.queue)))
            
        await ctx.send(embed=embed)

    @app_commands.command(name="agora", description="Shows the currently playing song")
    async def agora_slash(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild_id)
        if not player.current_song:
            await interaction.response.send_message(embed=discord.Embed(
                title=t('playback'),
                description=t('not_playing'),
                color=discord.Color.blue()))
            return

        song = player.current_song
        title = song['title']
        user = song['user']
        duration = song.get('duration', t('unknown'))
        channel = song.get('channel', t('unknown'))
            
        embed = discord.Embed(
            title=t('now_playing'),
            description=f"**{title}**",
            color=discord.Color.from_rgb(57, 255, 20)
        )
        
        embed.add_field(name=t('channel'), value=channel, inline=True)
        embed.add_field(name=t('duration'), value=duration, inline=True)
        if hasattr(user, 'mention'):
            embed.add_field(name=t('added_by'), value=user.mention, inline=False)
        else:
            embed.add_field(name=t('added_by'), value=str(user), inline=False)
        
        if len(player.queue) > 0:
            embed.set_footer(text=t('next_songs_in_queue', count=len(player.queue)))
            
        await interaction.response.send_message(embed=embed)

    @commands.command(name="fila")
    async def fila(self, ctx: commands.Context):
        player = self.get_player(ctx.guild.id)
        if len(player.queue) == 0 and not player.current_song:
            await ctx.send(embed=discord.Embed(
                title=t('queue_empty'),
                description=t('queue_no_songs'),
                color=discord.Color.blue()))
            return

        # Calcular duração total da fila
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
            
        await ctx.send(embed=embed)

    @app_commands.command(name="fila", description="Shows the music queue")
    async def fila_slash(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        player = self.get_player(interaction.guild_id)
        if len(player.queue) == 0 and not player.current_song:
            await interaction.followup.send(embed=discord.Embed(
                title=t('queue_empty'),
                description=t('queue_no_songs'),
                color=discord.Color.blue()), ephemeral=True)
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
            
        await interaction.followup.send(embed=embed, ephemeral=True)

    @commands.command()
    async def volume(self, ctx: commands.Context, vol: float):
        player = self.get_player(ctx.guild.id)
        player.set_volume(vol)
        embed = EmbedBuilder.create_success_embed(
            "Volume ajustado",
            f"Volume definido para {int(player.volume * 100)}%"
        )
        await ctx.send(embed=embed, delete_after=5)

    @app_commands.command(name="volume", description="Adjusts the volume (0.0 to 1.0)")
    @app_commands.describe(vol="Volume between 0.0 and 1.0")
    async def volume_slash(self, interaction: discord.Interaction, vol: float):
        player = self.get_player(interaction.guild_id)
        player.set_volume(vol)
        embed = EmbedBuilder.create_success_embed(
            "Volume ajustado",
            f"Volume definido para {int(player.volume * 100)}%"
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="nowplaying", description="Shows currently playing song with progress bar")
    async def nowplaying_slash(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        
        vc = interaction.guild.voice_client
        if not vc or not vc.is_playing():
            if not vc or (not vc.is_playing() and not vc.is_paused()):
                await interaction.followup.send(embed=EmbedBuilder.create_error_embed(
                    "Nada tocando",
                    "O bot não está tocando nenhuma música no momento."
                ))
                return

        if interaction.guild.id in self.bot.players:
            player_instance = self.bot.players[interaction.guild.id]
            
            if not player_instance.current_song:
                await interaction.followup.send(embed=EmbedBuilder.create_error_embed(
                    "Nada tocando",
                    "A fila está vazia."
                ))
                return

            progress = player_instance.get_progress()
            current_seconds = progress['current']
            total_seconds = progress['duration']

            # Extrair cor dominante
            thumb_url = player_instance.current_song.get('thumbnail')
            dominant_color = None
            if thumb_url:
                try:
                    # Executar em executor para não bloquear
                    loop = asyncio.get_event_loop()
                    dominant_color = await loop.run_in_executor(None, get_dominant_color, thumb_url)
                except Exception as e:
                    logging.error(f"Erro ao extrair cor: {e}")

            embed = EmbedBuilder.create_now_playing_embed(
                player_instance.current_song, 
                len(player_instance.queue),
                current_seconds=current_seconds,
                total_seconds=total_seconds,
                color=dominant_color
            )
            
            # Garantir que loop está definido
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            # Tentar gerar imagem personalizada (Card)
            # Descomente para usar o CARD em vez do EMBED (ou envie ambos)
            card_buffer = await loop.run_in_executor(None, create_now_playing_card, player_instance.current_song, progress['percent'])
            if card_buffer:
                file = discord.File(card_buffer, filename="nowplaying.png")
                embed.set_image(url="attachment://nowplaying.png")
                await interaction.followup.send(embed=embed, file=file)
            else:
                 await interaction.followup.send(embed=embed)

            if thumb_url:
                embed.set_thumbnail(url=thumb_url)
        else:
             await interaction.followup.send(embed=EmbedBuilder.create_error_embed(
                "Erro",
                "Player não encontrado para este servidor."
            ))

    # --- Comandos de Rádio ---

    @commands.command()
    async def radios(self, ctx: commands.Context):
        if not self.RADIOS:
            await ctx.send(t('no_radios_found'))
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
            
        await ctx.send(embed=embed)

    @app_commands.command(name="radios", description="Lists available radio stations")
    async def radios_slash(self, interaction: discord.Interaction):
        if not self.RADIOS:
            await interaction.response.send_message(t('no_radios_found'))
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
            
        await interaction.response.send_message(embed=embed)

    @commands.command()
    async def radio(self, ctx: commands.Context, radio_id: str):
        vc = await ensure_voice(ctx)
        if not vc: return
        
        radio_info = self.RADIOS.get(radio_id.lower())
        if not radio_info:
            await ctx.send(embed=EmbedBuilder.create_error_embed(t('error'), t('radio_not_found')))
            return
            
        url = radio_info.get('url')
        if not url:
            await ctx.send(embed=EmbedBuilder.create_error_embed(t('error'), t('invalid_url')))
            return
            
        player = self.get_player(ctx.guild.id)
        
        # Parar música atual se houver
        player.stop()
        
        try:
            # Rádios geralmente são streams diretos, usamos add_to_queue mas com metadados manuais seria melhor
            # O MusicPlayer detecta stream se for URL
            await player.add_to_queue(url, ctx.author)
            
            # Forçar update de metadados para parecer rádio
            if player.queue:
                player.queue[-1]['title'] = radio_info.get('name', radio_id)
                player.queue[-1]['is_radio'] = True
                player.queue[-1]['thumbnail'] = radio_info.get('favicon')
            
            await player.play_next()
            await ctx.send(embed=EmbedBuilder.create_radio_embed(radio_info))
            
        except Exception as e:
             await ctx.send(embed=EmbedBuilder.create_error_embed(t('error'), str(e)))

    @app_commands.command(name="radio", description="Plays a specific radio station")
    @app_commands.describe(radio_id="Radio ID")
    async def radio_slash(self, interaction: discord.Interaction, radio_id: str):
        if not interaction.user.voice:
             await interaction.response.send_message(t('user_must_be_in_voice'), ephemeral=True)
             return

        await interaction.response.defer()
        vc = await ensure_voice(interaction)
        if not vc: return
        
        radio_info = self.RADIOS.get(radio_id.lower())
        if not radio_info:
            await interaction.followup.send(embed=EmbedBuilder.create_error_embed(t('error'), t('radio_not_found')))
            return
            
        url = radio_info.get('url')
        if not url:
            await interaction.followup.send(embed=EmbedBuilder.create_error_embed(t('error'), t('invalid_url')))
            return
            
        player = self.get_player(interaction.guild_id)
        player.stop()
        
        try:
            await player.add_to_queue(url, interaction.user)
             # Forçar update de metadados
            if player.queue:
                player.queue[-1]['title'] = radio_info.get('name', radio_id)
                player.queue[-1]['is_radio'] = True
                player.queue[-1]['thumbnail'] = radio_info.get('favicon')

            await player.play_next()
            await interaction.followup.send(embed=EmbedBuilder.create_radio_embed(radio_info))
            
        except Exception as e:
             await interaction.followup.send(embed=EmbedBuilder.create_error_embed(t('error'), str(e)))

    @app_commands.command(name="addradio", description="Adds a new custom radio (Admin)")
    @app_commands.describe(id="Unique ID for remote", nome="Radio Name", url="Stream URL", localizacao="Location (optional)")
    async def add_radio_slash(self, interaction: discord.Interaction, id: str, nome: str, url: str, localizacao: str = "Desconhecido"):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(t('need_admin'), ephemeral=True)
            return

        if id in self.RADIOS:
            await interaction.response.send_message(embed=EmbedBuilder.create_error_embed(t('error'), t('radio_exists', name=nome)), ephemeral=True)
            return
            
        self.RADIOS[id] = {
            "name": nome,
            "url": url,
            "location": localizacao
        }
        
        try:
            with open(RADIOS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.RADIOS, f, indent=4)
            await interaction.response.send_message(embed=EmbedBuilder.create_success_embed(t('radio_added'), t('radio_added_success', name=nome, id=id)))
        except Exception as e:
            logging.error(f"Erro ao salvar rádio: {e}")
            await interaction.response.send_message(embed=EmbedBuilder.create_error_embed(t('error'), t('error_saving_radio')), ephemeral=True)

    @app_commands.command(name="removeradio", description="Removes an existing radio (Admin)")
    @app_commands.describe(id="ID of the radio to remove")
    async def remove_radio_slash(self, interaction: discord.Interaction, id: str):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(t('need_admin'), ephemeral=True)
            return

        if id not in self.RADIOS:
            await interaction.response.send_message(embed=EmbedBuilder.create_error_embed(t('error'), t('radio_not_found')), ephemeral=True)
            return
            
        name = self.RADIOS[id].get('name', id)
        del self.RADIOS[id]
        
        try:
            with open(RADIOS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.RADIOS, f, indent=4)
            await interaction.response.send_message(embed=EmbedBuilder.create_success_embed(t('radio_removed'), t('radio_removed_success', name=name)))
        except Exception as e:
            logging.error(f"Erro ao remover rádio: {e}")
            await interaction.response.send_message(embed=EmbedBuilder.create_error_embed(t('error'), t('error_removing_radio')), ephemeral=True)

    @commands.command(name="sync")
    async def sync_commands(self, ctx: commands.Context):
        """Força a sincronização dos comandos slash com o Discord"""
        try:
            if not ctx.author.guild_permissions.administrator:
                await ctx.send(embed=discord.Embed(title="Erro", description="Precisa de admin.", color=discord.Color.red()))
                return
                
            await ctx.send(embed=discord.Embed(title="Sincronizando", description="Sincronizando...", color=discord.Color.blue()))
            synced = await self.bot.tree.sync()
            await ctx.send(embed=discord.Embed(title="Sucesso", description=f"{len(synced)} comandos sincronizados.", color=discord.Color.green()))
                
        except Exception as e:
            logging.error(f"Erro ao sincronizar: {e}")
            await ctx.send(embed=discord.Embed(title="Erro", description=f"Erro: {str(e)}", color=discord.Color.red()))

async def setup(bot):
    await bot.add_cog(MusicCog(bot))
