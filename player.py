import asyncio
import discord
import logging
from collections import deque
import yt_dlp
import os

# Configuração do yt-dlp
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'opus',
        'preferredquality': '320',
    }],
    'quiet': True,
    'noplaylist': False,  # Permitir playlists
    'playlistend': 100,  # Limitar a 100 músicas por playlist
    'socket_timeout': 10,
    'retries': 3,
    'skip_download': True,
    'extract_flat': 'in_playlist',  # Extração rápida para playlists
    'source_address': '0.0.0.0',
    'cachedir': '/app/.cache',  # Diretório de cache explícito
    'geo_bypass': True,  # Tenta contornar restrições geográficas
    'geo_bypass_country': 'US',  # País para bypass (pode ser ajustado)
}

class MusicPlayer:
    def __init__(self, guild_id, bot):
        self.guild_id = guild_id
        self.bot = bot
        self.queue = deque()
        self.current_song = None
        self.volume = 0.5
        self.is_paused = False
        self.is_looping = False
        self.is_shuffling = False
        self.loop = asyncio.get_event_loop()
        
        # Soundboard state
        self.sfx_playing = False
        self.paused_for_sfx = False

    @property
    def guild(self):
        return self.bot.get_guild(self.guild_id)

    @property
    def voice_client(self):
        return self.guild.voice_client if self.guild else None

    async def add_to_queue(self, search, user):
        """Busca e adiciona música à fila (apenas primeira se for playlist)."""
        try:
            info_list = await self.extract_info(search)
            # info_list = [(title, url, thumbnail, duration, channel), ...]
            
            if not info_list:
                raise ValueError("Nenhuma música encontrada.")
            
            # Pegar apenas a primeira música
            info = info_list[0]
            song = {
                'title': info[0],
                'url': info[1],
                'thumbnail': info[2],
                'duration': info[3],
                'channel': info[4],
                'user': user
            }
            self.queue.append(song)
            return song
        except Exception as e:
            logging.error(f"Erro ao adicionar música: {e}")
            raise e

    async def add_playlist_to_queue(self, search, user):
        """Busca e adiciona todas as músicas de uma playlist à fila.
        
        Returns:
            tuple: (número de músicas adicionadas, lista de músicas)
        """
        try:
            info_list = await self.extract_info(search)
            
            if not info_list:
                raise ValueError("Nenhuma música encontrada.")
            
            songs_added = []
            for info in info_list:
                song = {
                    'title': info[0],
                    'url': info[1],
                    'thumbnail': info[2],
                    'duration': info[3],
                    'channel': info[4],
                    'user': user
                }
                self.queue.append(song)
                songs_added.append(song)
            
            return len(songs_added), songs_added
        except Exception as e:
            logging.error(f"Erro ao adicionar playlist: {e}")
            raise e

    async def extract_info(self, search):
        """Extrai informações do YouTube/SoundCloud.
        
        Retorna lista de tuplas: [(title, url, thumbnail, duration, channel), ...]
        """
        def run():
            with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                info = None
                entries = []
                
                if search.startswith(('http://', 'https://')):
                    # URL direta - pode ser música única ou playlist
                    info = ydl.extract_info(search, download=False)
                    
                    # Verificar se é playlist
                    if 'entries' in info:
                        entries = info['entries']
                    else:
                        entries = [info]
                        
                elif search.startswith(('scsearch:', 'ytsearch:')):
                    # Pesquisa explícita
                    info = ydl.extract_info(search, download=False)
                    entries = info.get('entries', [])
                else:
                    # Padrão: Pesquisa do YouTube (apenas primeiro resultado)
                    info = ydl.extract_info(f"ytsearch:{search}", download=False)
                    entries = info.get('entries', [])
                
                if not entries:
                    raise ValueError("Nenhum resultado encontrado.")
                
                # Processar todas as entradas
                results = []
                for entry in entries:
                    if not entry:  # Pular entradas vazias
                        continue
                        
                    title = entry.get('title', 'Desconhecido')
                    url = entry.get('url', entry.get('webpage_url', ''))
                    thumbnail = entry.get('thumbnail', '')
                    
                    duration = entry.get('duration', 0)
                    if duration:
                        minutes, seconds = divmod(duration, 60)
                        hours, minutes = divmod(minutes, 60)
                        duration_formatted = f"{int(hours)}:{int(minutes):02d}:{int(seconds):02d}" if hours > 0 else f"{int(minutes)}:{int(seconds):02d}"
                    else:
                        duration_formatted = "Desconhecida"
                    
                    channel = entry.get('uploader', entry.get('channel', 'Desconhecido'))
                    results.append((title, url, thumbnail, duration_formatted, channel))
                
                return results

        return await self.loop.run_in_executor(None, run)

    async def play_next(self):
        """Toca a próxima música da fila."""
        if not self.voice_client:
            return

        if self.is_shuffling and len(self.queue) > 0:
            # Lógica de embaralhamento: escolher aleatório mas manter fila intacta? Ou embaralhar fila?
            # Implementação original removia índice aleatório.
            pass # Simplificação por enquanto: remoção regular

        if not self.queue:
            self.current_song = None
            return

        # Remoção simples por enquanto, lógica de embaralhamento complexa pode ser adicionada depois
        self.current_song = self.queue.popleft()

        source_url = self.current_song['url']
        
        ffmpeg_options = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': f'-vn -af "aresample=48000,atempo=1.0,volume={self.volume}" -bufsize 10M'
        }

        def after_play(err):
            if err:
                logging.error(f"Erro no player: {err}")
            
            # Lógica de Loop
            if self.is_looping and self.current_song:
                self.queue.appendleft(self.current_song)
            
            # Agendar próxima música
            future = asyncio.run_coroutine_threadsafe(self.play_next(), self.bot.loop)
            try:
                future.result()
            except:
                pass

        try:
            # Lógica de verificação do caminho do executável (env var ou padrão)
            executable = 'ffmpeg' 
            self.voice_client.play(
                discord.FFmpegPCMAudio(source_url, executable=executable, **ffmpeg_options),
                after=after_play
            )
            self.is_paused = False
        except Exception as e:
            logging.error(f"Erro ao iniciar playback: {e}")
            await self.play_next() # Tentar próxima

    async def play_soundboard(self, sfx_path: str, volume: float = 1.0):
        """Tocar efeito sonoro do soundboard
        
        Args:
            sfx_path: Caminho para o arquivo de áudio
            volume: Volume do efeito (0.0 a 2.0)
        """
        if self.sfx_playing:
            logging.warning("SFX já está tocando, ignorando novo pedido")
            return
        
        if not self.voice_client:
            logging.error("Voice client não disponível para tocar SFX")
            return
        
        self.sfx_playing = True
        
        # Salvar estado da música
        was_playing = self.voice_client.is_playing()
        
        if was_playing:
            self.paused_for_sfx = True
            self.voice_client.pause()
            logging.info("Música pausada para tocar SFX")
        
        # Tocar SFX
        ffmpeg_options = {
            'options': f'-vn -af "volume={volume}"'
        }
        
        def after_sfx(error):
            if error:
                logging.error(f"Erro ao tocar SFX: {error}")
            
            self.sfx_playing = False
            logging.info("SFX finalizado, verificando retomada de música")
            
            # Retomar música se estava tocando
            if self.paused_for_sfx:
                # Criar coroutine para retomar música
                async def resume_music():
                    try:
                        if self.voice_client and self.voice_client.is_paused():
                            self.voice_client.resume()
                            logging.info("Música retomada após SFX")
                        else:
                            logging.warning(f"Voice client não está pausado. Estado: paused={self.voice_client.is_paused() if self.voice_client else 'N/A'}")
                    except Exception as e:
                        logging.error(f"Erro ao retomar música: {e}")
                    finally:
                        self.paused_for_sfx = False
                
                # Executar no loop principal
                future = asyncio.run_coroutine_threadsafe(resume_music(), self.bot.loop)
                try:
                    future.result(timeout=2)
                except Exception as e:
                    logging.error(f"Erro ao agendar retomada de música: {e}")
                    self.paused_for_sfx = False
        
        try:
            executable = 'ffmpeg'
            source = discord.FFmpegPCMAudio(sfx_path, executable=executable, **ffmpeg_options)
            self.voice_client.play(source, after=after_sfx)
            logging.info(f"SFX iniciado: {sfx_path} (volume: {volume})")
        except Exception as e:
            logging.error(f"Erro ao iniciar SFX: {e}")
            self.sfx_playing = False
            if self.paused_for_sfx:
                self.voice_client.resume()
                self.paused_for_sfx = False

    def stop(self):
        self.queue.clear()
        self.current_song = None
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()

    def skip(self):
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop() # callback 'after' acionará play_next

    def pause(self):
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.pause()
            self.is_paused = True

    def resume(self):
        if self.voice_client and self.voice_client.is_paused():
            self.voice_client.resume()
            self.is_paused = False

    def set_volume(self, volume):
        """Ajusta o volume do player.
        
        NOTA: O volume é aplicado apenas nas próximas músicas.
        FFmpegPCMAudio não permite ajuste de volume em tempo real após criação.
        """
        self.volume = max(0.0, min(1.0, volume))
        # O volume será aplicado na próxima música via opções do FFmpeg
        # Não é possível alterar o volume da música atual em reprodução
