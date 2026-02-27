"""Motor de reprodu??o principal e pr?-resolu??o da fila."""

import asyncio
import logging
import time
from collections import deque

from .core import SafeFFmpegPCMAudio

class PlaybackMixin:
    """Comportamentos de playback do MusicPlayer."""

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

        # Defesa principal contra corrida: se já está reproduzindo/pausado, não iniciar outra faixa.
        if self.is_voice_busy:
            logging.info("[play_next] Ignorado: voice client já está ocupado.")
            return

        # Durante SFX, não devemos consumir a fila normal.
        if self.sfx_playing:
            logging.info("[play_next] Ignorado: soundboard em reprodução.")
            return

        if self.is_shuffling and len(self.queue) > 1:
            import random
            queue_list = list(self.queue)
            random.shuffle(queue_list)
            self.queue = deque(queue_list)

        logging.info(f"[play_next] Tamanho da fila: {len(self.queue)}")
        if not self.queue:
            self.current_song = None
            self._schedule_queue_empty_cleanup()
            logging.info(f"[play_next] Fila vazia, limpando dashboard em {self._queue_empty_grace_seconds}s se continuar vazia")
            return

        self._cancel_queue_empty_cleanup()
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
            # Resolver apenas quando necessário em URL de serviço canônica.
            # Evita falso-positivo em stream direto contendo query param "source=youtube".
            requires_resolution = (
                (self.current_song.get('is_lazy', False) and not self._is_direct_stream_url(source_url))
                or self._is_resolvable_service_url(source_url)
            )
            
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
                    
                    extractor_name = str(info.get('extractor', '')).lower()
                    # Não sobrescrever metadados com extractor genérico (ex.: "videoplayback").
                    if extractor_name != 'generic':
                        self.current_song['title'] = info.get('title', self.current_song['title'])
                        self.current_song['thumbnail'] = info.get('thumbnail', self.current_song['thumbnail'])
                        duration = info.get('duration', 0)
                        self.current_song['duration'] = self._format_duration(duration)
                        self.current_song['duration_seconds'] = duration
                    else:
                        logging.debug("[play_next] Extractor 'generic' detectado; preservando metadados atuais.")
                    
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
            self.loop.create_task(self.play_next())
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
                next_future = asyncio.run_coroutine_threadsafe(self.play_next(), self.bot.loop)
                def _log_future_error(fut):
                    try:
                        exc = fut.exception()
                    except Exception as callback_exc:
                        logging.error(f"Falha ao inspecionar tarefa agendada: {callback_exc}")
                        return
                    if exc:
                        logging.error(f"Erro ao agendar proxima musica: {exc}")

                next_future.add_done_callback(_log_future_error)
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
            # Se a faixa já virou a atual, não pré-resolver para evitar corrida de extração duplicada.
            if song is self.current_song:
                return
            source_url = song['url']
            if self._is_direct_stream_url(source_url):
                return
            if not (song.get('is_lazy') or self._is_resolvable_service_url(source_url)):
                return
            # Se já estiver em cache, ignora
            if self.stream_cache.get(source_url):
                return

            # Resolver
            info = await self.loop.run_in_executor(
                None, 
                lambda: self.ydl.extract_info(source_url, download=False)
            )
            
            if info and info.get('url'):
                if song is self.current_song:
                    return
                self.stream_cache.set(source_url, info['url'])
                extractor_name = str(info.get('extractor', '')).lower()
                # Atualizar metadados de forma segura (verificar que o song ainda é o mesmo objeto)
                try:
                    if extractor_name != 'generic':
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
