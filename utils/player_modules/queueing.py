"""Rotinas de fila e processamento ass?ncrono de playlists."""

import asyncio
import logging

import discord
import yt_dlp

from .constants import MAX_PLAYLIST_SIZE, YDL_OPTIONS

class QueueMixin:
    """Comportamentos de enfileiramento do MusicPlayer."""

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
            stream_url = info[6] if len(info) > 6 else ''
            http_headers = info[7] if len(info) > 7 else {}
            
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
            self._cancel_queue_empty_cleanup()
            
            if stream_url and self._is_direct_stream_url(stream_url):
                self.stream_cache.set(
                    song['url'],
                    {'url': stream_url, 'headers': http_headers}
                )
                logging.info(f"[add_to_queue] Stream URL cacheada preventivamente para: {song['title']}")
                
            logging.info(f"[add_to_queue] Música adicionada à fila: {song['title']}")
            logging.info(f"[add_to_queue] Tamanho da fila agora: {len(self.queue)}")
            return song
        except Exception as e:
            logging.error(f"Erro ao adicionar música: {e}")
            raise e

    async def add_playlist_async(self, search: str, user: discord.Member) -> dict:
        """Adiciona playlist de forma otimizada.

        1. Busca a PRIMEIRA música imediatamente e toca.
        2. Inicia o processamento do RESTO da playlist em background.
        """
        try:
            logging.info(f"🎵 Iniciando processamento OTIMIZADO de playlist: {search}")

            # PASSO 1: Pegar APENAS a primeira música rapidamente
            logging.info("⚡ Buscando primeira música da playlist...")
            flat_first_opts = {
                **YDL_OPTIONS,
                'extract_flat': 'in_playlist',
                'playlistend': 1,
                'ignoreerrors': True,
            }

            def _extract_first():
                with yt_dlp.YoutubeDL(flat_first_opts) as ydl:
                    return ydl.extract_info(search, download=False)

            first_info = await self.loop.run_in_executor(None, _extract_first)

            first_song_title = "Playlist em processamento..."
            playback_started = False

            if first_info and 'entries' in first_info:
                entries = list(first_info['entries'])
                if entries:
                    first_entry = entries[0]
                    if first_entry:
                        song = {
                            'title': first_entry.get('title', 'Desconhecido'),
                            'url': first_entry.get('url'),
                            'thumbnail': None,
                            'duration': first_entry.get('duration_string'),
                            'duration_seconds': first_entry.get('duration'),
                            'channel': 'Playlist',
                            'user': user,
                            'is_lazy': True,
                        }
                        self.queue.append(song)
                        self._cancel_queue_empty_cleanup()
                        first_song_title = song['title']
                        logging.info(f"✓ Primeira música adicionada: {first_song_title}")

                        if not self.is_playback_busy:
                            await self.play_next()
                            playback_started = True

            # PASSO 2: Processar o RESTO em background
            asyncio.create_task(
                self._process_remaining_playlist(
                    search, user,
                    start_index=2,
                    playback_already_started=playback_started,
                )
            )

            return {
                'title': f"Playlist: {first_song_title}...",
                'url': search,
                'thumbnail': '',
                'duration': '...',
                'channel': 'Playlist',
                'user': user,
            }

        except Exception as e:
            logging.error(f"Erro ao adicionar playlist async: {e}")
            raise e

    async def _process_remaining_playlist(
        self, search, user, start_index=1, playback_already_started=False,
    ):
        """Processa o restante da playlist em segundo plano.

        Apenas enfileira as faixas restantes. Só dispara ``play_next`` se
        ``add_playlist_async`` não tiver conseguido iniciar a reprodução
        (ex.: primeira entrada era inválida).
        """
        try:
            logging.info(
                f"🎵 Processando restante da playlist (iniciando em {start_index})..."
            )

            flat_opts = {
                **YDL_OPTIONS,
                'extract_flat': 'in_playlist',
                'playliststart': start_index,
                'playlistend': MAX_PLAYLIST_SIZE,
                'ignoreerrors': True,
            }

            logging.info(f"⚡ Extraindo URLs da playlist (max {MAX_PLAYLIST_SIZE})...")

            def _extract_remaining():
                with yt_dlp.YoutubeDL(flat_opts) as ydl:
                    return ydl.extract_info(search, download=False)

            playlist_info = await self.loop.run_in_executor(None, _extract_remaining)

            if not playlist_info:
                logging.error("Nenhuma informação de playlist encontrada")
                return

            entries = playlist_info.get('entries', [])
            if not entries:
                logging.error("Playlist vazia")
                return

            valid_entries = [e for e in entries if e is not None]

            total_tracks = len(valid_entries)
            logging.info(f"✓ {total_tracks} músicas válidas encontradas na playlist")

            if valid_entries:
                logging.debug(
                    f"Primeira entrada: {valid_entries[0].get('title')} "
                    f"({valid_entries[0].get('url')})"
                )
                logging.debug(f"Última entrada: {valid_entries[-1].get('title')}")

            # Detecção de Mix do YouTube
            if 'RD' in search or 'list=RD' in search:
                logging.warning(
                    "Detectado YouTube MIX (Lista infinita). "
                    "Limitando a 25 músicas para evitar spam."
                )
                valid_entries = valid_entries[:25]

            added_count = 0

            for idx, entry in enumerate(valid_entries):
                if added_count >= MAX_PLAYLIST_SIZE:
                    break

                if not entry:
                    continue

                url = entry.get('url') or entry.get('webpage_url') or entry.get('id')

                if url and not url.startswith('http'):
                    ie_key = entry.get('ie_key', '')
                    if ie_key == 'Youtube' or 'youtube' in (entry.get('extractor', '') or ''):
                        url = f"https://www.youtube.com/watch?v={url}"
                    elif ie_key == 'SoundCloud' or 'soundcloud' in (entry.get('extractor', '') or ''):
                        url = (
                            f"https://soundcloud.com/{url}"
                            if not url.startswith('soundcloud')
                            else f"https://{url}"
                        )

                title = (
                    entry.get('title')
                    or entry.get('track')
                    or entry.get('name')
                    or None
                )

                duration = entry.get('duration', 0)
                thumbnail = entry.get('thumbnail', '')

                if not title:
                    if url:
                        temp_title = url.split('/')[-1].split('?')[0]
                        temp_title = temp_title.replace('-', ' ').replace('_', ' ')[:40]
                        title = f"🎵 {temp_title}..."
                        logging.debug(f"Título temporário criado: {title}")
                    else:
                        title = f"🎵 Música #{idx + 1}"

                song = {
                    'title': title,
                    'url': url,
                    'thumbnail': thumbnail,
                    'duration': self._format_duration(duration),
                    'duration_seconds': duration,
                    'is_lazy': True,
                    'channel': 'Playlist',
                    'user': user,
                }

                self.queue.append(song)
                self._cancel_queue_empty_cleanup()
                added_count += 1

                # Só dispara play_next se add_playlist_async não
                # conseguiu iniciar reprodução E nada está tocando.
                if (
                    not playback_already_started
                    and added_count == 1
                    and not self.is_playback_busy
                ):
                    logging.info(
                        f"✓ Iniciando reprodução tardia via background: {song['title']}"
                    )
                    self.loop.create_task(self.play_next())
                    playback_already_started = True

            logging.info(f"✓ Playlist completa: {added_count} músicas adicionadas à fila")

        except Exception as e:
            logging.error(f"Erro ao processar playlist: {e}")
