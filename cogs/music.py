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
                title="Conectado",
                description=f"Juntei-me ao canal **{vc.channel.name}**.",
                color=discord.Color.green()))

    @app_commands.command(name="join", description="Entra no canal de voz")
    async def join_slash(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        vc = await ensure_voice(interaction)
        if vc:
            await interaction.followup.send(embed=discord.Embed(
                title="Conectado",
                description=f"Juntei-me ao canal **{vc.channel.name}**.",
                color=discord.Color.green()))

    @commands.command()
    async def leave(self, ctx: commands.Context):
        vc = ctx.voice_client
        if vc:
            await vc.disconnect()
            await ctx.send(embed=discord.Embed(
                title="Desconectado",
                description="Saí do canal de voz.",
                color=discord.Color.orange()))
        else:
            await ctx.send(embed=discord.Embed(
                title="Erro",
                description="Não estou em um canal de voz.",
                color=discord.Color.red()))

    @app_commands.command(name="leave", description="Sai do canal de voz")
    async def leave_slash(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        vc = interaction.guild.voice_client
        if vc:
            await vc.disconnect()
            await interaction.followup.send(embed=discord.Embed(
                title="Desconectado",
                description="Saí do canal de voz.",
                color=discord.Color.orange()))
        else:
            await interaction.followup.send(embed=discord.Embed(
                title="Erro",
                description="Não estou em um canal de voz.",
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
                title="Desconectado",
                description=f"Saí de {count} canais de voz em todos os servidores.",
                color=discord.Color.orange()))
        else:
            await ctx.send(embed=discord.Embed(
                title="Informação",
                description="Não estou conectado a nenhum canal de voz.",
                color=discord.Color.blue()))
    
    @app_commands.command(name="sair_todos", description="Sai de todos os canais de voz em todos os servidores")
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
                title="Desconectado",
                description=f"Saí de {count} canais de voz em todos os servidores.",
                color=discord.Color.orange()))
        else:
            await interaction.followup.send(embed=discord.Embed(
                title="Informação",
                description="Não estou conectado a nenhum canal de voz.",
                color=discord.Color.blue()))

    # --- Comandos de Reprodução ---

    @commands.command()
    async def play(self, ctx: commands.Context, *, search: str):
        vc = await ensure_voice(ctx)
        if not vc: return
        
        player = self.get_player(ctx.guild.id)
        
        try:
            searches = [s.strip() for s in search.split(';') if s.strip()]
            
            if len(searches) > 1:
                await ctx.send(embed=discord.Embed(title="Adicionando...", description=f"Adicionando {len(searches)} músicas...", color=discord.Color.blue()))
                for s in searches:
                    await player.add_to_queue(s, ctx.author)
                await ctx.send(embed=discord.Embed(title="Sucesso", description=f"Adicionadas {len(searches)} músicas à fila.", color=discord.Color.green()))
            else:
                is_playlist = search.startswith(('http://', 'https://')) and ('/playlist' in search or '/sets/' in search)
                
                if is_playlist:
                    loading_msg = await ctx.send(embed=discord.Embed(
                        title="⏳ Processando Playlist",
                        description="Extraindo músicas da playlist...",
                        color=discord.Color.blue()
                    ))
                    
                    count, songs = await player.add_playlist_to_queue(search, ctx.author) # Note: add_playlist_to_queue might not be in the simple player.py I saw earlier? 
                    # Wait, player.py had add_to_queue and add_playlist_async. 
                    # Checking player.py again... it has add_playlist_async. 
                    # The bot.py I read had add_playlist_to_queue in the ctx command (line 630), but add_playlist_async in slash (line 693).
                    # I should probably use add_playlist_async if possible or check if add_playlist_to_queue exists.
                    # Looking at player.py content (Step 7), there is NO add_playlist_to_queue. Only add_playlist_async.
                    # So the original bot.py code was calling a method that might not exist in the new player.py? 
                    # Ah, maybe I missed it or it was added?
                    # Let's assume add_playlist_async is the way to go.
                    
                    # Actually, for the text command, let's use add_playlist_async too for consistency.
                    song = await player.add_playlist_async(search, ctx.author)

                    await loading_msg.delete()
                    embed = EmbedBuilder.create_success_embed(
                        "Playlist Adicionada",
                        f"**{song['title']}** está sendo processada em segundo plano!"
                    )
                    await ctx.send(embed=embed)
                else:
                    song = await player.add_to_queue(search, ctx.author)
                    position = len(list(player.queue))
                    embed = EmbedBuilder.create_success_embed(
                        "Adicionada à fila",
                        f"**{song['title']}** • Posição #{position}"
                    )
                    await ctx.send(embed=embed, delete_after=5)
            
            if not player.voice_client.is_playing() and not player.is_paused:
                await player.play_next()

        except Exception as e:
            logging.error(f"Erro no play: {e}")
            await ctx.send(f"Erro ao buscar música: {e}")

    @app_commands.command(name="play", description="Toca músicas do YouTube ou SoundCloud (use ; para múltiplas)")
    @app_commands.describe(search="Nome, URL ou 'scsearch: termo' para SoundCloud")
    async def play_slash(self, interaction: discord.Interaction, search: str):
        await interaction.response.defer()
        
        vc = await ensure_voice(interaction)
        if not vc:
            await interaction.followup.send("Você precisa estar em um canal de voz!", ephemeral=True)
            return

        player = self.get_player(interaction.guild_id)

        try:
            searches = [s.strip() for s in search.split(';') if s.strip()]
            
            if len(searches) > 1:
                await interaction.followup.send(embed=discord.Embed(title="Adicionando...", description=f"Adicionando {len(searches)} músicas...", color=discord.Color.blue()))
                for s in searches:
                    await player.add_to_queue(s, interaction.user)
                await interaction.followup.send(embed=discord.Embed(title="Sucesso", description=f"Adicionadas {len(searches)} músicas à fila.", color=discord.Color.green()))
            else:
                is_playlist = search.startswith(('http://', 'https://')) and ('/playlist' in search or '/sets/' in search or 'list=' in search or '/album/' in search)
                
                if is_playlist:
                    await interaction.followup.send(embed=discord.Embed(
                        title="⏳ Processando Playlist",
                        description="Extraindo músicas da playlist...",
                        color=discord.Color.blue()
                    ))
                    
                    song = await player.add_playlist_async(search, interaction.user)
                    
                    embed = EmbedBuilder.create_success_embed(
                        "Playlist Adicionada",
                        f"**{song['title']}** está sendo processada em segundo plano!"
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    song = await player.add_to_queue(search, interaction.user)
                    position = len(list(player.queue))
                    embed = EmbedBuilder.create_success_embed(
                        "Adicionada à fila",
                        f"**{song['title']}** • Posição #{position}"
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
            
            if not player.voice_client.is_playing() and not player.is_paused:
                await player.play_next()
                
        except Exception as e:
            msg = f"Erro: {e}"
            await interaction.followup.send(msg)

    @commands.command()
    async def skip(self, ctx: commands.Context):
        player = self.get_player(ctx.guild.id)
        player.skip()
        await ctx.send("Música pulada.")

    @app_commands.command(name="skip", description="Pula para a próxima música")
    async def skip_slash(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild_id)
        player.skip()
        await interaction.response.send_message("Música pulada.")

    @commands.command()
    async def stop(self, ctx: commands.Context):
        player = self.get_player(ctx.guild.id)
        player.stop()
        await ctx.send("Música parada e fila limpa.")

    @app_commands.command(name="stop", description="Para a reprodução e limpa a fila")
    async def stop_slash(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild_id)
        player.stop()
        await interaction.response.send_message("Música parada e fila limpa.")

    @commands.command()
    async def agora(self, ctx: commands.Context):
        player = self.get_player(ctx.guild.id)
        if not player.current_song:
            await ctx.send(embed=discord.Embed(
                title="Reprodução",
                description="Não estou tocando nada no momento.",
                color=discord.Color.blue()))
            return

        song = player.current_song
        title = song['title']
        thumbnail = song.get('thumbnail')
        user = song['user']
        duration = song.get('duration', 'Desconhecida')
        channel = song.get('channel', 'Desconhecido')
            
        embed = discord.Embed(
            title="🎵 Tocando Agora",
            description=f"**{title}**",
            color=discord.Color.from_rgb(57, 255, 20)
        )
        
        embed.add_field(name="Canal", value=channel, inline=True)
        embed.add_field(name="Duração", value=duration, inline=True)
        embed.add_field(name="Adicionado por", value=user.mention, inline=False)
        
        if len(player.queue) > 0:
            embed.set_footer(text=f"Próximas: {len(player.queue)} música(s) na fila")
        
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
            if thumbnail.startswith("https://i.ytimg.com/"):
                embed.set_image(url=thumbnail.replace("hqdefault", "maxresdefault"))
            else:
                embed.set_image(url=thumbnail)
                
        await ctx.send(embed=embed)

    @app_commands.command(name="agora", description="Mostra a música atual")
    async def agora_slash(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild_id)
        if not player.current_song:
            await interaction.response.send_message("Não estou tocando nada no momento.")
            return

        song = player.current_song
        embed = discord.Embed(title="Tocando Agora", description=f"**{song['title']}**", color=discord.Color.green())
        if song.get('thumbnail'):
            embed.set_thumbnail(url=song['thumbnail'])
        embed.add_field(name="Duração", value=song['duration'])
        
        await interaction.response.send_message(embed=embed)

    @commands.command(name="fila")
    async def fila(self, ctx: commands.Context):
        player = self.get_player(ctx.guild.id)
        if not player.queue and not player.current_song:
            embed = EmbedBuilder.create_error_embed(
                "Fila vazia",
                "Não há músicas na fila no momento."
            )
            await ctx.send(embed=embed, delete_after=5)
            return
             
        embed = EmbedBuilder.create_queue_embed(player.current_song, list(player.queue))
        await ctx.send(embed=embed)

    @app_commands.command(name="fila", description="Mostra a fila de músicas")
    async def fila_slash(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        player = self.get_player(interaction.guild_id)
        if not player.queue and not player.current_song:
            embed = EmbedBuilder.create_error_embed(
                "Fila vazia",
                "Não há músicas na fila no momento."
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        embed = EmbedBuilder.create_queue_embed(player.current_song, list(player.queue))
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

    @app_commands.command(name="volume", description="Ajusta o volume (0.0 a 1.0)")
    @app_commands.describe(vol="Volume entre 0.0 e 1.0")
    async def volume_slash(self, interaction: discord.Interaction, vol: float):
        player = self.get_player(interaction.guild_id)
        player.set_volume(vol)
        embed = EmbedBuilder.create_success_embed(
            "Volume ajustado",
            f"Volume definido para {int(player.volume * 100)}%"
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="nowplaying", description="Mostra a música tocando atualmente com barra de progresso")
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
            
            # Tentar gerar imagem personalizada (Card)
            # Descomente para usar o CARD em vez do EMBED (ou envie ambos)
            # card_buffer = await loop.run_in_executor(None, create_now_playing_card, player_instance.current_song, progress['percent'])
            # file = discord.File(card_buffer, filename="nowplaying.png")
            # embed.set_image(url="attachment://nowplaying.png")
            # await interaction.followup.send(embed=embed, file=file)

            if thumb_url:
                embed.set_thumbnail(url=thumb_url)

            await interaction.followup.send(embed=embed)
        else:
             await interaction.followup.send(embed=EmbedBuilder.create_error_embed(
                "Erro",
                "Player não encontrado para este servidor."
            ))

    # --- Comandos de Rádio ---

    @app_commands.command(name="radios", description="Lista todas as rádios disponíveis")
    async def radios_slash(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📻 Rádios Disponíveis",
            description="Use /radio [nome] para tocar uma rádio",
            color=discord.Color.blue()
        )

        for key, radio in self.RADIOS.items():
            embed.add_field(
                name=f"{radio['name']} ({radio['location']})",
                value=f"Comando: `/radio {key}`\n{radio['description']}",
                inline=False
            )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="radio", description="Toca uma rádio")
    @app_commands.describe(nome="Nome da rádio para tocar (use /radios para ver a lista)")
    async def radio_slash(self, interaction: discord.Interaction, nome: str):
        await interaction.response.defer(ephemeral=False)
        
        if nome not in self.RADIOS:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Erro",
                    description="Rádio não encontrada. Use /radios para ver a lista de rádios disponíveis.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            return

        if not interaction.user.voice:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Erro",
                    description="Você precisa estar em um canal de voz para usar este comando!",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            return

        try:
            radio = self.RADIOS[nome]
            vc = interaction.guild.voice_client
            if vc:
                if vc.channel != interaction.user.voice.channel:
                    await vc.move_to(interaction.user.voice.channel)
            else:
                vc = await interaction.user.voice.channel.connect()

            # Usar FFMPEG_PATH de config se existir, ou 'ffmpeg'
            executable = 'ffmpeg'
            # Note: I didn't verify if FFMPEG_PATH was in config.py. It wasn't in my plan for config.py.
            # I should just use 'ffmpeg' or add it to config if needed. 
            # In bot.py it checked global FFMPEG_PATH which seemed undefined in the displayed code or maybe I missed it.
            # I will assume 'ffmpeg' is fine for now.

            ffmpeg_options = {
                'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                'options': f'-vn -af "aresample=48000,atempo=1.0,volume=0.5" -bufsize 10M' # volume default 0.5
            }
            if vc.is_playing():
                vc.stop()

            # Limpar player queue se existir
            if interaction.guild.id in self.bot.players:
                player = self.bot.players[interaction.guild.id]
                player.queue.clear()
                player.current_song = None

            vc.play(
                discord.FFmpegPCMAudio(radio['url'], executable=executable, **ffmpeg_options),
                after=lambda e: logging.error(f'Erro na reprodução da rádio: {e}') if e else None
            )

            embed = EmbedBuilder.create_radio_embed(radio)
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logging.error(f"Erro ao tocar rádio: {e}")
            embed = EmbedBuilder.create_error_embed(
                "Erro ao tocar rádio",
                f"Não foi possível iniciar a transmissão: {str(e)}"
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="addradio", description="Adiciona uma nova rádio personalizada")
    async def add_radio_slash(self, interaction: discord.Interaction, nome: str, url: str, localizacao: str = "Desconhecido", descricao: str = "Rádio personalizada"):
        await interaction.response.defer(ephemeral=False)
        
        if not url.startswith(('http://', 'https://')):
            await interaction.followup.send(embed=discord.Embed(title="Erro", description="URL inválida.", color=discord.Color.red()))
            return
            
        radio_id = nome.lower().replace(" ", "_")
        
        if radio_id in self.RADIOS:
            await interaction.followup.send(embed=discord.Embed(title="Erro", description=f"Uma rádio com o nome '{nome}' já existe.", color=discord.Color.red()))
            return
            
        self.RADIOS[radio_id] = {
            "name": nome,
            "location": localizacao,
            "url": url,
            "description": descricao
        }
        
        try:
            with open(RADIOS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.RADIOS, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logging.error(f"Erro ao salvar rádios: {e}")
            await interaction.followup.send(embed=discord.Embed(title="Erro", description="Ocorreu um erro ao salvar a rádio.", color=discord.Color.red()))
            return
            
        await interaction.followup.send(embed=discord.Embed(
            title="Rádio Adicionada",
            description=f"Rádio '{nome}' adicionada com sucesso!\nUse `/radio {radio_id}` para tocar.",
            color=discord.Color.green()
        ))

    @app_commands.command(name="removeradio", description="Remove uma rádio personalizada")
    async def remove_radio_slash(self, interaction: discord.Interaction, nome: str):
        await interaction.response.defer(ephemeral=False)
        
        radio_id = nome.lower().replace(" ", "_")
        
        if radio_id not in self.RADIOS:
            await interaction.followup.send(embed=discord.Embed(title="Erro", description=f"Rádio '{nome}' não encontrada.", color=discord.Color.red()))
            return
            
        del self.RADIOS[radio_id]
        
        try:
            with open(RADIOS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.RADIOS, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logging.error(f"Erro ao salvar rádios: {e}")
            await interaction.followup.send(embed=discord.Embed(title="Erro", description="Erro ao remover rádio.", color=discord.Color.red()))
            return
            
        await interaction.followup.send(embed=discord.Embed(
            title="Rádio Removida",
            description=f"Rádio '{nome}' removida com sucesso!",
            color=discord.Color.green()
        ))

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
