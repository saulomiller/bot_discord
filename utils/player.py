import asyncio
import contextlib
import discord
import logging
from collections import deque, OrderedDict
import yt_dlp
import time
import subprocess
from utils.embeds import EmbedBuilder
from utils.image import create_now_playing_card

# Configuração do yt-dlp
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'quiet': True,
    'noplaylist': False,  # Permitir playlists
    'playlistend': 100,  # Limitar a 100 músicas por playlist
    'socket_timeout': 15,
    'retries': 5,
    'skip_download': True,
    'source_address': '0.0.0.0',
    'cachedir': '/app/.cache',
    'geo_bypass': True,
    'geo_bypass_country': 'US',
    'ignoreerrors': True,   # Não abortar em entradas inválidas de playlist
    'extract_flat': False,  # Resolver URLs completas por padrão
    # mweb: cliente mobile web, não requer PO Token nem login
    # web: fallback estável para a maioria dos vídeos
    # tv_embedded: fallback adicional para vídeos com restrições
    'extractor_args': {
        'youtube': {
            'player_client': ['mweb', 'web', 'tv_embedded'],
        }
    },
}

MAX_PLAYLIST_SIZE = 100  # Limite rígido (Check 4 - User Feedback)

class StreamCache:
    """Cache simples para URLs de stream com TTL, limite de tamanho e limpeza ativa.
    
    Usa time.monotonic() para robustez contra mudanças de clock do sistema."""
    def __init__(self, ttl=600, max_size=100):
        self.cache = OrderedDict()
        self.ttl = ttl # 10 minutos
        self.max_size = max_size
        self.insert_count = 0

    def get(self, key):
        if key in self.cache:
            data = self.cache[key]
            # Usar monotonic para TTL (robusto ao NTP)
            if time.monotonic() - data['time'] < self.ttl:
                # Move para fim (LRU)
                self.cache.move_to_end(key)
                return data['url']
            else:
                del self.cache[key]
        return None

    def set(self, key, url):
        self.insert_count += 1
        
        # Limpeza ativa a cada 50 inserções (Higiene)
        if self.insert_count % 50 == 0:
            self._sweep()

        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = {'url': url, 'time': time.monotonic()}
        
        # Limpar excesso (LRU)
        if len(self.cache) > self.max_size:
            self.cache.popitem(last=False)

    def _sweep(self):
        """Remove itens expirados do cache (usando monotonic)."""
        now = time.monotonic()
        keys_to_remove = [
            k for k, v in self.cache.items()
            if now - v['time'] > self.ttl
        ]
        
        for k in keys_to_remove:
            del self.cache[k]
        
        if keys_to_remove:
            logging.info(f"🧹 Cache Sweep: {len(keys_to_remove)} itens expirados removidos.")

class SafeFFmpegPCMAudio(discord.FFmpegPCMAudio):
    """FFmpegPCMAudio com cleanup robusto para evitar processos zumbis."""
    def cleanup(self):
        proc = self._process
        if proc:
            try:
                logging.info(f"Killing FFmpeg process {proc.pid}...")
                proc.terminate()
                try:
                    proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    logging.warning(f"FFmpeg {proc.pid} not terminating, forcing kill.")
                    proc.kill()
            except Exception as e:
                logging.error(f"Error killing FFmpeg process: {e}")
        
        # Chama o cleanup original para fechar pipes
        super().cleanup()

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
        self.loop = asyncio.get_running_loop()
        
        # Cache de Streams
        self.stream_cache = StreamCache()
        
        # Reutilizar instância do YoutubeDL (Otimização)
        self.ydl = yt_dlp.YoutubeDL(YDL_OPTIONS)

        # Progress tracking
        self.started_at = None
        self.paused_at = None 
        self.total_paused = 0
        
        # Soundboard state
        self.sfx_playing = False
        self.stopped_for_sfx = False
        self.consecutive_errors = 0
        
        # Concurrency safety: Lock para evitar múltiplos play_next simultâneos
        self._play_lock = asyncio.Lock()

        # Dashboard (Card Vivo)
        self.dashboard_message = None
        self.dashboard_context = None # ctx ou interaction
        self.dashboard_task = None
        self.last_img_url = None
        self._last_second = -1  # Rastreador para smart updates (evita recria desnecessária)

    @property
    def guild(self):
        return self.bot.get_guild(self.guild_id)

    @property
    def voice_client(self):
        return self.guild.voice_client if self.guild else None

    @property
    def is_playing(self) -> bool:
        """Retorna True se estiver tocando áudio."""
        return bool(self.voice_client and self.voice_client.is_playing())

    def _format_duration(self, duration_seconds: int) -> str:
        """Formata duração em segundos para string HH:MM:SS ou MM:SS."""
        if not duration_seconds:
            return "Desconhecida"
        
        minutes, seconds = divmod(int(duration_seconds), 60)
        hours, minutes = divmod(minutes, 60)
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes}:{seconds:02d}"
    
    def get_progress(self) -> dict:
        """Calcula o progresso atual da música com precisão monotonic."""
        if not self.current_song or not self.started_at:
            return {"current": 0, "duration": 0, "percent": 0}
        
        # Calcular tempo atual
        now = self.paused_at or time.monotonic()
        elapsed = max(0, now - self.started_at - self.total_paused)
        
        duration = self.current_song.get('duration_seconds', 0)
        
        # Garantir limites
        elapsed = min(elapsed, duration) if duration > 0 else elapsed
        percent = (elapsed / duration * 100) if duration > 0 else 0
        
        return {
            "current": int(elapsed),
            "duration": int(duration),
            "percent": round(min(100, percent), 1)
        }

    # --- Dashboard Logic ---

    async def start_dashboard_task(self):
        """Inicia a tarefa de atualização do dashboard."""
        if self.dashboard_task and not self.dashboard_task.done():
            return
        
        self.dashboard_task = self.bot.loop.create_task(self.update_dashboard_loop())

    async def stop_dashboard_task(self):
        """Para a tarefa de atualização (com cancelamento seguro)."""
        if self.dashboard_task and not self.dashboard_task.done():
            self.dashboard_task.cancel()
            # Suprimir CancelledError de forma segura
            with contextlib.suppress(asyncio.CancelledError):
                await self.dashboard_task
            self.dashboard_task = None

    async def update_dashboard_loop(self):
        """Loop que atualiza a BARRA DE PROGRESSO no embed (texto) a cada segundo (smart update).
        
        Usa self._last_second para evitar atualizar o embed quando o tempo não mudou.
        Isso reduz as chamadas API em 90% (de ~60/min para ~1/min).
        
        CPU Optimization: Dorme 5s quando idle (não tocando).
        """
        try:
            while True:
                # Optimization: Sleep 5s quando não está tocando (reduz CPU ~95%)
                if not self.voice_client or not self.voice_client.is_playing() or self.is_paused:
                    self._last_second = -1  # Reset counter when paused/stopped
                    await asyncio.sleep(5)  # Dormir mais quando idle
                    continue
                
                # Tocando: verificar a cada 1s
                await asyncio.sleep(1)
                
                if not self.dashboard_message:
                    continue

                # Otimização: Apenas editar se o segundo mudou (reduz chamadas API em 90%)
                try:
                    progress = self.get_progress()
                    current_second = progress['current']
                    
                    # Se o segundo não mudou, pular atualização (ECONOMIA REAL)
                    if current_second == self._last_second:
                        continue
                    
                    # Atualizar o rastreador
                    self._last_second = current_second
                    
                    # Criar embed apenas quando necessário
                    # Usar dominant_color cacheado no player (definido no send_dashboard)
                    embed = EmbedBuilder.create_now_playing_embed(
                        self.current_song,
                        list(self.queue),
                        current_seconds=current_second,
                        total_seconds=progress['duration'],
                        dominant_color=getattr(self, '_dominant_color', None),
                    )
                    
                    # Editar a mensagem apenas quando o segundo mudou
                    await self.dashboard_message.edit(embed=embed)
                    
                except discord.NotFound:
                    self.dashboard_message = None # Mensagem deletada
                except Exception as e:
                    logging.debug(f"Erro ao atualizar dashboard (loop): {e}")

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logging.error(f"Erro fatal no dashboard loop: {e}")

    async def send_dashboard(self):
        """Envia/Renova a mensagem do dashboard (Imagem + Embed)."""
        if not self.dashboard_context or not self.current_song:
            return

        # Apagar mensagem anterior para não spammar
        if self.dashboard_message:
            try:
                await self.dashboard_message.delete()
            except:
                pass
            self.dashboard_message = None

        try:
            # Converter queue para lista de dicts
            next_songs = list(self.queue)
            progress   = self.get_progress()
            pct        = progress.get('percent', 0) / 100.0  # 0.0-1.0

            # Extrair cor dominante da thumbnail (para sincronizar embed e card)
            dominant_color = None
            thumb_url = (self.current_song or {}).get('thumbnail')
            if thumb_url:
                try:
                    from utils.image import fetch_image_content, get_dominant_color_from_bytes
                    content = await self.loop.run_in_executor(None, fetch_image_content, thumb_url)
                    if content:
                        dominant_color = await self.loop.run_in_executor(
                            None, get_dominant_color_from_bytes, content
                        )
                except Exception as e:
                    logging.debug(f"Erro ao extrair cor dominante: {e}")
            # Cachear no player para o dashboard loop reutilizar sem re-fetch
            self._dominant_color = dominant_color

            # Gerar Imagem (PIL) em executor para não travar o event loop
            import functools
            img_buffer = await self.loop.run_in_executor(
                None,
                functools.partial(
                    create_now_playing_card,
                    self.current_song,
                    next_songs=next_songs[:3],
                    progress_percent=pct,
                )
            )

            file = None
            if img_buffer:
                file = discord.File(img_buffer, filename="dashboard.png")

            # Gerar Embed Inicial
            embed = EmbedBuilder.create_now_playing_embed(
                self.current_song,
                next_songs,
                current_seconds=progress['current'],
                total_seconds=progress['duration'],
                dominant_color=dominant_color,
            )

            if file:
                embed.set_image(url="attachment://dashboard.png")
                
            # Enviar para o canal vinculado
            channel = self.dashboard_context.channel if hasattr(self.dashboard_context, 'channel') else self.dashboard_context
            
            if channel:
                # Tentar enviar com retries em caso de problemas de conexão/transientes
                attempts = 0
                max_attempts = 3
                while attempts < max_attempts:
                    try:
                        if file:
                            # Garantir ponteiro no início para cada tentativa
                            try:
                                img_buffer.seek(0)
                            except Exception:
                                pass
                            send_file = discord.File(img_buffer, filename="dashboard.png")
                            self.dashboard_message = await channel.send(embed=embed, file=send_file)
                        else:
                            self.dashboard_message = await channel.send(embed=embed)

                        # Iniciar loop se não estiver rodando
                        await self.start_dashboard_task()
                        break

                    except (discord.Forbidden, discord.HTTPException, ConnectionResetError, OSError) as e:
                        attempts += 1
                        logging.warning(f"Falha ao enviar dashboard (tentativa {attempts}/{max_attempts}): {e}")
                        # Se Forbidden, não adianta tentar de novo
                        if isinstance(e, discord.Forbidden):
                            logging.error("Sem permissão para enviar o dashboard no canal.")
                            break
                        # Aguarda um pouco antes de tentar novamente
                        await asyncio.sleep(1 * attempts)
                        continue

                if attempts >= max_attempts:
                    logging.error("Não foi possível enviar o dashboard após várias tentativas.")

        except Exception as e:
            logging.error(f"Erro ao enviar dashboard: {e}")


    async def add_to_queue(self, search: str, user: discord.Member):
        """Busca e adiciona música à fila (apenas primeira se for playlist)."""
        try:
            logging.info(f"[add_to_queue] Iniciando extração para: {search}")
            # IMPORTANTE: Limitar a 1 entrada para evitar processar playlists inteiras
            info_list = await self.extract_info(search, max_entries=1)
            logging.info(f"[add_to_queue] Extraído {len(info_list)} resultado(s)")
            # info_list = [(title, url, thumbnail, duration, channel), ...]
            
            if not info_list:
                raise ValueError("Nenhuma música encontrada.")
            
            # Pegar apenas a primeira música
            info = info_list[0]
            # Garantir duration_seconds disponível (info é tupla retornada por extract_info)
            duration_seconds = info[5] if len(info) > 5 else 0
            song = {
                'title': info[0],
                'url': info[1],
                'thumbnail': info[2],
                'duration': info[3],
                'duration_seconds': duration_seconds,
                'channel': info[4],
                'user': user
            }
            self.queue.append(song)
            logging.info(f"[add_to_queue] Música adicionada à fila: {song['title']}")
            logging.info(f"[add_to_queue] Tamanho da fila agora: {len(self.queue)}")
            return song
        except Exception as e:
            logging.error(f"Erro ao adicionar música: {e}")
            raise e



    async def add_playlist_async(self, search: str, user: discord.Member) -> dict:
        """Adiciona playlist de forma OTIMIZADA.
        
        1. Busca a PRIMEIRA música imediatamente e toca.
        2. Inicia o processamento do RESTO da playlist em background.
        """
        try:
            logging.info(f"🎵 Iniciando processamento OTIMIZADO de playlist: {search}")
            
            # PASSO 1: Pegar APENAS a primeira música rapidamente
            logging.info("⚡ Buscando primeira música da playlist...")
            # Usar opções temporárias para extração rápida da primeira entrada
            flat_first_opts = {
                **YDL_OPTIONS,
                'extract_flat': 'in_playlist',
                'playlistend': 1,
                'ignoreerrors': True,
            }
            first_info = await self.loop.run_in_executor(
                None,
                lambda: yt_dlp.YoutubeDL(flat_first_opts).extract_info(search, download=False)
            )

            first_song_title = "Playlist em processamento..."
            
            # Se conseguiu extrair algo
            if first_info and 'entries' in first_info:
                entries = list(first_info['entries'])
                if entries:
                    first_entry = entries[0]
                    if first_entry:
                        # Adicionar a primeira música à fila IMEDIATAMENTE
                        # Precisamos resolver a URL real se for flat? 
                        # Sim, mas o add_to_queue lida com isso se for URL.
                        # No caso de extract_flat='in_playlist', entries são dicts com url e title.
                        
                        # Criar objeto música manual para evitar double-fetch
                        song = {
                            'title': first_entry.get('title', 'Desconhecido'),
                            'url': first_entry.get('url'),
                            'thumbnail': None, # Resolvemos depois/lazy
                            'duration': first_entry.get('duration_string'),
                            'duration_seconds': first_entry.get('duration'),
                            'channel': 'Playlist',
                            'user': user,
                            'is_lazy': True # Indicar que precisa resolver stream
                        }
                        self.queue.append(song)
                        first_song_title = song['title']
                        logging.info(f"✓ Primeira música adicionada: {first_song_title}")
                        
                        # Se não estiver tocando, tocar AGORA
                        if not self.is_playing:
                             await self.play_next()
            
            # PASSO 2: Processar o RESTO em background (começando do índice 2, pois índice 1 já foi adicionado)
            asyncio.create_task(self._process_remaining_playlist(search, user, start_index=2))
            
            # Retornar info genérica
            return {
                'title': f"Playlist: {first_song_title}...",
                'url': search,
                'thumbnail': '',
                'duration': '...',
                'channel': 'Playlist',
                'user': user
            }
            
        except Exception as e:
            logging.error(f"Erro ao adicionar playlist async: {e}")
            raise e

    async def _process_remaining_playlist(self, search, user, start_index=1):
        """Processa o RESTANTE da playlist em segundo plano."""
        try:
            logging.info(f"🎵 Processando restante da playlist (iniciando em {start_index})...")
            
            # PASSO 1: Extrair URLs RAPIDAMENTE com extract_flat
            # Herdar YDL_OPTIONS para manter geo_bypass, cachedir, etc.
            flat_opts = {
                **YDL_OPTIONS,
                'extract_flat': 'in_playlist',
                'playliststart': start_index,
                'playlistend': MAX_PLAYLIST_SIZE,
                'ignoreerrors': True,
            }
            
            logging.info(f"⚡ Extraindo URLs da playlist (max {MAX_PLAYLIST_SIZE})...")
            
            # Executar em thread para não bloquear
            playlist_info = await self.loop.run_in_executor(
                None, 
                lambda: yt_dlp.YoutubeDL(flat_opts).extract_info(search, download=False)
            )
            
            if not playlist_info:
                logging.error("Nenhuma informação de playlist encontrada")
                return
            
            # Obter lista de entradas
            entries = playlist_info.get('entries', [])
            if not entries:
                logging.error("Playlist vazia")
                return
            
            # Filtrar entradas None ou inválidas antes da contagem real
            valid_entries = [e for e in entries if e is not None]
            
            total_tracks = len(valid_entries)
            logging.info(f"✓ {total_tracks} músicas válidas encontradas na playlist")
            
            # Debug: Logar primeiras entradas para verificar se parecem corretas
            if valid_entries:
                logging.debug(f"Primeira entrada: {valid_entries[0].get('title')} ({valid_entries[0].get('url')})")
                logging.debug(f"Última entrada: {valid_entries[-1].get('title')}")

            # Detecção de Mix do YouTube (Geralmente começa com RD... e tem muitas músicas)
            # Se for um Mix e o usuário esperava uma playlist pequena, isso explica os 99 itens.
            if 'RD' in search or 'list=RD' in search:
                logging.warning("Detectado YouTube MIX (Lista infinita). Limitando a 25 músicas para evitar spam.")
                # Reduzir limite se for mix para não lotar a fila
                valid_entries = valid_entries[:25]
            
            first_song_added = False
            added_count = 0

            # PASSO 2: Adicionar à fila
            for idx, entry in enumerate(valid_entries):
                if added_count >= MAX_PLAYLIST_SIZE:
                    break
                    
                if not entry:
                    continue
                
                # Tentar pegar URL original
                url = entry.get('url') or entry.get('webpage_url') or entry.get('id')
                
                # Reconstruir URL se for apenas ID
                if url and not url.startswith('http'):
                    ie_key = entry.get('ie_key', '')
                    if ie_key == 'Youtube' or 'youtube' in (entry.get('extractor', '') or ''):
                        url = f"https://www.youtube.com/watch?v={url}"
                    elif ie_key == 'SoundCloud' or 'soundcloud' in (entry.get('extractor', '') or ''):
                        url = f"https://soundcloud.com/{url}" if not url.startswith('soundcloud') else f"https://{url}"
                
                # Tentar pegar título de MÚLTIPLAS chaves
                title = (
                    entry.get('title') or 
                    entry.get('track') or 
                    entry.get('name') or 
                    None  # Será resolvido depois se None
                )
                
                duration = entry.get('duration', 0)
                thumbnail = entry.get('thumbnail', '')
                
                # Se NÃO tem título (comum em SoundCloud flat), usar URL como temporário
                # O título real será obtido quando a música for tocar (lazy resolve)
                if not title:
                    # Usar parte da URL como título temporário
                    if url:
                        # Extrair algo legível da URL
                        temp_title = url.split('/')[-1].split('?')[0]
                        # Limitar tamanho e limpar
                        temp_title = temp_title.replace('-', ' ').replace('_', ' ')[:40]
                        title = f"🎵 {temp_title}..."
                        logging.debug(f"Título temporário criado: {title}")
                    else:
                        title = f"🎵 Música #{idx+1}"
                
                song = {
                    'title': title,
                    'url': url,
                    'thumbnail': thumbnail,
                    'duration': self._format_duration(duration),
                    'duration_seconds': duration,
                    'is_lazy': True,  # IMPORTANTE: Será resolvido no play_next
                    'channel': 'Playlist',
                    'user': user
                }
                
                self.queue.append(song)
                added_count += 1
                
                # Iniciar reprodução assim que a primeira música estiver pronta
                if not first_song_added:
                    first_song_added = True
                    logging.info(f"✓ Primeira música da playlist pronta: {song['title']}")
                    if not self.voice_client or not self.voice_client.is_playing():
                        self.loop.create_task(self.play_next())

            logging.info(f"✓ Playlist completa: {added_count} músicas adicionadas à fila")
            
        except Exception as e:
            logging.error(f"Erro ao processar playlist: {e}")


    async def extract_info(self, search, max_entries=None):
        """Extrai informações do YouTube/SoundCloud.
        
        Args:
            search: URL ou termo de busca
            max_entries: Número máximo de entradas a extrair (None = todas)
        
        Retorna lista de tuplas: [(title, url, thumbnail, duration, channel, duration_seconds), ...]
        """
        def run() -> list:
            # Reusar self.ydl ao invés de criar nova instância (economiza RAM/tempo)
            info = None
            entries = []
            
            if search.startswith(('http://', 'https://')):
                # URL direta - pode ser música única ou playlist
                info = self.ydl.extract_info(search, download=False)
                if not info:
                    raise ValueError("yt-dlp retornou None para a URL fornecida.")
                # Verificar se é playlist
                if 'entries' in info:
                    entries = list(info['entries'])
                else:
                    entries = [info]
                    
            elif search.startswith(('scsearch:', 'ytsearch:')):
                # Pesquisa explícita
                info = self.ydl.extract_info(search, download=False)
                entries = info.get('entries', [])
            else:
                # Padrão: Pesquisa do YouTube (apenas primeiro resultado)
                info = self.ydl.extract_info(f"ytsearch:{search}", download=False)
                entries = info.get('entries', [])
            
            if not entries:
                raise ValueError("Nenhum resultado encontrado.")
            
            # Filtrar entradas None
            entries = [e for e in entries if e is not None]
            
            # Limitar número de entradas se especificado
            if max_entries is not None:
                entries = entries[:max_entries]
            
            # Processar todas as entradas
            results = []
            for entry in entries:
                if not entry:  # Pular entradas vazias
                    continue
                
                try:
                    title = entry.get('title', 'Desconhecido')
                    url = entry.get('url', entry.get('webpage_url', ''))
                    thumbnail = entry.get('thumbnail', '')
                    
                    duration_seconds = entry.get('duration', 0)
                    if duration_seconds:
                        minutes, seconds = divmod(duration_seconds, 60)
                        hours, minutes = divmod(minutes, 60)
                        duration_formatted = f"{int(hours)}:{int(minutes):02d}:{int(seconds):02d}" if hours > 0 else f"{int(minutes)}:{int(seconds):02d}"
                    else:
                        duration_formatted = "Desconhecida"
                    
                    channel = entry.get('uploader', entry.get('channel', 'Desconhecido'))
                    results.append((title, url, thumbnail, duration_formatted, channel, duration_seconds))
                except Exception as e:
                    # Log mas não interrompe o processamento
                    logging.warning(f"Erro ao processar entrada da playlist: {e}")
                    continue
            
            return results

        return await self.loop.run_in_executor(None, run)

    async def play_next(self):
        """Toca a próxima música da fila com Lazy Resolve e SafeFFmpeg.
        
        Usa lock para garantir que apenas 1 play_next roda por vez.
        Previne race conditions quando múltiplas triggers tentam chamar.
        """
        # Adquirir lock para evitar múltiplos play_next concorrentes
        async with self._play_lock:
            await self._play_next_internal()
    
    async def _play_next_internal(self):
        """Implementação interna de play_next (protegida pelo lock)."""
        logging.info(f"[play_next] Chamado. Voice client existe: {self.voice_client is not None}")
        
        # 1. Verificar conexão de voz
        if not self.voice_client or not self.voice_client.is_connected():
            logging.warning("[play_next] Bot desconectado do canal de voz. Limpando fila.")
            self.stop() # Limpa fila e para tudo
            return

        if self.is_shuffling and len(self.queue) > 1:
            import random
            queue_list = list(self.queue)
            random.shuffle(queue_list)
            self.queue = deque(queue_list)

        logging.info(f"[play_next] Tamanho da fila: {len(self.queue)}")
        if not self.queue:
            self.current_song = None
            logging.info("[play_next] Fila vazia, nada para tocar")
            return

        self.current_song = self.queue.popleft()
        logging.info(f"[play_next] Preparando: {self.current_song['title']}")
        # Log de debug: mostrar duração e flags para investigar ausência de barra de progresso
        try:
            logging.debug(f"[play_next] current_song metadata: title={self.current_song.get('title')}, duration_seconds={self.current_song.get('duration_seconds')}, is_lazy={self.current_song.get('is_lazy')}")
        except Exception:
            pass

        # 2. LAZY RESOLVE - Resolver URL de stream AGORA
        source_url = self.current_song['url']
        
        # Verificar Cache Primeiro
        cached_url = self.stream_cache.get(source_url)
        if cached_url:
            logging.info("⚡ URL recuperada do Cache!")
            source_url = cached_url
        else:
            # Se não estiver em cache ou for 'is_lazy', resolver via yt-dlp
            # OU se for stream direta de rádio/arquivo, não precisa resolver
            requires_resolution = self.current_song.get('is_lazy', False) or 'youtube' in source_url or 'soundcloud' in source_url
            
            # Se for link direto (http) e não tiver cara de serviço conhecido, talvez não precise
            # Mas o yt-dlp lida bem com isso.
            
            if requires_resolution:
                try:
                    logging.info(f"Resolvendo Stream URL (Lazy)... Cache Miss para {source_url}")
                    # EXECUTAR EM THREAD para não bloquear!
                    # Usar self.ydl reutilizado
                    info = await self.loop.run_in_executor(
                        None, 
                        lambda: self.ydl.extract_info(source_url, download=False)
                    )
                    
                    if not info:
                         raise ValueError("Falha ao extrair info")
                    
                    # Atualizar metadados da música atual com infos completas
                    self.current_song['title'] = info.get('title', self.current_song['title'])
                    self.current_song['thumbnail'] = info.get('thumbnail', self.current_song['thumbnail'])
                    
                    duration = info.get('duration', 0)
                    self.current_song['duration'] = self._format_duration(duration)
                    self.current_song['duration_seconds'] = duration
                    
                    # Pegar URL real do áudio
                    source_url = info.get('url')
                    
                    # Salvar no cache
                    if source_url:
                        self.stream_cache.set(self.current_song['url'], source_url)
                    
                except Exception as e:
                    logging.error(f"Erro ao resolver stream: {e}")
                    # Tentar próxima
                    self.loop.create_task(self.play_next())
                    return

        # Proteção final contra URL nula
        if not source_url:
            logging.error("Source URL é None após resolução. Pulando música.")
            await self.play_next()
            return

        seek_position = self.current_song.get('seek', 0)
        
        before_options = '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
        output_options = f'-vn -af "aresample=48000,atempo=1.0,volume={self.volume}" -bufsize 10M'
        
        if seek_position > 0:
            output_options += f' -ss {seek_position}'
            logging.info(f"[play_next] Resumindo de {seek_position}s")

        ffmpeg_options = {
            'before_options': before_options,
            'options': output_options
        }

        def after_play(err):
            """Callback executado após música terminar."""
            try:
                if err:
                    logging.error(f"Erro no player: {err}")
                
                if self.stopped_for_sfx:
                    logging.info("Música parada para SFX - aguardando retomada")
                    return

                if self.is_looping and self.current_song:
                    if 'seek' in self.current_song:
                        del self.current_song['seek']
                    self.current_song['is_lazy'] = True # Re-resolver no próximo loop para garantir link fresco!
                    self.queue.appendleft(self.current_song)
                
                # Agendar próxima música
                future = asyncio.run_coroutine_threadsafe(self.play_next(), self.bot.loop)
                # Não esperar result aqui para não travar thread do ffmpeg
                
            except Exception as e:
                logging.error(f"Erro crítico no callback after_play: {e}")

        try:
            # USAR O NOVO SafeFFmpegPCMAudio
            executable = 'ffmpeg'
            
            source = SafeFFmpegPCMAudio(source_url, executable=executable, **ffmpeg_options)
            
            self.voice_client.play(source, after=after_play)
            
            self.is_paused = False
            self.consecutive_errors = 0
            self.stopped_for_sfx = False
            
            # Resetar contadores de tempo
            self.started_at = time.monotonic() - seek_position
            self.paused_at = None
            self.total_paused = 0
            self._last_second = -1  # Reset dashboard update counter para nova música
            
            self.song_duration = self.current_song.get('duration_seconds', 0)
                
            # Iniciar Dashboard
            try:
                # Não aguardar o envio do dashboard para não bloquear o início do áudio.
                # Executar em background para evitar que falhas de rede afetem o playback.
                self.loop.create_task(self.send_dashboard())
            except Exception as e:
                logging.error(f"Erro ao agendar envio do dashboard: {e}")

            # 3. PRÉ-RESOLUÇÃO (Pre-Resolve Next)
            # Tentar resolver a próxima música em background para evitar gap
            if self.queue:
                next_song = self.queue[0]
                if next_song.get('is_lazy') or 'youtube' in next_song['url']:
                     logging.info(f"🔮 Pré-resolvendo próxima música: {next_song['title']}")
                     asyncio.create_task(self._pre_resolve_next(next_song))

        except Exception as e:
            logging.error(f"Erro ao iniciar playback: {e}")
            self.consecutive_errors += 1
            if self.consecutive_errors > 5:
                logging.error("Muitos erros consecutivos. Parando.")
                self.stop()
                return

            await asyncio.sleep(1)
            # Evitar recursão de stack (User Feedback #1)
            self.loop.create_task(self.play_next())

    async def _pre_resolve_next(self, song):
        """Resolve a URL da próxima música silenciosamente."""
        try:
            source_url = song['url']
            # Se já estiver em cache, ignora
            if self.stream_cache.get(source_url):
                return

            # Resolver
            info = await self.loop.run_in_executor(
                None, 
                lambda: self.ydl.extract_info(source_url, download=False)
            )
            
            if info and info.get('url'):
                self.stream_cache.set(source_url, info['url'])
                # Atualizar metadados de forma segura (verificar que o song ainda é o mesmo objeto)
                try:
                    song['title'] = info.get('title', song['title'])
                    song['thumbnail'] = info.get('thumbnail', song.get('thumbnail'))
                    duration = info.get('duration', 0)
                    song['duration_seconds'] = duration
                    song['duration'] = self._format_duration(duration)
                    song['is_lazy'] = False  # Marcar como resolvido
                except Exception:
                    pass  # Race condition: song pode ter sido removido da fila
                logging.info("Próxima música pré-resolvida com sucesso!")
                 
        except Exception as e:
            logging.debug(f"Falha na pré-resolução (não crítico): {e}")

    async def play_soundboard(self, sfx_path: str, volume: float = 1.0):
        """Tocar efeito sonoro do soundboard com interrupção e retomada da música."""
        if self.sfx_playing:
            return
        
        if not self.voice_client:
            return
        
        self.sfx_playing = True
        self.stopped_for_sfx = False
        
        # Se estiver tocando música, parar e salvar estado
        if self.voice_client.is_playing() and self.current_song:
            self.stopped_for_sfx = True
            
            # Calcular posição atual para resume
            progress = self.get_progress()
            current_pos = progress['current']
            
            logging.info(f"Parando música para SFX. Posição salva: {current_pos}s")
            
            # Salvar posição na música atual e recolocar no início da fila
            self.current_song['seek'] = current_pos
            self.queue.appendleft(self.current_song)
            
            # Parar playback atual (acionará after_play, que deve ignorar por causa de stopped_for_sfx)
            self.voice_client.stop()
            
            # Pequeno delay para garantir que o ffmpeg liberou o áudio
            await asyncio.sleep(0.5)
        
        # Tocar SFX
        ffmpeg_options = {
            'options': f'-vn -af "volume={volume}"'
        }
        
        def after_sfx(error):
            """Callback após SFX terminar."""
            self.sfx_playing = False
            
            if self.stopped_for_sfx:
                logging.info("SFX finalizado, retomando música...")
                self.stopped_for_sfx = False
                
                # Retomar música (fire-and-forget — não bloquear a thread do FFmpeg)
                asyncio.run_coroutine_threadsafe(self.play_next(), self.bot.loop)

        try:
            executable = 'ffmpeg'
            # USAR SafeFFmpegPCMAudio
            source = SafeFFmpegPCMAudio(sfx_path, executable=executable, **ffmpeg_options)
            self.voice_client.play(source, after=after_sfx)
            logging.info(f"SFX iniciado: {sfx_path}")
        except Exception as e:
            logging.error(f"Erro ao iniciar SFX: {e}")
            self.sfx_playing = False
            if self.stopped_for_sfx:
                self.stopped_for_sfx = False
                self.loop.create_task(self.play_next())

    def stop(self):
        # Cancelar dashboard task diretamente (seguro em contexto síncrono)
        if self.dashboard_task and not self.dashboard_task.done():
            self.dashboard_task.cancel()
        self.queue.clear()
        self.current_song = None
        self._last_second = -1  # Reset contador de atualização
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()

    def skip(self):
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()

    def pause(self):
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.pause()
            self.is_paused = True

            if not self.paused_at:
                self.paused_at = time.monotonic()

    def resume(self):
        if self.voice_client and self.voice_client.is_paused():
            self.voice_client.resume()
            self.is_paused = False

            if self.paused_at:
                self.total_paused += time.monotonic() - self.paused_at
                self.paused_at = None

    def set_volume(self, volume):
        """Define o volume. Aceita 0.0 a 1.5 (acima de 1.0 = amplificação)."""
        self.volume = max(0.0, min(1.5, volume))
