"""Motor de reprodu??o principal e pr?-resolu??o da fila."""

import asyncio
import logging
import time
import yt_dlp
from collections import deque

from .constants import YDL_FALLBACK_CLIENTS, YDL_OPTIONS
from .core import SafeFFmpegPCMAudio


def _extract_video_id(url: str) -> str | None:
    """Extrai o video_id de uma URL do YouTube para o cache de falhas."""
    if not url:
        return None
    # youtube.com/watch?v=XXXX  ou  youtu.be/XXXX
    if "v=" in url:
        return url.split("v=")[-1].split("&")[0]
    if "youtu.be/" in url:
        return url.split("youtu.be/")[-1].split("?")[0]
    return None


def _try_extract_with_clients(
    ydl_base_params: dict, url: str, clients: list
) -> dict | None:
    """Tenta extrair info usando uma lista específica de player_clients.

    Cria uma instância temporária do YoutubeDL com os clientes indicados
    para não modificar a instância global (self.ydl).
    """
    override = {
        **ydl_base_params,
        "extractor_args": {
            "youtube": {
                "player_client": clients,
            }
        },
    }
    with yt_dlp.YoutubeDL(override) as ydl_tmp:
        return ydl_tmp.extract_info(url, download=False)


class PlaybackMixin:
    """Comportamentos de playback do MusicPlayer."""

    @staticmethod
    def _ffmpeg_escape(value: str) -> str:
        return (
            str(value)
            .replace("\\", "\\\\")
            .replace('"', r"\"")
        )

    def _build_ffmpeg_request_options(self, headers: dict | None) -> str:
        """Monta opções HTTP completas para ffmpeg (modo robusto)."""
        if not headers:
            return ""

        options = []

        # 🔥 HEADERS COMPLETOS (principal melhoria)
        header_lines = []
        for k, v in headers.items():
            if v:
                header_lines.append(f"{k}: {v}")
        headers_str = "\\r\\n".join(header_lines) + "\\r\\n"
        
        if header_lines:  # evita passar -headers vazio
            options.append(f'-headers "{self._ffmpeg_escape(headers_str)}"')

        # 🔧 Compatibilidade extra (fallback)
        user_agent = headers.get("User-Agent") or headers.get("user-agent")
        referer = headers.get("Referer") or headers.get("referer")
        origin = headers.get("Origin") or headers.get("origin")

        if user_agent:
            options.append(f'-user_agent "{self._ffmpeg_escape(user_agent)}"')

        if referer:
            options.append(f'-referer "{self._ffmpeg_escape(referer)}"')
        elif origin:
            options.append(f'-referer "{self._ffmpeg_escape(origin)}"')

        return " ".join(options)

    def _resolve_stream_url(self, source_url: str) -> tuple[str, dict]:
        """Resolve a URL de stream com fallback automático de player_clients.

        Estratégia:
        1. Tenta com self.ydl (clientes primários: ios, android, tv_embedded).
        2. Se falhar, itera pelos YDL_FALLBACK_CLIENTS em ordem.
        3. Se todos falharem, lança exceção.

        Retorna: (stream_url, http_headers)
        """
        last_error: Exception | None = None

        # --- Tentativa 1: cliente primário (self.ydl já configurado) ---
        try:
            info = self.ydl.extract_info(source_url, download=False)
            if info and info.get("url"):
                return info["url"], dict(info.get("http_headers") or {}), info
        except Exception as e:
            last_error = e
            logging.warning(
                f"[resolve] Clientes primários falharam para {source_url}: {e}"
            )

        # --- Tentativas de Fallback ---
        base_params = dict(self.ydl.params)
        # Remover chaves que causam conflito ao criar instância temporária
        base_params.pop("logger", None)

        for idx, clients in enumerate(YDL_FALLBACK_CLIENTS):
            try:
                logging.info(
                    f"[resolve] Fallback {idx + 1}/{len(YDL_FALLBACK_CLIENTS)} com clientes: {clients}"
                )
                info = _try_extract_with_clients(
                    base_params, source_url, clients
                )
                if info and info.get("url"):
                    logging.info(
                        f"[resolve] ✓ Sucesso com clientes: {clients}"
                    )
                    return (
                        info["url"],
                        dict(info.get("http_headers") or {}),
                        info,
                    )
            except Exception as e:
                last_error = e
                logging.warning(f"[resolve] Fallback {clients} falhou: {e}")

        raise ValueError(
            f"Todos os clientes falharam para {source_url}: {last_error}"
        )

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
        logging.info(
            f"[play_next] Chamado. Voice client existe: {self.voice_client is not None}"
        )

        # 1. Verificar conexão de voz
        if not self.voice_client or not self.voice_client.is_connected():
            logging.warning(
                "[play_next] Bot desconectado do canal de voz. Limpando fila."
            )
            self.stop()  # Limpa fila e para tudo
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
            logging.info(
                f"[play_next] Fila vazia, limpando dashboard em {self._queue_empty_grace_seconds}s se continuar vazia"
            )
            return

        self._cancel_queue_empty_cleanup()
        self.current_song = self.queue.popleft()
        logging.info(f"[play_next] Preparando: {self.current_song['title']}")
        try:
            logging.debug(
                f"[play_next] current_song metadata: title={self.current_song.get('title')}, duration_seconds={self.current_song.get('duration_seconds')}, is_lazy={self.current_song.get('is_lazy')}"
            )
        except Exception:
            pass

        # 2. LAZY RESOLVE - Resolver URL de stream AGORA
        source_url = self.current_song["url"]
        source_headers = dict(self.current_song.get("stream_headers") or {})

        # --- Cache de falhas: pular vídeos que já falharam nesta sessão ---
        video_id = _extract_video_id(source_url)
        if video_id and video_id in self._failed_ids:
            logging.warning(
                f"[play_next] Pulando {source_url} — marcado como falho nesta sessão."
            )
            self.loop.create_task(self.play_next())
            return

        # Verificar Cache de Streams Primeiro
        cached_entry = self.stream_cache.get(source_url)
        if cached_entry:
            logging.info("⚡ URL recuperada do Cache!")
            if isinstance(cached_entry, dict):
                source_url = cached_entry.get("url") or source_url
                source_headers = dict(
                    cached_entry.get("headers") or source_headers
                )
            else:
                source_url = cached_entry
        else:
            requires_resolution = (
                self.current_song.get("is_lazy", False)
                and not self._is_direct_stream_url(source_url)
            ) or self._is_resolvable_service_url(source_url)

            if requires_resolution:
                try:
                    logging.info(
                        f"Resolvendo Stream URL (Lazy)... Cache Miss para {source_url}"
                    )
                    # _resolve_stream_url tenta primário + fallbacks automaticamente
                    (
                        stream_url,
                        stream_headers,
                        info,
                    ) = await self.loop.run_in_executor(
                        None, lambda: self._resolve_stream_url(source_url)
                    )

                    extractor_name = str(info.get("extractor", "")).lower()
                    if extractor_name != "generic":
                        self.current_song["title"] = info.get(
                            "title", self.current_song["title"]
                        )
                        self.current_song["thumbnail"] = info.get(
                            "thumbnail", self.current_song["thumbnail"]
                        )
                        duration = info.get("duration", 0)
                        self.current_song["duration"] = self._format_duration(
                            duration
                        )
                        self.current_song["duration_seconds"] = duration
                    else:
                        logging.debug(
                            "[play_next] Extractor 'generic' detectado; preservando metadados atuais."
                        )

                    source_url = stream_url
                    source_headers = stream_headers
                    if source_headers:
                        self.current_song["stream_headers"] = source_headers

                    # Salvar no cache de streams
                    if source_url:
                        self.stream_cache.set(
                            self.current_song["url"],
                            {"url": source_url, "headers": source_headers},
                        )

                except Exception as e:
                    logging.error(f"Erro ao resolver stream: {e}")
                    # Marcar video_id como falho para não tentar de novo nesta sessão
                    if video_id:
                        self._failed_ids.add(video_id)
                        logging.info(
                            f"[play_next] video_id '{video_id}' adicionado ao cache de falhas."
                        )
                    self.loop.create_task(self.play_next())
                    return

        # Proteção final contra URL nula
        if not source_url:
            logging.error("Source URL é None após resolução. Pulando música.")
            if video_id:
                self._failed_ids.add(video_id)
            self.loop.create_task(self.play_next())
            return

        seek_position = self.current_song.get("seek", 0)

        before_options = (
            "-reconnect 1 "
            "-reconnect_streamed 1 "
            "-reconnect_on_network_error 1 "
            "-reconnect_on_http_error 5xx "
            "-reconnect_delay_max 10 "
            "-rw_timeout 15000000 "
        )
        request_options = self._build_ffmpeg_request_options(source_headers)
        if request_options:
            before_options = f"{before_options} {request_options}"
        output_options = (
            f'-vn -b:a 192k -af "volume={self.volume}" '
            '-f s16le -ar 48000 -ac 2'
        )

        if seek_position > 0:
            before_options += f" -ss {seek_position}"

        ffmpeg_options = {
            "before_options": before_options,
            "options": output_options,
        }

        def after_play(err):
            """Callback executado após música terminar."""
            try:
                if err:
                    logging.error(f"Erro no player: {err}")

                if self.stopped_for_sfx:
                    logging.info(
                        "Música parada para SFX - aguardando retomada"
                    )
                    return

                if self.is_looping and self.current_song:
                    if "seek" in self.current_song:
                        del self.current_song["seek"]
                    self.current_song["is_lazy"] = (
                        True  # Re-resolver no próximo loop para garantir link fresco!
                    )
                    self.queue.appendleft(self.current_song)

                # Agendar próxima música
                next_future = asyncio.run_coroutine_threadsafe(
                    self.play_next(), self.bot.loop
                )

                def _log_future_error(fut):
                    try:
                        exc = fut.exception()
                    except Exception as callback_exc:
                        logging.error(
                            f"Falha ao inspecionar tarefa agendada: {callback_exc}"
                        )
                        return
                    if exc:
                        logging.error(f"Erro ao agendar proxima musica: {exc}")

                next_future.add_done_callback(_log_future_error)

            except Exception as e:
                logging.error(f"Erro crítico no callback after_play: {e}")

        try:
            executable = "ffmpeg"
            source = SafeFFmpegPCMAudio(
                source_url, executable=executable, **ffmpeg_options
            )

            self.voice_client.play(source, after=after_play)

            self.is_paused = False
            self.consecutive_errors = 0
            self.stopped_for_sfx = False

            # Resetar contadores de tempo
            self.started_at = time.monotonic() - seek_position
            self.paused_at = None
            self.total_paused = 0
            self._last_second = -1

            self.song_duration = self.current_song.get("duration_seconds", 0)

            # Iniciar Dashboard
            try:
                self.loop.create_task(self.send_dashboard())
            except Exception as e:
                logging.error(f"Erro ao agendar envio do dashboard: {e}")

            # 3. PRÉ-RESOLUÇÃO (Pre-Resolve Next)
            if self.queue:
                next_song = self.queue[0]
                if next_song.get("is_lazy") or "youtube" in next_song["url"]:
                    logging.info(
                        f"🔮 Pré-resolvendo próxima música: {next_song['title']}"
                    )
                    asyncio.create_task(self._pre_resolve_next(next_song))

        except Exception as e:
            logging.error(f"Erro ao iniciar playback: {e}")
            self.consecutive_errors += 1
            if self.consecutive_errors > 5:
                logging.error("Muitos erros consecutivos. Parando.")
                self.stop()
                return

            await asyncio.sleep(1)
            self.loop.create_task(self.play_next())

    async def _pre_resolve_next(self, song):
        """Resolve a URL da próxima música silenciosamente."""
        try:
            if song is self.current_song:
                return
            source_url = song["url"]
            if self._is_direct_stream_url(source_url):
                return
            if not (
                song.get("is_lazy")
                or self._is_resolvable_service_url(source_url)
            ):
                return
            if self.stream_cache.get(source_url):
                return

            # Verificar cache de falhas antes de tentar
            video_id = _extract_video_id(source_url)
            if video_id and video_id in self._failed_ids:
                logging.info(
                    f"[pre_resolve] Pulando {source_url} — no cache de falhas."
                )
                return

            stream_url, stream_headers, info = await self.loop.run_in_executor(
                None, lambda: self._resolve_stream_url(source_url)
            )

            if stream_url:
                if song is self.current_song:
                    return
                self.stream_cache.set(
                    source_url, {"url": stream_url, "headers": stream_headers}
                )
                extractor_name = str(info.get("extractor", "")).lower()
                try:
                    if extractor_name != "generic":
                        song["title"] = info.get("title", song["title"])
                        song["thumbnail"] = info.get(
                            "thumbnail", song.get("thumbnail")
                        )
                        duration = info.get("duration", 0)
                        song["duration_seconds"] = duration
                        song["duration"] = self._format_duration(duration)
                    if stream_headers:
                        song["stream_headers"] = stream_headers
                    song["is_lazy"] = False
                except Exception:
                    pass
                logging.info("Próxima música pré-resolvida com sucesso!")

        except Exception as e:
            logging.debug(f"Falha na pré-resolução (não crítico): {e}")
            # Marcar como falha para não re-tentar desnecessariamente
            video_id = _extract_video_id(song.get("url", ""))
            if video_id:
                self._failed_ids.add(video_id)