import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio
import os
import logging
from dotenv import load_dotenv
import json
import aiofiles
from cachetools import TTLCache
import psutil
import time
from functools import lru_cache
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
import uvicorn
from player import MusicPlayer
import socket

# Configuração do logging
logging.getLogger("uvicorn.error").propagate = False
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# --- Gerenciamento de Token e Configuração ---
TOKEN_FILE = "token.json"

def load_token_from_json():
    """Carrega o token do arquivo token.json."""
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r") as f:
                data = json.load(f)
                return data.get("DISCORD_TOKEN")
        except (json.JSONDecodeError, IOError) as e:
            logging.error(f"Erro ao ler {TOKEN_FILE}: {e}")
            return None
    return None

def save_token_to_json(token: str):
    """Salva o token no arquivo token.json."""
    with open(TOKEN_FILE, "w") as f:
        json.dump({"DISCORD_TOKEN": token}, f)

def prompt_token_terminal():
    """Solicita token via input no terminal."""
    print("\n" + "="*60)
    print("🎵 DISCORD MUSIC BOT - CONFIGURAÇÃO DE TOKEN")
    print("="*60)
    print("\nNenhum token válido encontrado no sistema.")
    print("\nOpções:")
    print("1. Inserir token agora (via terminal)")
    print("2. Usar interface web (http://localhost:8000)")
    print("3. Pular por enquanto (API apenas)")
    print("\nInstruções para obter o token:")
    print("- Acesse: https://discord.com/developers/applications")
    print("- Clique em 'New Application'")
    print("- Vá para 'Bot' e clique em 'Add Bot'")
    print("- Clique em 'Copy Token'")
    print("="*60)
    
    try:
        choice = input("\nEscolha uma opção (1/2/3): ").strip()
    except (EOFError, OSError):
        logging.warning("\n⚠️ Ambiente não interativo detectado (Docker/Systemd).")
        logging.info("⏳ Pulando configuração de token via terminal.")
        return None
    
    if choice == "1":
        try:
            token = input("\nCole o token do Discord: ").strip()
        except (EOFError, OSError):
            return None
            
        if len(token) > 50:
            save_token_to_json(token)
            logging.info("✅ Token salvo com sucesso!")
            return token
        else:
            logging.error("❌ Token inválido (muito curto)")
            return None
    elif choice == "2":
        logging.info("\n✅ Acesse: http://localhost:8000 para configurar o token")
        return None
    else:
        logging.info("\n⏳ Pulando configuração de token. Apenas API rodando.")
        return None


# Carrega variáveis do arquivo .env (se existir) para o ambiente
load_dotenv()
# Configurar intents
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True

# Inicializar FastAPI
app = FastAPI(
    title="Discord Music Bot API",
    description="API para controlar o bot de música do Discord.",
    version="1.0.0",
)

# Inicializar o bot
bot = commands.Bot(command_prefix='/', intents=intents)

# Gerenciador de players (Multi-Guild)
players = {} # Dict[guild_id, MusicPlayer]

def get_player(guild_id) -> MusicPlayer:
    if guild_id not in players:
        players[guild_id] = MusicPlayer(guild_id, bot)
    return players[guild_id]

# Variáveis globais para compatibilidade com código legacy
current_song = None
song_queue = []
playlist_processing_task = None
playlist_cancel_flag = False
current_volume = 0.5
is_looping = False
is_shuffling = False
is_paused = False

# Caches e variáveis globais
playlist_cache = {}
music_info_cache = TTLCache(maxsize=100, ttl=3600)
last_resource_check = 0
resource_check_interval = 60
cpu_usage = 0
memory_usage = 0

# Diretório para armazenar playlists
PLAYLIST_DIR = "playlist"

# Caminho para o executável do FFmpeg (será definido pela GUI)
FFMPEG_PATH = None

# Verificar se o diretório de playlists existe, caso contrário, criar
if not os.path.exists(PLAYLIST_DIR):
    try:
        os.makedirs(PLAYLIST_DIR)
        logging.info(f"Diretório '{PLAYLIST_DIR}' criado com sucesso")
    except Exception as e:
        logging.error(f"Erro ao criar diretório '{PLAYLIST_DIR}': {e}")

# Carregar rádios do arquivo JSON
def load_radios():
    """Carregar rádios do arquivo JSON"""
    if os.path.exists("radios.json"):
        try:
            with open("radios.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Erro ao carregar rádios: {e}")
    return {}

# Dicionário de rádios disponíveis
RADIOS = load_radios()

# Função para carregar playlists de forma assíncrona
async def load_playlist_async(playlist_name):
    # Verificar se já está no cache
    if playlist_name in playlist_cache:
        return playlist_cache[playlist_name]
    
    playlist_path = os.path.join(PLAYLIST_DIR, f"{playlist_name}.txt")
    
    if not os.path.exists(playlist_path):
        return None
    
    try:
        # Usar aiofiles para leitura assíncrona
        async with aiofiles.open(playlist_path, 'r', encoding='utf-8') as f:
            content = await f.read()
            lines = [line.strip() for line in content.split('\n') if line.strip() and not line.strip().startswith('#')]
            
            # Armazenar no cache
            playlist_cache[playlist_name] = lines
            return lines
    except Exception as e:
        logging.error(f"Erro ao carregar playlist {playlist_name}: {e}")
        return None

# Função para monitorar recursos do sistema
async def check_system_resources():
    global last_resource_check, cpu_usage, memory_usage
    
    # Verificar se já passou tempo suficiente desde a última verificação
    current_time = time.time()
    if current_time - last_resource_check < resource_check_interval:
        return cpu_usage, memory_usage
    
    last_resource_check = current_time
    
    try:
        # Obter uso de CPU e memória
        cpu_usage = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        memory_usage = memory.percent
        
        # Registrar no log se estiver acima de limites
        if cpu_usage > 80:
            logging.warning(f"Uso de CPU alto: {cpu_usage}%")
        
        if memory_usage > 80:
            logging.warning(f"Uso de memória alto: {memory_usage}%")
            
        # Limpar cache se memória estiver muito alta
        if memory_usage > 90:
            logging.warning("Limpando caches devido ao alto uso de memória")
            music_info_cache.clear()
            playlist_cache.clear()
            
        return cpu_usage, memory_usage
    except Exception as e:
        logging.error(f"Erro ao verificar recursos do sistema: {e}")
        return None, None



# Função para configurar eventos e comandos
def setup_bot():
    @bot.event
    async def on_ready() -> None:
        logging.info(f'O bot fez login como: {bot.user}')
        
        # Sincronizar comandos slash quando iniciar
        try:
            synced = await bot.tree.sync()
            logging.info(f"Sincronizados {len(synced)} comandos slash")
        except Exception as e:
            logging.error(f"Erro ao sincronizar comandos: {e}")

    # Adicionar um handler para erros de comando não encontrado
    @bot.event
    async def on_command_error(ctx, error):
        if isinstance(error, commands.errors.CommandNotFound):
            # Ignorar esse erro específico para evitar mensagens duplicadas
            pass
        else:
            # Registrar outros erros
            logging.error(f"Erro em comando: {error}")

    # Comando de texto
    @bot.command()
    async def join(ctx: commands.Context):
        vc = await ensure_voice(ctx)
        if vc:
            await ctx.send(embed=discord.Embed(
                title="Conectado",
                description=f"Juntei-me ao canal **{vc.channel.name}**.",
                color=discord.Color.green()))

    # Comando slash
    @bot.tree.command(name="join", description="Entra no canal de voz")
    async def join_slash(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        vc = await ensure_voice(interaction)
        if vc:
            await interaction.followup.send(embed=discord.Embed(
                title="Conectado",
                description=f"Juntei-me ao canal **{vc.channel.name}**.",
                color=discord.Color.green()))

    # Comando de texto
    @bot.command()
    async def leave(ctx: commands.Context):
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

    # Comando slash
    @bot.tree.command(name="leave", description="Sai do canal de voz")
    async def leave_slash(interaction: discord.Interaction):
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

    # Comando para sair de todos os canais em todos os servidores
    @bot.command(name="sair_todos")
    async def sair_todos(ctx: commands.Context):
        """Comando para sair de todos os canais de voz em todos os servidores"""
        count = 0
        # Percorrer todas as guildas e tentar desconectar
        for guild in bot.guilds:
            voice_client = guild.voice_client
            if voice_client and voice_client.is_connected():
                try:
                    # Limpar o player desta guild
                    if guild.id in players:
                        players[guild.id].stop()
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
    
    # Comando slash para sair de todos os canais
    @bot.tree.command(name="sair_todos", description="Sai de todos os canais de voz em todos os servidores")
    async def sair_todos_slash(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        count = 0
        # Percorrer todas as guildas e tentar desconectar
        for guild in bot.guilds:
            voice_client = guild.voice_client
            if voice_client and voice_client.is_connected():
                try:
                    # Limpar o player desta guild
                    if guild.id in players:
                        players[guild.id].stop()
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

    # Comando de texto
    @bot.command()
    async def play(ctx: commands.Context, *, search: str):
        vc = await ensure_voice(ctx)
        if not vc: return
        
        player = get_player(ctx.guild.id)
        
        try:
            # Check for multiple songs
            searches = [s.strip() for s in search.split(';') if s.strip()]
            
            if len(searches) > 1:
                await ctx.send(embed=discord.Embed(title="Adicionando...", description=f"Adicionando {len(searches)} músicas...", color=discord.Color.blue()))
                for s in searches:
                    await player.add_to_queue(s, ctx.author)
                await ctx.send(embed=discord.Embed(title="Sucesso", description=f"Adicionadas {len(searches)} músicas à fila.", color=discord.Color.green()))
            else:
                song = await player.add_to_queue(search, ctx.author)
                embed = discord.Embed(
                    title="Adicionada à Fila",
                    description=f"**{song['title']}**",
                    color=discord.Color.green()
                )
                if song.get('thumbnail'):
                    embed.set_thumbnail(url=song['thumbnail'])
                await ctx.send(embed=embed)
            
            # Start playback if idle
            if not player.voice_client.is_playing() and not player.is_paused:
                await player.play_next()

        except Exception as e:
            logging.error(f"Erro no play: {e}")
            await ctx.send(f"Erro ao buscar música: {e}")



    # Comando slash
    @bot.tree.command(name="play", description="Toca uma ou várias músicas (separadas por ;)")
    @app_commands.describe(search="Nome ou URL da música")
    async def play_slash(interaction: discord.Interaction, search: str):
        await interaction.response.defer()
        
        vc = await ensure_voice(interaction)
        if not vc:
            await interaction.followup.send("Você precisa estar em um canal de voz!", ephemeral=True)
            return

        player = get_player(interaction.guild_id)

        try:
            # Check for multiple songs
            searches = [s.strip() for s in search.split(';') if s.strip()]
            
            if len(searches) > 1:
                await interaction.followup.send(embed=discord.Embed(title="Adicionando...", description=f"Adicionando {len(searches)} músicas...", color=discord.Color.blue()))
                for s in searches:
                    await player.add_to_queue(s, interaction.user)
                await interaction.followup.send(embed=discord.Embed(title="Sucesso", description=f"Adicionadas {len(searches)} músicas à fila.", color=discord.Color.green()))
            else:
                song = await player.add_to_queue(search, interaction.user)
                embed = discord.Embed(
                    title="Adicionada à Fila",
                    description=f"**{song['title']}**",
                    color=discord.Color.green()
                )
                if song.get('thumbnail'):
                    embed.set_thumbnail(url=song['thumbnail'])
                await interaction.followup.send(embed=embed)
            
            # Start playback if idle
            if not player.voice_client.is_playing() and not player.is_paused:
                await player.play_next()
                
        except Exception as e:
            msg = f"Erro: {e}"
            await interaction.followup.send(msg)



    # Comando de texto
    @bot.command()
    async def skip(ctx: commands.Context):
        player = get_player(ctx.guild.id)
        player.skip()
        await ctx.send("Música pulada.")

    # Comando slash
    @bot.tree.command(name="skip", description="Pula para a próxima música")
    async def skip_slash(interaction: discord.Interaction):
        player = get_player(interaction.guild_id)
        player.skip()
        await interaction.response.send_message("Música pulada.")

    # Comando de texto
    @bot.command()
    async def stop(ctx: commands.Context):
        player = get_player(ctx.guild.id)
        player.stop()
        await ctx.send("Música parada e fila limpa.")

    # Comando slash
    @bot.tree.command(name="stop", description="Para a reprodução e limpa a fila")
    async def stop_slash(interaction: discord.Interaction):
        player = get_player(interaction.guild_id)
        player.stop()
        await interaction.response.send_message("Música parada e fila limpa.")

    # Comando de texto
    @bot.command()
    async def agora(ctx: commands.Context):
        player = get_player(ctx.guild.id)
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
            
        # Criar embed melhorado
        embed = discord.Embed(
            title="🎵 Tocando Agora",
            description=f"**{title}**",
            color=discord.Color.from_rgb(57, 255, 20)  # Verde vibrante
        )
        
        # Adicionar campos com informações extras
        embed.add_field(name="Canal", value=channel, inline=True)
        embed.add_field(name="Duração", value=duration, inline=True)
        embed.add_field(name="Adicionado por", value=user.mention, inline=False)
        
        # Configurar o rodapé
        if len(player.queue) > 0:
            embed.set_footer(text=f"Próximas: {len(player.queue)} música(s) na fila")
        
        # Adicionar imagem de capa, se disponível
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
            # Adicionar uma imagem grande na parte inferior para um visual mais rico
            if thumbnail.startswith("https://i.ytimg.com/"):
                # Para miniaturas do YouTube, podemos tentar obter uma versão maior
                embed.set_image(url=thumbnail.replace("hqdefault", "maxresdefault"))
            else:
                embed.set_image(url=thumbnail)
                
        await ctx.send(embed=embed)

    # Comando slash
    @bot.tree.command(name="agora", description="Mostra a música atual")
    async def agora_slash(interaction: discord.Interaction):
        player = get_player(interaction.guild_id)
        if not player.current_song:
            await interaction.response.send_message("Não estou tocando nada no momento.")
            return

        song = player.current_song
        embed = discord.Embed(title="Tocando Agora", description=f"**{song['title']}**", color=discord.Color.green())
        if song.get('thumbnail'):
            embed.set_thumbnail(url=song['thumbnail'])
        embed.add_field(name="Duração", value=song['duration'])
        
        await interaction.response.send_message(embed=embed)

        await interaction.response.send_message(embed=embed)

    # Comando de texto
    @bot.command(name="fila")
    async def fila(ctx: commands.Context):
        player = get_player(ctx.guild.id)
        if not player.queue and not player.current_song:
             await ctx.send("A fila está vazia.")
             return
             
        embed = discord.Embed(title="Fila de Reprodução", color=discord.Color.blue())
        if player.current_song:
            embed.add_field(name="Tocando Agora", value=player.current_song['title'], inline=False)
            
        if player.queue:
            queue_list = "\n".join([f"{i+1}. {s['title']}" for i, s in enumerate(list(player.queue)[:10])])
            if len(player.queue) > 10:
                queue_list += f"\n... e mais {len(player.queue)-10}"
            embed.add_field(name="Próximas", value=queue_list, inline=False)
            
        await ctx.send(embed=embed)




        if not song_queue and not current_song:
            await ctx.send(embed=discord.Embed(
                title="Fila de Reprodução",
                description="A fila está vazia.",
                color=discord.Color.blue()))
            return

        # Criar um embed mais detalhado para a fila
        embed = discord.Embed(
            title="📋 Fila de Reprodução",
            color=discord.Color.from_rgb(114, 137, 218)  # Cor do Discord
        )
        
        # Função para truncar texto longo
        def truncate_text(text, max_length=50):
            return text[:max_length] + "..." if len(text) > max_length else text
        
        # Adicionar informações sobre a música atual
        if current_song:
            try:
                # Extrair todas as informações da música atual
                if len(current_song) >= 6:  # Formato novo com duração e canal
                    current_title, _, current_thumbnail, current_user, current_duration, current_channel = current_song
                else:  # Compatibilidade com formato antigo
                    current_title, _, current_thumbnail, current_user = current_song
                    current_duration = "Desconhecida"
                    current_channel = "Desconhecido"
                
                # Truncar título longo
                current_title = truncate_text(current_title, 70)
                current_channel = truncate_text(current_channel, 30)
                
                user_mention = current_user.mention if hasattr(current_user, 'mention') else "Desconhecido"
                
                embed.add_field(
                    name="🎵 Tocando Agora",
                    value=f"**{current_title}**\n"
                          f"▸ ⏱️ **Duração:** {current_duration}\n"
                          f"▸ 🎤 **Canal:** {current_channel}\n"
                          f"▸ 👤 **Adicionado por:** {user_mention}",
                    inline=False
                )
                
                # Adicionar separador visual
                embed.add_field(
                    name="⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯",
                    value="",
                    inline=False
                )
                
                # Adicionar thumbnail da música atual
                if current_thumbnail:
                    embed.set_thumbnail(url=current_thumbnail)
            except Exception as e:
                logging.error(f"Erro ao criar campo de música atual: {e}")
                # Continuar com a exibição da fila mesmo se houver erro na música atual
        
        # Adicionar as próximas músicas da fila
        if song_queue:
            # Limitar o número total de músicas para evitar estourar o limite
            display_count = min(8, len(song_queue))
            
            queue_text = ""
            total_length = 0
            
            for i, song_info in enumerate(song_queue[:display_count], 1):
                try:
                    # Verificar o formato da música na fila
                    if len(song_info) >= 6:  # Formato novo
                        title, _, _, user, duration, channel = song_info
                    else:  # Formato antigo
                        title, _, _, user = song_info
                        duration = "?"
                        channel = "?"
                    
                    # Truncar títulos longos para economizar espaço
                    title = truncate_text(title, 70)
                    
                    display_name = user.display_name if hasattr(user, 'display_name') else "Desconhecido"
                    display_name = truncate_text(display_name, 15)
                    
                    # Criar linha para esta música e verificar se adicionar não ultrapassará o limite
                    line = f"**{i}.** {title}\n   ▸ ⏱️ **Duração:** {duration} | 👤 **Por:** {display_name}\n"
                    
                    # Verificar se adicionar esta linha excederá o limite do Discord
                    if total_length + len(line) > 900:  # Margem de segurança abaixo de 1024
                        queue_text += f"\n... e mais {len(song_queue) - i + 1} música(s)"
                        break
                        
                    queue_text += line
                    total_length += len(line)
                except Exception as e:
                    logging.error(f"Erro ao processar música {i} da fila: {e}")
                    # Continuar com as próximas músicas
            
            if len(song_queue) > display_count and total_length < 900:
                queue_text += f"\n... e mais {len(song_queue) - display_count} música(s)"
                
            embed.add_field(
                name="📑 Próximas Músicas",
                value=queue_text or "Nenhuma música na fila",
                inline=False
            )
        
        # Adicionar informações de rodapé
        embed.set_footer(text=f"Total na fila: {len(song_queue)} música(s)")
        
        await ctx.send(embed=embed)

    # Comando slash
    @bot.tree.command(name="fila", description="Mostra a fila de músicas")
    # @bot.tree.command(name="fila", description="Mostra a fila de músicas")
    async def fila_slash_legacy(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        if not song_queue and not current_song:
            await interaction.followup.send(embed=discord.Embed(
                title="Fila de Reprodução",
                description="A fila está vazia.",
                color=discord.Color.blue()))
            return

        # Criar um embed mais detalhado para a fila
        embed = discord.Embed(
            title="📋 Fila de Reprodução",
            color=discord.Color.from_rgb(114, 137, 218)  # Cor do Discord
        )
        
        # Função para truncar texto longo
        def truncate_text(text, max_length=50):
            return text[:max_length] + "..." if len(text) > max_length else text
        
        # Adicionar informações sobre a música atual
        if current_song:
            try:
                # Extrair todas as informações da música atual
                if len(current_song) >= 6:  # Formato novo com duração e canal
                    current_title, _, current_thumbnail, current_user, current_duration, current_channel = current_song
                else:  # Compatibilidade com formato antigo
                    current_title, _, current_thumbnail, current_user = current_song
                    current_duration = "Desconhecida"
                    current_channel = "Desconhecido"
                
                # Truncar título longo
                current_title = truncate_text(current_title, 70)
                current_channel = truncate_text(current_channel, 30)
                
                user_mention = current_user.mention if hasattr(current_user, 'mention') else "Desconhecido"
                
                embed.add_field(
                    name="🎵 Tocando Agora",
                    value=f"**{current_title}**\n"
                          f"▸ ⏱️ **Duração:** {current_duration}\n"
                          f"▸ 🎤 **Canal:** {current_channel}\n"
                          f"▸ 👤 **Adicionado por:** {user_mention}",
                    inline=False
                )
                
                # Adicionar separador visual
                embed.add_field(
                    name="⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯",
                    value="",
                    inline=False
                )
                
                # Adicionar thumbnail da música atual
                if current_thumbnail:
                    embed.set_thumbnail(url=current_thumbnail)
            except Exception as e:
                logging.error(f"Erro ao criar campo de música atual: {e}")
                # Continuar com a exibição da fila mesmo se houver erro na música atual
        
        # Adicionar as próximas músicas da fila
        if song_queue:
            # Limitar o número total de músicas para evitar estourar o limite
            display_count = min(8, len(song_queue))
            
            queue_text = ""
            total_length = 0
            
            for i, song_info in enumerate(song_queue[:display_count], 1):
                try:
                    # Verificar o formato da música na fila
                    if len(song_info) >= 6:  # Formato novo
                        title, _, _, user, duration, channel = song_info
                    else:  # Formato antigo
                        title, _, _, user = song_info
                        duration = "?"
                        channel = "?"
                    
                    # Truncar títulos longos para economizar espaço
                    title = truncate_text(title, 70)
                    
                    display_name = user.display_name if hasattr(user, 'display_name') else "Desconhecido"
                    display_name = truncate_text(display_name, 15)
                    
                    # Criar linha para esta música e verificar se adicionar não ultrapassará o limite
                    line = f"**{i}.** {title}\n   ▸ ⏱️ **Duração:** {duration} | 👤 **Por:** {display_name}\n"
                    
                    # Verificar se adicionar esta linha excederá o limite do Discord
                    if total_length + len(line) > 900:  # Margem de segurança abaixo de 1024
                        queue_text += f"\n... e mais {len(song_queue) - i + 1} música(s)"
                        break
                        
                    queue_text += line
                    total_length += len(line)
                except Exception as e:
                    logging.error(f"Erro ao processar música {i} da fila: {e}")
                    # Continuar com as próximas músicas
            
            if len(song_queue) > display_count and total_length < 900:
                queue_text += f"\n... e mais {len(song_queue) - display_count} música(s)"
                
            embed.add_field(
                name="📑 Próximas Músicas",
                value=queue_text or "Nenhuma música na fila",
                inline=False
            )
        
        # Adicionar informações de rodapé
        embed.set_footer(text=f"Total na fila: {len(song_queue)} música(s)")
        
        await interaction.followup.send(embed=embed)

    # Comando de texto
    @bot.command()
    async def volume(ctx: commands.Context, vol: float):
        player = get_player(ctx.guild.id)
        player.set_volume(vol)
        await ctx.send(f"Volume ajustado para {int(player.volume * 100)}%")

    # Comando slash
    @bot.tree.command(name="volume", description="Ajusta o volume (0.0 a 1.0)")
    @app_commands.describe(vol="Volume entre 0.0 e 1.0")
    async def volume_slash(interaction: discord.Interaction, vol: float):
        player = get_player(interaction.guild_id)
        player.set_volume(vol)
        await interaction.response.send_message(f"Volume ajustado para {int(player.volume * 100)}%")




    # Comando de texto para reproduzir playlist a partir de arquivo
    @bot.command(name="playlist")
    async def playlist_command(ctx: commands.Context, filename: str = None):
        """Reproduz músicas de um arquivo de playlist .txt da pasta 'playlist'"""
        global playlist_processing_task, playlist_cancel_flag
        
        # Se nenhum nome de arquivo for fornecido, listar playlists disponíveis
        if filename is None:
            # Listar playlists disponíveis
            playlists = [f[:-4] for f in os.listdir(PLAYLIST_DIR) if f.endswith('.txt')]
            if not playlists:
                await ctx.send(embed=discord.Embed(
                    title="Playlists",
                    description="Não há playlists disponíveis.",
                    color=discord.Color.orange()))
                return
                
            await ctx.send(embed=discord.Embed(
                title="Playlists Disponíveis",
                description="\n".join(f"• {p}" for p in playlists),
                color=discord.Color.blue()))
            return
        
        # Resetar a flag de cancelamento antes de iniciar
        playlist_cancel_flag = False
        
        # Verificar recursos do sistema antes de processar
        await check_system_resources()
        
        # Verificar se o usuário está em um canal de voz
        vc = await ensure_voice(ctx)
        if not vc:
            return
            
        # Verificar se o arquivo existe
        if not filename.endswith('.txt'):
            filename += '.txt'  # Adicionar extensão se não foi fornecida
            
        file_path = os.path.join(PLAYLIST_DIR, filename)
        if not os.path.exists(file_path):
            await ctx.send(embed=discord.Embed(
                title="Erro",
                description=f"Arquivo '{filename}' não encontrado na pasta '{PLAYLIST_DIR}'.",
                color=discord.Color.red()))
            return
            
        # Função interna para processar a playlist
        async def process_playlist():
            try:
                with open(file_path, 'r', encoding='utf-8') as file:
                    lines = [line.strip() for line in file.readlines() if line.strip() and not line.strip().startswith('#')]
                    
                if not lines:
                    await ctx.send(embed=discord.Embed(
                        title="Erro",
                        description=f"O arquivo '{filename}' está vazio ou contém apenas comentários.",
                        color=discord.Color.red()))
                    return
                    
                # Enviar mensagem inicial
                await ctx.send(embed=discord.Embed(
                    title="Carregando Playlist",
                    description=f"Adicionando {len(lines)} músicas da playlist '{filename}' à fila...\n\n"
                                f"**Reprodução começará em breve. Aguarde a mensagem de conclusão.**",
                    color=discord.Color.blue()))
                    
                # Verificar se o bot já está tocando
                was_playing = vc.is_playing()
                    
                # Processar cada linha como uma música
                total_added = 0
                failed_tracks = []
                started_playback = False
                
                for i, search in enumerate(lines):
                    # Verificar flag de cancelamento
                    if playlist_cancel_flag:
                        logging.info(f"Processamento da playlist '{filename}' cancelado manualmente")
                        break
                        
                    try:
                        # Usar timeout para evitar bloqueios
                        title, url, thumbnail, duration, channel = await asyncio.wait_for(
                            extract_info(search), 
                            timeout=20
                        )
                        
                        # Verificar flag de cancelamento novamente após o processamento
                        if playlist_cancel_flag:
                            logging.info(f"Processamento da playlist '{filename}' cancelado após extract_info")
                            break
                            
                        song_queue.append((title, url, thumbnail, ctx.author, duration, channel))
                        total_added += 1
                        
                        # Se já processamos pelo menos 1 música e o bot não está tocando nada,
                        # iniciar a reprodução imediatamente
                        if not was_playing and not started_playback and not vc.is_playing():
                            # Verificar flag de cancelamento antes de iniciar reprodução
                            if playlist_cancel_flag:
                                logging.info(f"Playlist '{filename}' cancelada antes de iniciar reprodução")
                                break
                                
                            await play_next_legacy(ctx)
                            started_playback = True
                            
                    except asyncio.TimeoutError:
                        logging.error(f"Timeout ao processar '{search}' da playlist '{filename}'")
                        failed_tracks.append(f"{search} (timeout)")
                    except Exception as e:
                        logging.error(f"Erro ao processar '{search}' da playlist '{filename}': {e}")
                        failed_tracks.append(search)
                
                # Verificar se cancelamos o processamento
                if playlist_cancel_flag:
                    await ctx.send(embed=discord.Embed(
                        title="Processamento Cancelado",
                        description=f"O processamento da playlist '{filename}' foi cancelado.\n"
                                    f"Foram adicionadas {total_added} músicas antes do cancelamento.",
                        color=discord.Color.orange()))
                    return
                
                # Enviar mensagem de conclusão
                embed = discord.Embed(
                    title="Playlist Carregada",
                    description=f"**{total_added}** músicas da playlist '{filename}' foram adicionadas à fila por {ctx.author.mention}.",
                    color=discord.Color.green()
                ).set_footer(text=f"Fila: {len(song_queue)} música(s)")
                
                # Adicionar informações sobre músicas que falharam
                if failed_tracks:
                    embed.add_field(
                        name="⚠️ Algumas músicas não puderam ser adicionadas:",
                        value="\n".join(f"- {track[:50]}..." if len(track) > 50 else f"- {track}" for track in failed_tracks[:5]) + 
                              (f"\n... e mais {len(failed_tracks) - 5} falhas." if len(failed_tracks) > 5 else ""),
                        inline=False
                    )
                    
                await ctx.send(embed=embed)
                
                # Iniciar reprodução se não estiver tocando ainda e não iniciamos antes
                if not vc.is_playing() and not started_playback:
                    await play_next_legacy(ctx)
                    
            except Exception as e:
                logging.error(f"Erro ao processar playlist '{filename}': {e}")
                await ctx.send(embed=discord.Embed(
                    title="Erro",
                    description=f"Ocorreu um erro ao processar a playlist '{filename}':\n{str(e)[:500]}",
                    color=discord.Color.red()))
                
        # Criar e armazenar a tarefa para que possa ser cancelada
        playlist_processing_task = asyncio.create_task(process_playlist())

    # Comando slash para reproduzir playlist
    @bot.tree.command(name="playlist", description="Reproduz músicas de um arquivo de playlist .txt")
    @app_commands.describe(filename="Nome do arquivo de playlist (da pasta 'playlist')")
    async def playlist_slash(interaction: discord.Interaction, filename: str):
        """Comando slash para reproduzir músicas de um arquivo de playlist"""
        global playlist_processing_task, playlist_cancel_flag
        
        # Resetar a flag de cancelamento antes de iniciar
        playlist_cancel_flag = False
        
        await interaction.response.defer(ephemeral=False)
        
        # Verificar se o usuário está em um canal de voz
        vc = await ensure_voice(interaction)
        if not vc:
            await interaction.followup.send(embed=discord.Embed(
                title="Erro",
                description="Você precisa estar em um canal de voz!",
                color=discord.Color.red()))
            return
            
        # Verificar se o arquivo existe
        if not filename.endswith('.txt'):
            filename += '.txt'  # Adicionar extensão se não foi fornecida
            
        file_path = os.path.join(PLAYLIST_DIR, filename)
        if not os.path.exists(file_path):
            await interaction.followup.send(embed=discord.Embed(
                title="Erro",
                description=f"Arquivo '{filename}' não encontrado na pasta '{PLAYLIST_DIR}'.",
                color=discord.Color.red()))
            return
            
        # Adaptar o contexto para reutilizar o código
        class SlashContext:
            def __init__(self, interaction):
                self.interaction = interaction
                self.guild = interaction.guild
                self.author = interaction.user

            async def send(self, **kwargs):
                await interaction.followup.send(**kwargs)
                
        ctx = SlashContext(interaction)
        
        # Função interna para processar a playlist
        async def process_playlist():
            try:
                with open(file_path, 'r', encoding='utf-8') as file:
                    lines = [line.strip() for line in file.readlines() if line.strip() and not line.strip().startswith('#')]
                    
                if not lines:
                    await interaction.followup.send(embed=discord.Embed(
                        title="Erro",
                        description=f"O arquivo '{filename}' está vazio ou contém apenas comentários.",
                        color=discord.Color.red()))
                    return
                    
                # Enviar mensagem inicial
                await interaction.followup.send(embed=discord.Embed(
                    title="Carregando Playlist",
                    description=f"Adicionando {len(lines)} músicas da playlist '{filename}' à fila...\n\n"
                                f"**Reprodução começará em breve. Aguarde a mensagem de conclusão.**",
                    color=discord.Color.blue()))
                    
                # Verificar se o bot já está tocando
                was_playing = vc.is_playing()
                    
                # Processar cada linha como uma música
                total_added = 0
                failed_tracks = []
                started_playback = False
                
                for i, search in enumerate(lines):
                    # Verificar flag de cancelamento
                    if playlist_cancel_flag:
                        logging.info(f"Processamento da playlist '{filename}' cancelado manualmente")
                        break
                        
                    try:
                        # Usar timeout para evitar bloqueios
                        title, url, thumbnail, duration, channel = await asyncio.wait_for(
                            extract_info(search), 
                            timeout=20
                        )
                        
                        # Verificar flag de cancelamento novamente após o processamento
                        if playlist_cancel_flag:
                            logging.info(f"Processamento da playlist '{filename}' cancelado após extract_info")
                            break
                            
                        song_queue.append((title, url, thumbnail, ctx.author, duration, channel))
                        total_added += 1
                        
                        # Se já processamos pelo menos 1 música e o bot não está tocando nada,
                        # iniciar a reprodução imediatamente
                        if not was_playing and not started_playback and not vc.is_playing():
                            # Verificar flag de cancelamento antes de iniciar reprodução
                            if playlist_cancel_flag:
                                logging.info(f"Playlist '{filename}' cancelada antes de iniciar reprodução")
                                break
                                
                            await play_next_legacy(ctx)
                            started_playback = True
                            
                    except asyncio.TimeoutError:
                        logging.error(f"Timeout ao processar '{search}' da playlist '{filename}'")
                        failed_tracks.append(f"{search} (timeout)")
                    except Exception as e:
                        logging.error(f"Erro ao processar '{search}' da playlist '{filename}': {e}")
                        failed_tracks.append(search)
                
                # Verificar se cancelamos o processamento
                if playlist_cancel_flag:
                    await interaction.followup.send(embed=discord.Embed(
                        title="Processamento Cancelado",
                        description=f"O processamento da playlist '{filename}' foi cancelado.\n"
                                    f"Foram adicionadas {total_added} músicas antes do cancelamento.",
                        color=discord.Color.orange()))
                    return
                
                # Enviar mensagem de conclusão
                embed = discord.Embed(
                    title="Playlist Carregada",
                    description=f"**{total_added}** músicas da playlist '{filename}' foram adicionadas à fila por {ctx.author.mention}.",
                    color=discord.Color.green()
                ).set_footer(text=f"Fila: {len(song_queue)} música(s)")
                
                # Adicionar informações sobre músicas que falharam
                if failed_tracks:
                    embed.add_field(
                        name="⚠️ Algumas músicas não puderam ser adicionadas:",
                        value="\n".join(f"- {track[:50]}..." if len(track) > 50 else f"- {track}" for track in failed_tracks[:5]) + 
                              (f"\n... e mais {len(failed_tracks) - 5} falhas." if len(failed_tracks) > 5 else ""),
                        inline=False
                    )
                    
                await interaction.followup.send(embed=embed)
                
                # Iniciar reprodução se não estiver tocando ainda e não iniciamos antes
                if not vc.is_playing() and not started_playback:
                    await play_next_legacy(ctx)
                    
            except Exception as e:
                logging.error(f"Erro ao processar playlist '{filename}': {e}")
                await interaction.followup.send(embed=discord.Embed(
                    title="Erro",
                    description=f"Ocorreu um erro ao processar a playlist '{filename}':\n{str(e)[:500]}",
                    color=discord.Color.red()))
                
        # Criar e armazenar a tarefa para que possa ser cancelada
        playlist_processing_task = asyncio.create_task(process_playlist())

    # Comando para listar todas as playlists disponíveis
    @bot.command(name="playlists")
    async def list_playlists(ctx: commands.Context):
        """Lista todas as playlists disponíveis na pasta 'playlist'"""
        try:
            # Verificar se o diretório existe
            if not os.path.exists(PLAYLIST_DIR):
                await ctx.send(embed=discord.Embed(
                    title="Informação",
                    description=f"O diretório '{PLAYLIST_DIR}' não existe. Criando...",
                    color=discord.Color.blue()))
                os.makedirs(PLAYLIST_DIR)
                
            # Listar arquivos .txt no diretório
            playlist_files = [f for f in os.listdir(PLAYLIST_DIR) if f.endswith('.txt')]
            
            if not playlist_files:
                await ctx.send(embed=discord.Embed(
                    title="Playlists Disponíveis",
                    description=f"Nenhuma playlist encontrada na pasta '{PLAYLIST_DIR}'.\n\n"
                                f"💡 Para criar uma playlist, adicione um arquivo .txt com URLs ou nomes de músicas (um por linha) na pasta '{PLAYLIST_DIR}'.",
                    color=discord.Color.blue()))
                return
                
            # Criar uma lista formatada de arquivos
            file_list = "\n".join([f"📄 **{i+1}.** {f}" for i, f in enumerate(playlist_files)])
            
            # Enviar embed com a lista
            embed = discord.Embed(
                title="📋 Playlists Disponíveis",
                description=f"Playlists encontradas na pasta '{PLAYLIST_DIR}':\n\n{file_list}\n\n"
                            f"Para reproduzir uma playlist, use `/playlist nomedoarquivo`",
                color=discord.Color.from_rgb(114, 137, 218)
            )
            embed.set_footer(text=f"Total: {len(playlist_files)} playlist(s)")
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            logging.error(f"Erro ao listar playlists: {e}")
            await ctx.send(embed=discord.Embed(
                title="Erro",
                description=f"Ocorreu um erro ao listar as playlists: {str(e)}",
                color=discord.Color.red()))
                
    # Comando slash para listar playlists
    @bot.tree.command(name="playlists", description="Lista todas as playlists disponíveis")
    async def list_playlists_slash(interaction: discord.Interaction):
        """Comando slash para listar todas as playlists disponíveis"""
        await interaction.response.defer(ephemeral=False)
        
        try:
            # Verificar se o diretório existe
            if not os.path.exists(PLAYLIST_DIR):
                await interaction.followup.send(embed=discord.Embed(
                    title="Informação",
                    description=f"O diretório '{PLAYLIST_DIR}' não existe. Criando...",
                    color=discord.Color.blue()))
                os.makedirs(PLAYLIST_DIR)
                
            # Listar arquivos .txt no diretório
            playlist_files = [f for f in os.listdir(PLAYLIST_DIR) if f.endswith('.txt')]
            
            if not playlist_files:
                await interaction.followup.send(embed=discord.Embed(
                    title="Playlists Disponíveis",
                    description=f"Nenhuma playlist encontrada na pasta '{PLAYLIST_DIR}'.\n\n"
                                f"💡 Para criar uma playlist, adicione um arquivo .txt com URLs ou nomes de músicas (um por linha) na pasta '{PLAYLIST_DIR}'.",
                    color=discord.Color.blue()))
                return
                
            # Criar uma lista formatada de arquivos
            file_list = "\n".join([f"📄 **{i+1}.** {f}" for i, f in enumerate(playlist_files)])
            
            # Enviar embed com a lista
            embed = discord.Embed(
                title="📋 Playlists Disponíveis",
                description=f"Playlists encontradas na pasta '{PLAYLIST_DIR}':\n\n{file_list}\n\n"
                            f"Para reproduzir uma playlist, use `/playlist nomedoarquivo`",
                color=discord.Color.from_rgb(114, 137, 218)
            )
            embed.set_footer(text=f"Total: {len(playlist_files)} playlist(s)")
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logging.error(f"Erro ao listar playlists: {e}")
            await interaction.followup.send(embed=discord.Embed(
                title="Erro",
                description=f"Ocorreu um erro ao listar as playlists: {str(e)}",
                color=discord.Color.red()))

    # Comando para forçar a sincronização dos comandos slash
    @bot.command(name="sync")
    async def sync_commands(ctx: commands.Context):
        """Força a sincronização dos comandos slash com o Discord"""
        try:
            # Verificar se o autor tem permissões administrativas
            if not ctx.author.guild_permissions.administrator:
                await ctx.send(embed=discord.Embed(
                    title="Erro",
                    description="Você precisa ter permissões de administrador para usar este comando.",
                    color=discord.Color.red()))
                return
                
            # Sincronizar comandos slash
            await ctx.send(embed=discord.Embed(
                title="Sincronizando",
                description="Sincronizando comandos slash com o Discord...",
                color=discord.Color.blue()))
                
            synced = await bot.tree.sync()
            
            await ctx.send(embed=discord.Embed(
                title="Sucesso",
                description=f"{len(synced)} comandos slash foram sincronizados com o Discord.",
                color=discord.Color.green()))
                
        except Exception as e:
            logging.error(f"Erro ao sincronizar comandos: {e}")
            await ctx.send(embed=discord.Embed(
                title="Erro",
                description=f"Ocorreu um erro ao sincronizar os comandos: {str(e)}",
                color=discord.Color.red()))

    # Comando para pular a playlist atual (incluindo músicas em processamento)
    @bot.command(name="skipplaylist")
    async def skip_playlist(ctx: commands.Context):
        """Pula toda a playlist atual, incluindo músicas em processamento"""
        global playlist_cancel_flag, playlist_processing_task
        
        vc = ctx.voice_client
        if not vc:
            await ctx.send(embed=discord.Embed(
                title="Erro",
                description="Não estou conectado a um canal de voz.",
                color=discord.Color.red()))
            return
        
        # Verificar se há uma playlist sendo processada
        if not playlist_processing_task or playlist_processing_task.done():
            await ctx.send(embed=discord.Embed(
                title="Informação",
                description="Não há playlist sendo processada atualmente.",
                color=discord.Color.blue()))
            
            # Mesmo assim podemos limpar a fila e pular a música atual
            if vc.is_playing():
                vc.stop()
                song_queue.clear()
                await ctx.send(embed=discord.Embed(
                    title="Playlist Pulada",
                    description="Música atual pulada e fila limpa.",
                    color=discord.Color.green()))
            return
            
        # Sinalizar cancelamento da tarefa de processamento
        playlist_cancel_flag = True
        
        # Limpar a fila de músicas
        removed_songs = len(song_queue)
        song_queue.clear()
        
        # Parar a música atual
        was_playing = False
        if vc.is_playing():
            was_playing = True
            vc.stop()
        
        await ctx.send(embed=discord.Embed(
            title="Playlist Pulada",
            description="Cancelando processamento da playlist atual.\n"
                        f"Removidas {removed_songs} músicas da fila."
                        + ("\nMúsica atual interrompida." if was_playing else ""),
            color=discord.Color.green()))

    # Comando slash para pular a playlist atual
    @bot.tree.command(name="skipplaylist", description="Pula toda a playlist atual, incluindo músicas em processamento")
    async def skip_playlist_slash(interaction: discord.Interaction):
        """Comando slash para pular toda a playlist atual"""
        await interaction.response.defer(ephemeral=False)
        
        global playlist_cancel_flag, playlist_processing_task
        
        vc = interaction.guild.voice_client
        if not vc:
            await interaction.followup.send(embed=discord.Embed(
                title="Erro",
                description="Não estou conectado a um canal de voz.",
                color=discord.Color.red()))
            return
        
        # Verificar se há uma playlist sendo processada
        if not playlist_processing_task or playlist_processing_task.done():
            await interaction.followup.send(embed=discord.Embed(
                title="Informação",
                description="Não há playlist sendo processada atualmente.",
                color=discord.Color.blue()))
            
            # Mesmo assim podemos limpar a fila e pular a música atual
            if vc.is_playing():
                vc.stop()
                song_queue.clear()
                await interaction.followup.send(embed=discord.Embed(
                    title="Playlist Pulada",
                    description="Música atual pulada e fila limpa.",
                    color=discord.Color.green()))
            return
            
        # Sinalizar cancelamento da tarefa de processamento
        playlist_cancel_flag = True
        
        # Limpar a fila de músicas
        removed_songs = len(song_queue)
        song_queue.clear()
        
        # Parar a música atual
        was_playing = False
        if vc.is_playing():
            was_playing = True
            vc.stop()
        
        await interaction.followup.send(embed=discord.Embed(
            title="Playlist Pulada",
            description="Cancelando processamento da playlist atual.\n"
                        f"Removidas {removed_songs} músicas da fila."
                        + ("\nMúsica atual interrompida." if was_playing else ""),
            color=discord.Color.green()))

    # Comando para listar rádios disponíveis
    @bot.tree.command(name="radios", description="Lista todas as rádios disponíveis")
    async def radios_slash(interaction: discord.Interaction):
        embed = discord.Embed(
            title="📻 Rádios Disponíveis",
            description="Use /radio [nome] para tocar uma rádio",
            color=discord.Color.blue()
        )

        for key, radio in RADIOS.items():
            embed.add_field(
                name=f"{radio['name']} ({radio['location']})",
                value=f"Comando: `/radio {key}`\n{radio['description']}",
                inline=False
            )

        await interaction.response.send_message(embed=embed)

    # Comando para tocar uma rádio
    @bot.tree.command(name="radio", description="Toca uma rádio")
    @app_commands.describe(nome="Nome da rádio para tocar (use /radios para ver a lista)")
    async def radio_slash(interaction: discord.Interaction, nome: str):
        await interaction.response.defer(ephemeral=False)
        
        if nome not in RADIOS:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Erro",
                    description="Rádio não encontrada. Use /radios para ver a lista de rádios disponíveis.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            return

        # Verificar se o usuário está em um canal de voz
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
            radio = RADIOS[nome]
            
            # Verificar se já está conectado
            vc = interaction.guild.voice_client
            if vc:
                if vc.channel != interaction.user.voice.channel:
                    # Se estiver em um canal diferente, mover para o novo canal
                    await vc.move_to(interaction.user.voice.channel)
            else:
                # Se não estiver conectado, conectar ao canal
                vc = await interaction.user.voice.channel.connect()

            # Usar o caminho do FFmpeg se fornecido
            executable = FFMPEG_PATH if FFMPEG_PATH and os.path.exists(FFMPEG_PATH) else 'ffmpeg'

            # Configurar opções do FFmpeg para streaming
            ffmpeg_options = {
                # Opções para garantir reconexão e estabilidade do stream
                'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                # Opções para normalizar o áudio e evitar aceleração
                'options': f'-vn -af "aresample=48000,atempo=1.0,volume={current_volume}" -bufsize 10M'
            }
            # Parar reprodução atual se houver
            if vc.is_playing():
                vc.stop()

            # Limpar a fila de músicas
            global song_queue, current_song
            song_queue.clear()
            current_song = None

            # Iniciar reprodução da rádio
            vc.play(
                discord.FFmpegPCMAudio(radio['url'], executable=executable, **ffmpeg_options),
                after=lambda e: logging.error(f'Erro na reprodução da rádio: {e}') if e else None
            )

            # Criar embed informativo
            embed = discord.Embed(
                title="📻 Rádio Iniciada",
                description=f"**{radio['name']}**\n{radio['description']}",
                color=discord.Color.green()
            )
            embed.add_field(name="Localização", value=radio['location'])
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logging.error(f"Erro ao tocar rádio: {e}")
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Erro",
                    description=f"Erro ao tocar a rádio: {str(e)}",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )

    @bot.tree.command(name="addradio", description="Adiciona uma nova rádio personalizada")
    @app_commands.describe(
        nome="Nome da rádio",
        url="URL da stream da rádio",
        localizacao="Localização da rádio (opcional)",
        descricao="Descrição da rádio (opcional)"
    )
    async def add_radio_slash(
        interaction: discord.Interaction,
        nome: str,
        url: str,
        localizacao: str = "Desconhecido",
        descricao: str = "Rádio personalizada"
    ):
        await interaction.response.defer(ephemeral=False)
        
        # Verificar se a URL é válida
        if not url.startswith(('http://', 'https://')):
            await interaction.followup.send(embed=discord.Embed(
                title="Erro",
                description="URL inválida. A URL deve começar com http:// ou https://",
                color=discord.Color.red()
            ))
            return
            
        # Criar um identificador único para a rádio
        radio_id = nome.lower().replace(" ", "_")
        
        # Verificar se a rádio já existe
        if radio_id in RADIOS:
            await interaction.followup.send(embed=discord.Embed(
                title="Erro",
                description=f"Uma rádio com o nome '{nome}' já existe.",
                color=discord.Color.red()
            ))
            return
            
        # Adicionar a nova rádio
        RADIOS[radio_id] = {
            "name": nome,
            "location": localizacao,
            "url": url,
            "description": descricao
        }
        
        # Salvar as rádios em um arquivo JSON
        try:
            with open("radios.json", "w", encoding="utf-8") as f:
                json.dump(RADIOS, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logging.error(f"Erro ao salvar rádios: {e}")
            await interaction.followup.send(embed=discord.Embed(
                title="Erro",
                description="Ocorreu um erro ao salvar a rádio. Tente novamente mais tarde.",
                color=discord.Color.red()
            ))
            return
            
        await interaction.followup.send(embed=discord.Embed(
            title="Rádio Adicionada",
            description=f"Rádio '{nome}' adicionada com sucesso!\nUse `/radio {radio_id}` para tocar.",
            color=discord.Color.green()
        ))

    @bot.tree.command(name="removeradio", description="Remove uma rádio personalizada")
    @app_commands.describe(nome="Nome da rádio a ser removida")
    async def remove_radio_slash(interaction: discord.Interaction, nome: str):
        await interaction.response.defer(ephemeral=False)
        
        radio_id = nome.lower().replace(" ", "_")
        
        if radio_id not in RADIOS:
            await interaction.followup.send(embed=discord.Embed(
                title="Erro",
                description=f"Rádio '{nome}' não encontrada.",
                color=discord.Color.red()
            ))
            return
            
        # Remover a rádio
        del RADIOS[radio_id]
        
        # Salvar as alterações
        try:
            with open("radios.json", "w", encoding="utf-8") as f:
                json.dump(RADIOS, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logging.error(f"Erro ao salvar rádios: {e}")
            await interaction.followup.send(embed=discord.Embed(
                title="Erro",
                description="Ocorreu um erro ao remover a rádio. Tente novamente mais tarde.",
                color=discord.Color.red()
            ))
            return
            
        await interaction.followup.send(embed=discord.Embed(
            title="Rádio Removida",
            description=f"Rádio '{nome}' removida com sucesso!",
            color=discord.Color.green()
        ))

# Configurar o bot na inicialização
setup_bot()

# ========================== FUNÇÕES AUXILIARES ==========================

class VoiceConnectionError(Exception):
    """Exceção personalizada para erros de conexão de voz."""
    pass

async def ensure_voice(ctx: commands.Context | discord.Interaction) -> discord.VoiceClient | None:
    """Garante que o bot esteja no mesmo canal de voz que o autor."""
    # Adaptar para funcionar tanto com commands.Context quanto com Interaction
    author = ctx.user if isinstance(ctx, discord.Interaction) else ctx.author
    guild = ctx.guild
        
    if not author.voice:
        raise VoiceConnectionError("Você precisa estar em um canal de voz!")

    channel = author.voice.channel

    # Permissões
    perms = channel.permissions_for(guild.me)
    if not perms.connect or not perms.speak:
        raise VoiceConnectionError("Não tenho permissão para conectar ou falar neste canal.")

    vc = guild.voice_client
    if vc is None:
        vc = await channel.connect()
    elif vc.channel != channel:
        await vc.move_to(channel)
        
    return vc

async def extract_info(search: str) -> tuple[str, str, str, str, str]:
    """Extrai informações da música, incluindo título, URL, thumbnail, duração e canal"""
    # Verificar se a busca já está no cache
    if search in music_info_cache:
        return music_info_cache[search]
        
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'opus',
            'preferredquality': '320',
        }],
        'quiet': True,
        'noplaylist': True,
        'socket_timeout': 10,  # Timeout para evitar travamentos
        'retries': 3,          # Número de tentativas em caso de falha
        'skip_download': True, # Apenas extrair informações, não baixar
        'extract_flat': False, # Extrair informações completas
        'source_address': '0.0.0.0',  # Bind to ipv4 para melhor compatibilidade
    }
    loop = asyncio.get_event_loop()

    def run():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                logging.info(f"Buscando informações para: {search}")
                
                # Verificar se é uma URL direta ou uma busca
                if search.startswith(('http://', 'https://')):
                    info = ydl.extract_info(search, download=False)
                    entries = [info]  # URL direta, usar como entrada única
                else:
                    info = ydl.extract_info(f"ytsearch:{search}", download=False)
                    entries = info.get('entries', [])
                
                if not entries:
                    raise ValueError(f"Nenhum resultado encontrado para '{search}'.")
                    
                entry = entries[0]
                
                # Extrair informações extras
                title = entry.get('title', 'Título desconhecido')
                url = entry.get('url', entry.get('webpage_url', ''))
                
                if not url:
                    raise ValueError(f"URL não encontrada para '{search}'.")
                    
                thumbnail = entry.get('thumbnail', '')
                
                # Extrair duração formatada em minutos:segundos
                duration = entry.get('duration', 0)
                if duration:
                    minutes, seconds = divmod(duration, 60)
                    hours, minutes = divmod(minutes, 60)
                    if hours > 0:
                        duration_formatted = f"{int(hours)}:{int(minutes):02d}:{int(seconds):02d}"
                    else:
                        duration_formatted = f"{int(minutes)}:{int(seconds):02d}"
                else:
                    duration_formatted = "Desconhecida"
                
                # Nome do canal
                channel = entry.get('uploader', entry.get('channel', 'Desconhecido'))
                
                # Armazenar no cache
                result = (title, url, thumbnail, duration_formatted, channel)
                music_info_cache[search] = result
                
                logging.info(f"Informações extraídas com sucesso para: {title}")
                return result
            except Exception as e:
                logging.error(f"Erro ao extrair informação da música '{search}': {e}")
                raise ValueError(f"Erro ao buscar informações: {str(e)}")

    try:
        # Executar com timeout mais curto para evitar bloqueio
        return await asyncio.wait_for(loop.run_in_executor(None, run), timeout=15)
    except asyncio.TimeoutError:
        logging.error(f"Timeout ao buscar informações da música: {search}")
        raise ValueError(f"A busca por '{search}' demorou muito tempo. Tente novamente.")
    except Exception as e:
        logging.error(f"Erro não tratado ao buscar música '{search}': {e}")
        raise ValueError(f"Não foi possível buscar '{search}': {str(e)}")

async def play_next_legacy(ctx: commands.Context | discord.Interaction):
    """Tocar a próxima música na fila"""
    global current_song
    
    # Verificar recursos do sistema
    cpu, mem = await check_system_resources()
    if cpu and cpu > 90:
        logging.warning(f"Uso de CPU muito alto ({cpu}%). Pausando reprodução.")
        await asyncio.sleep(5)  # Esperar um pouco antes de tentar novamente
    
    # Obter a guild
    if isinstance(ctx, discord.Interaction):
        guild = ctx.guild
    else:
        guild = ctx.guild
    
    # Verificar se há músicas na fila
    if not song_queue:
        current_song = None
        return
        
    # Verificar se está conectado a um canal de voz
    vc = guild.voice_client
    if not vc:
        current_song = None
        return
        
    # Obter a próxima música da fila
    if is_shuffling:
        import random
        idx = random.randint(0, len(song_queue) - 1)
        current_song = song_queue.pop(idx)
    else:
        current_song = song_queue.pop(0)
    
    # Função para truncar texto longo
    def truncate_text(text, max_length=50):
        return text[:max_length] + "..." if len(text) > max_length else text
    
    # Extrair todas as informações da música
    try:
        if len(current_song) >= 6:  # Formato novo com duração e canal
            title, url, thumbnail, author, duration, channel = current_song
        else:  # Compatibilidade com formato antigo
            title, url, thumbnail, author = current_song
            duration = "Desconhecida"
            channel = "Desconhecido"
        
        # Truncar textos longos
        title_display = truncate_text(title, 80)
        channel_display = truncate_text(channel, 30)
    except Exception as e:
        logging.error(f"Erro ao extrair informações da música: {e}")
        if song_queue:  # Tentar próxima música se possível
            try:
                asyncio.create_task(play_next(ctx))
            except:
                pass
        return
    
    # Usar o caminho do FFmpeg se fornecido, senão usar o padrão do sistema
    executable = FFMPEG_PATH if FFMPEG_PATH and os.path.exists(FFMPEG_PATH) else 'ffmpeg'

    # Configurar opções do FFmpeg
    ffmpeg_options = {
        # Opções para garantir reconexão e estabilidade do stream
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        # Opções para normalizar o áudio, evitar aceleração e aplicar volume
        'options': f'-vn -af "aresample=48000,atempo=1.0,volume={current_volume}" -bufsize 10M'
    }

    # Criar um embed melhorado para "Tocando Agora"
    embed = discord.Embed(
        title="🎵 Tocando Agora",
        description=f"**{title_display}**",
        color=discord.Color.from_rgb(57, 255, 20)  # Verde vibrante
    )
    
    # Adicionar campos com informações extras
    embed.add_field(name="Canal", value=channel_display, inline=True)
    embed.add_field(name="Duração", value=duration, inline=True)
    
    try:
        # Garantir que author tem mention
        author_mention = author.mention if hasattr(author, 'mention') else "Desconhecido"
        embed.add_field(name="Adicionado por", value=author_mention, inline=False)
    except Exception as e:
        logging.error(f"Erro ao adicionar autor ao embed: {e}")
        embed.add_field(name="Adicionado por", value="Desconhecido", inline=False)
    
    # Configurar o rodapé
    if len(song_queue) > 0:
        embed.set_footer(text=f"Próximas: {len(song_queue)} música(s) na fila")
    
    # Adicionar imagem de capa, se disponível
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
        # Adicionar uma imagem grande na parte inferior para um visual mais rico
        if thumbnail.startswith("https://i.ytimg.com/"):
            # Para miniaturas do YouTube, podemos tentar obter uma versão maior
            embed.set_image(url=thumbnail.replace("hqdefault", "maxresdefault"))
        else:
            embed.set_image(url=thumbnail)
    
    # Configurar reprodução
    try:
        source = discord.FFmpegPCMAudio(url, executable=executable, **ffmpeg_options)
        vc.play(source, after=lambda err: after_play(err))
    except Exception as e:
        logging.error(f"Erro ao reproduzir música: {e}")
        current_song = None
        if song_queue:  # Tentar próxima música se possível
            try:
                asyncio.create_task(play_next(ctx))
            except:
                pass
        return
    
    # Função para o callback após terminar a música
    def after_play(err):
        if err:
            logging.error(f"Erro na reprodução: {err}")
        
        try:
            # Criar um contexto para o loop de evento atual
            class DummyContext:
                def __init__(self, guild):
                    self.guild = guild
                    
                    async def dummy_send(embed=None):
                        pass
                        
                    self.send = dummy_send
            
            # Aguardar um momento para garantir que a música atual termine
            asyncio.run_coroutine_threadsafe(
                asyncio.sleep(0.5),
                bot.loop
            )
            
            # Verificar se deve repetir a música atual
            if is_looping and current_song:
                song_queue.insert(0, current_song)
            
            # Reproduzir a próxima música
            asyncio.run_coroutine_threadsafe(
                play_next(DummyContext(guild)),
                bot.loop
            )
        except Exception as err2:
            logging.error(f"Erro no callback after_play: {err2}")
    
    # Enviar embed para informar música atual
    try:
        if isinstance(ctx, discord.Interaction):
            if not ctx.response.is_done():
                try:
                    await ctx.response.send_message(embed=embed)
                except:
                    pass
            else:
                try:
                    await ctx.followup.send(embed=embed)
                except:
                    pass
        else:
            try:
                await ctx.send(embed=embed)
            except:
                pass
    except Exception as e:
        logging.error(f"Erro ao enviar mensagem de música atual: {e}")

# Função para desconectar de todos os canais de voz
def disconnect_from_all_voice_channels():
    """Desconecta o bot de todos os canais de voz em todas as guildas."""
    # Esta função será usada pela GUI para forçar a desconexão
    pass

# ========================== API WEB (FastAPI) ==========================

class MusicRequest(BaseModel):
    search: str

class PlaylistRequest(BaseModel):
    filename: str

class VolumeRequest(BaseModel):
    level: float

@app.get("/api/status")
async def get_status():
    """Retorna o status atual do bot."""
    # Extrair informações da música atual de forma segura
    current_song_info = None
    if current_song:
        try:
            title, _, thumbnail, user, duration, channel = current_song
            current_song_info = {
                "title": title,
                "thumbnail": thumbnail,
                "user": user.display_name if hasattr(user, 'display_name') else "Desconhecido",
                "duration": duration,
                "channel": channel
            }
        except (ValueError, TypeError):
            current_song_info = {"title": "Informações da música indisponíveis"}

    # Extrair informações da fila de forma segura
    queue_info = []
    for song in song_queue[:10]: # Limitar a 10 para não sobrecarregar
        try:
            title, _, _, user, duration, _ = song
            queue_info.append({
                "title": title,
                "user": user.display_name if hasattr(user, 'display_name') else "Desconhecido",
                "duration": duration
            })
        except (ValueError, TypeError):
            queue_info.append({"title": "Informações da música indisponíveis"})

    return {
        "bot_user": str(bot.user),
        "is_ready": bot.is_ready(),
        "guilds": len(bot.guilds),
        "current_song": current_song_info,
        "queue": queue_info,
        "volume": current_volume,
        "is_looping": is_looping,
        "is_shuffling": is_shuffling,
        "is_paused": is_paused,
        "voice_connections": len(bot.voice_clients)
    }

@app.get("/queue")
async def get_queue():
    """Retorna a fila de músicas atual."""
    return {"queue": [song[0] for song in song_queue]}

@app.post("/api/play")
async def api_play(request: MusicRequest):
    """Adiciona uma música à fila e inicia a reprodução."""
    if not bot.voice_clients:
        raise HTTPException(status_code=400, detail="Bot não está em um canal de voz.")
    
    vc = bot.voice_clients[0]
    player = get_player(vc.guild.id)

    try:
        # User placeholder for API
        api_user = bot.user 
        song = await player.add_to_queue(request.search, api_user)

        if not vc.is_playing() and not player.is_paused:
            await player.play_next()

        return {"status": "success", "message": f"'{song['title']}' adicionado à fila."}
    except Exception as e:
        logging.error(f"API /play error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/skip")
async def api_skip():
    """Pula a música atual."""
    if not bot.voice_clients:
        raise HTTPException(status_code=400, detail="Bot não está em um canal de voz.")
    
    vc = bot.voice_clients[0]
    player = get_player(vc.guild.id)
    player.skip()
    return {"status": "success", "message": "Música pulada."}

@app.post("/api/pause")
async def api_pause():
    """Pausa a música atual."""
    if not bot.voice_clients:
        raise HTTPException(status_code=400, detail="Bot não está em um canal de voz.")
    
    vc = bot.voice_clients[0]
    player = get_player(vc.guild.id)
    player.pause()
    return {"status": "success", "message": "Música pausada."}

@app.post("/api/resume")
async def api_resume():
    """Retoma a música pausada."""
    if not bot.voice_clients:
        raise HTTPException(status_code=400, detail="Bot não está em um canal de voz.")
    
    vc = bot.voice_clients[0]
    player = get_player(vc.guild.id)
    player.resume()
    return {"status": "success", "message": "Música retomada."}

@app.post("/api/volume")
async def api_volume(request: VolumeRequest):
    """Ajusta o volume do bot."""
    if request.level < 0 or request.level > 1:
        raise HTTPException(status_code=400, detail="O volume deve estar entre 0.0 e 1.0")
        
    if not bot.voice_clients:
        # Armazenar volume padrão para futuras conexões
        global current_volume
        current_volume = request.level
        logging.info(f"Volume padrão ajustado para {request.level} (sem conexões ativas)")
        return {"status": "success", "message": f"Volume padrão ajustado para {int(request.level*100)}%"}
          
    # Atualizar volume para todos os players ativos
    count = 0
    for vc in bot.voice_clients:
        player = get_player(vc.guild.id)
        player.set_volume(request.level)
        count += 1
        
    logging.info(f"Volume ajustado para {request.level} via API para {count} players")
    return {"status": "success", "message": f"Volume ajustado para {int(request.level*100)}%"}


@app.post("/api/set_token")
async def set_token(request: dict = Body(...)):
    """Define o token do Discord (USO RESTRITO E INSEGURO)."""
    global bot
    token = request.get("token")
    if not token or len(token) < 50: # Validação básica do token
        raise HTTPException(status_code=400, detail="Token não fornecido.")
    
    try:
        # 1. Salvar o token no arquivo .env para persistência
        save_token_to_json(token)
        
        # 2. Atualizar a variável de ambiente no processo atual
        os.environ['DISCORD_TOKEN'] = token
        logging.info("Token do Discord foi salvo/atualizado via API.")

        if bot.is_ready():
            logging.info("Bot já está online. Tentando reiniciar com o novo token...")
            asyncio.create_task(bot.close())
            bot = commands.Bot(command_prefix='/', intents=intents)
            setup_bot() # Reconfigura todos os comandos e eventos no novo objeto bot
            asyncio.create_task(bot.start(token))
            return {"status": "success", "message": "Token atualizado. Bot reiniciando..."}
        else:
            # Se o bot não está online, iniciamos ele pela primeira vez.
            logging.info("Bot está offline. Iniciando com o novo token...")
            asyncio.create_task(bot.start(token))
            return {"status": "success", "message": "Token salvo. Bot iniciando..."}

    except Exception as e:
        logging.error(f"Erro ao salvar token via API: {e}")
        raise HTTPException(status_code=500, detail="Falha ao salvar o token.")

@app.post("/api/startup")
async def startup_bot(request: dict = Body(...)):
    """Inicia o bot com um novo token fornecido."""
    global bot
    token = request.get("token")
    
    if not token or len(token) < 50:
        raise HTTPException(status_code=400, detail="Token não fornecido ou inválido.")
    
    if bot.is_ready():
        raise HTTPException(status_code=400, detail="Bot já está online.")
    
    try:
        save_token_to_json(token)
        logging.info("Iniciando bot com novo token via API...")
        asyncio.create_task(bot.start(token))
        return {"status": "success", "message": "Bot iniciando com novo token..."}
    except Exception as e:
        logging.error(f"Erro ao iniciar bot: {e}")
        raise HTTPException(status_code=500, detail="Falha ao iniciar o bot.")

@app.post("/api/restart")
async def restart_bot():
    """Reinicia o bot com o token atual."""
    global bot
    
    if not bot.is_ready():
        raise HTTPException(status_code=400, detail="Bot não está online.")
    
    # Carregar token atual
    token = load_token_from_json()
    if not token:
        token = os.getenv("DISCORD_TOKEN")
    
    if not token:
        raise HTTPException(status_code=400, detail="Nenhum token configurado para reiniciar.")
    
    try:
        logging.info("Reiniciando bot via API...")
        # Desconectar do Discord
        await bot.close()
        
        # Aguardar um pouco para limpeza
        await asyncio.sleep(1)
        
        # Recriar o bot e iniciar novamente
        bot = commands.Bot(command_prefix='/', intents=intents)
        setup_bot()
        asyncio.create_task(bot.start(token))
        
        return {"status": "success", "message": "Bot reiniciando..."}
    except Exception as e:
        logging.error(f"Erro ao reiniciar bot: {e}")
        raise HTTPException(status_code=500, detail="Falha ao reiniciar o bot.")

@app.post("/api/shutdown")
async def shutdown_bot():
    """Desliga o bot."""
    global bot
    
    if not bot.is_ready():
        raise HTTPException(status_code=400, detail="Bot não está online.")
    
    try:
        logging.info("Desligando bot via API...")
        await bot.close()
        return {"status": "success", "message": "Bot desligado. A API continua rodando."}
    except Exception as e:
        logging.error(f"Erro ao desligar bot: {e}")
        raise HTTPException(status_code=500, detail="Falha ao desligar o bot.")

# ========================== INICIALIZAÇÃO ==========================

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Criar diretório para arquivos estáticos se não existir
if not os.path.exists("static"):
    os.makedirs("static")

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=FileResponse)
async def read_index():
    return "static/index.html"

async def run_bot_and_api():
    """Inicia o bot do Discord e o servidor da API."""
    # Prioriza o token do token.json, depois do .env
    token = load_token_from_json()
    if not token:
        token = os.getenv("DISCORD_TOKEN")
    
    # Se ainda não tem token, perguntar no terminal
    if not token or not token.strip():
        loop = asyncio.get_event_loop()
        token = await loop.run_in_executor(None, prompt_token_terminal)

    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="warning")
    server = uvicorn.Server(config)

    # Inicia o servidor uvicorn em uma tarefa de fundo
    api_task = asyncio.create_task(server.serve())

    # Verifica se o token é válido antes de tentar iniciar o bot
    if token and token.strip() and token not in ["SEU_TOKEN_AQUI", "SEU_TOKEN_DO_DISCORD_AQUI", "your_discord_token_here"]:
        async def run_bot_safe():
            """Tenta iniciar o bot, mas não deixa a API morrer se falhar"""
            try:
                logging.info("Token do Discord encontrado. Iniciando o bot...")
                await bot.start(token)
            except discord.errors.LoginFailure as e:
                logging.error(f"❌ Falha de autenticação do Discord: {e}")
                logging.warning("Token inválido. A API web continua rodando, mas o bot está offline.")
                logging.warning("Acesse a interface web para configurar um token válido.")
            except discord.errors.PrivilegedIntentsRequired as e:
                logging.error(f"❌ Intents não habilitados no Developer Portal: {e}")
                logging.warning("📌 Acesse https://discord.com/developers/applications")
                logging.warning("📌 Habilite: Message Content Intent e Presence Intent")
                logging.warning("⏳ Aguardando token válido via interface web ou terminal...")
            except Exception as e:
                logging.error(f"❌ Erro ao iniciar o bot: {e}")
                logging.warning("⏳ A API web continua rodando. Você pode tentar novamente via interface web.")
        
        # Iniciar o bot em background, NÃO bloquear a API
        bot_task = asyncio.create_task(run_bot_safe())
        # Apenas aguardarmos a API rodar - o bot roda independentemente
        await api_task
    else:
        logging.warning("⏳ Nenhum token válido do Discord encontrado. A API web está rodando, mas o bot está offline.")
        logging.warning("✨ Acesse a interface web (http://localhost:8000) para configurar o token.")
        await api_task

if __name__ == "__main__":
    try:
        asyncio.run(run_bot_and_api())
    except KeyboardInterrupt:
        logging.info("Bot finalizado pelo usuário.")
