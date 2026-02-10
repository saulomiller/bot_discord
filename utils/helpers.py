import discord
from discord.ext import commands
import logging
import os
import json
import psutil
import time
import asyncio
import yt_dlp
from config import RADIOS_FILE, DATA_DIR, SOUNDBOARD_METADATA_FILE, SOUNDBOARD_DIR, save_token_to_json

# --- Caches ---
music_info_cache = {}
playlist_cache = {}

# --- Exceções ---
class VoiceConnectionError(Exception):
    """Exceção personalizada para erros de conexão de voz."""
    pass

# --- Funções de Voz ---
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

# --- Funções de Sistema ---
# Variáveis globais para monitoramento de recursos
last_resource_check = 0
resource_check_interval = 60
cpu_usage = 0
memory_usage = 0

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

# --- Funções de Rádio ---
def load_radios():
    """Carregar rádios do arquivo JSON"""
    # Tenta carregar do diretório de dados
    if os.path.exists(RADIOS_FILE):
        try:
            with open(RADIOS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Erro ao carregar rádios de {RADIOS_FILE}: {e}")
            
    # Fallback: Tenta carregar da raiz se não existir em data/ (para compatibilidade ou primeira execução)
    if os.path.exists("radios.json"):
        try:
            logging.info("Carregando radios.json da raiz e copiando para data/radios.json")
            with open("radios.json", "r", encoding="utf-8") as f:
                data = json.load(f)
            # Salvar no novo local para o futuro
            try:
                if not os.path.exists(DATA_DIR):
                    os.makedirs(DATA_DIR)
                with open(RADIOS_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4)
            except Exception as e:
                logging.warning(f"Não foi possível migrar radios.json para data/: {e}")
            return data
        except Exception as e:
            logging.error(f"Erro ao carregar rádios da raiz: {e}")
            
    return {}

# --- Funções de Soundboard ---
def load_soundboard_metadata():
    """Carregar metadata do soundboard (favoritos, volume, etc)"""
    if os.path.exists(SOUNDBOARD_METADATA_FILE):
        try:
            with open(SOUNDBOARD_METADATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Erro ao carregar metadata do soundboard: {e}")
    return {"soundboard": []}

def save_soundboard_metadata(metadata):
    """Salvar metadata do soundboard"""
    try:
        if not os.path.exists(SOUNDBOARD_DIR):
            os.makedirs(SOUNDBOARD_DIR)
        with open(SOUNDBOARD_METADATA_FILE, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Erro ao salvar metadata do soundboard: {e}")

def get_sfx_metadata(sfx_id):
    """Obter metadata de um efeito sonoro específico"""
    metadata = load_soundboard_metadata()
    for sfx in metadata.get("soundboard", []):
        if sfx.get("id") == sfx_id:
            return sfx
    return {"id": sfx_id, "favorite": False, "volume": 1.0}

def update_sfx_metadata(sfx_id, updates):
    """Atualizar metadata de um efeito sonoro"""
    metadata = load_soundboard_metadata()
    soundboard = metadata.get("soundboard", [])
    
    # Procurar SFX existente
    for sfx in soundboard:
        if sfx.get("id") == sfx_id:
            sfx.update(updates)
            save_soundboard_metadata(metadata)
            return sfx
    
    # Se não existir, criar novo
    new_sfx = {"id": sfx_id, "favorite": False, "volume": 1.0}
    new_sfx.update(updates)
    soundboard.append(new_sfx)
    metadata["soundboard"] = soundboard
    save_soundboard_metadata(metadata)
    return new_sfx

# --- Extração de Info (YouTube/SoundCloud) ---
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
                # IMPORTANTE: Acessar a variável global do módulo
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
