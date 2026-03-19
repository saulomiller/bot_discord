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
            logging.info(
                f"[add_to_queue] Extraído {len(info_list)} resultado(s)"
            )
            # info_list = [(title, url, thumbnail, duration, channel), ...]

            if not info_list:
                raise ValueError("Nenhuma música encontrada.")

            # Pegar apenas a primeira música
            info = info_list[0]
            # Garantir duration_seconds disponível (info é tupla retornada por extract_info)
            duration_seconds = info[5] if len(info) > 5 else 0
            song = {
                "title": info[0],
                "url": info[1],
                "thumbnail": info[2],
                "duration": info[3],
                "duration_seconds": duration_seconds,
                "channel": info[4],
                "user": user,
            }
            self.queue.append(song)
            self._cancel_queue_empty_cleanup()
            logging.info(
                f"[add_to_queue] Música adicionada à fila: {song['title']}"
            )
            logging.info(
                f"[add_to_queue] Tamanho da fila agora: {len(self.queue)}"
            )
            return song
        except Exception as e:
            logging.error(f"Erro ao adicionar música: {e}")
            raise e

    async def add_playlist_async(
        self, search: str, user: discord.Member
    ) -> dict:
        """Adiciona playlist de forma OTIMIZADA.

        1. Busca a PRIMEIRA música imediatamente e toca.
        2. Inicia o processamento do RESTO da playlist em background.
        """
        try:
            logging.info(
                f"🎵 Iniciando processamento OTIMIZADO de playlist: {search}"
            )

            # PASSO 1: Pegar APENAS a primeira música rapidamente
            logging.info("⚡ Buscando primeira música da playlist...")
            # Usar opções temporárias para extração rápida da primeira entrada
            flat_first_opts = {
                **YDL_OPTIONS,
                "extract_flat": "in_playlist",
                "playlistend": 1,
                "ignoreerrors": True,
            }
            first_info = await self.loop.run_in_executor(
                None,
                lambda: yt_dlp.YoutubeDL(flat_first_opts).extract_info(
                    search, download=False
                ),
            )

            first_song_title = "Playlist em processamento..."

            # Se conseguiu extrair algo
            if first_info and "entries" in first_info:
                entries = list(first_info["entries"])
                if entries:
                    first_entry = entries[0]
                    if first_entry:
                        # Adicionar a primeira música à fila IMEDIATAMENTE
                        # Precisamos resolver a URL real se for flat?
                        # Sim, mas o add_to_queue lida com isso se for URL.
                        # No caso de extract_flat='in_playlist', entries são dicts com url e title.

                        # Criar objeto música manual para evitar double-fetch
                        song = {
                            "title": first_entry.get("title", "Desconhecido"),
                            "url": first_entry.get("url"),
                            "thumbnail": None,  # Resolvemos depois/lazy
                            "duration": first_entry.get("duration_string"),
                            "duration_seconds": first_entry.get("duration"),
                            "channel": "Playlist",
                            "user": user,
                            "is_lazy": True,  # Indicar que precisa resolver stream
                        }
                        self.queue.append(song)
                        self._cancel_queue_empty_cleanup()
                        first_song_title = song["title"]
                        logging.info(
                            f"✓ Primeira música adicionada: {first_song_title}"
                        )

                        # Se não estiver tocando, tocar AGORA
                        if not self.is_playback_busy:
                            await self.play_next()

            # PASSO 2: Processar o RESTO em background (começando do índice 2, pois índice 1 já foi adicionado)
            asyncio.create_task(
                self._process_remaining_playlist(search, user, start_index=2)
            )

            # Retornar info genérica
            return {
                "title": f"Playlist: {first_song_title}...",
                "url": search,
                "thumbnail": "",
                "duration": "...",
                "channel": "Playlist",
                "user": user,
            }

        except Exception as e:
            logging.error(f"Erro ao adicionar playlist async: {e}")
            raise e

    async def _process_remaining_playlist(self, search, user, start_index=1):
        """Processa o RESTANTE da playlist em segundo plano."""
        try:
            logging.info(
                f"🎵 Processando restante da playlist (iniciando em {start_index})..."
            )

            # PASSO 1: Extrair URLs RAPIDAMENTE com extract_flat
            # Herdar YDL_OPTIONS para manter geo_bypass, cachedir, etc.
            flat_opts = {
                **YDL_OPTIONS,
                "extract_flat": "in_playlist",
                "playliststart": start_index,
                "playlistend": MAX_PLAYLIST_SIZE,
                "ignoreerrors": True,
            }

            logging.info(
                f"⚡ Extraindo URLs da playlist (max {MAX_PLAYLIST_SIZE})..."
            )

            # Executar em thread para não bloquear
            playlist_info = await self.loop.run_in_executor(
                None,
                lambda: yt_dlp.YoutubeDL(flat_opts).extract_info(
                    search, download=False
                ),
            )

            if not playlist_info:
                logging.error("Nenhuma informação de playlist encontrada")
                return

            # Obter lista de entradas
            entries = playlist_info.get("entries", [])
            if not entries:
                logging.error("Playlist vazia")
                return

            # Filtrar entradas None ou inválidas antes da contagem real
            valid_entries = [e for e in entries if e is not None]

            total_tracks = len(valid_entries)
            logging.info(
                f"✓ {total_tracks} músicas válidas encontradas na playlist"
            )

            # Debug: Logar primeiras entradas para verificar se parecem corretas
            if valid_entries:
                logging.debug(
                    f"Primeira entrada: {valid_entries[0].get('title')} ({valid_entries[0].get('url')})"
                )
                logging.debug(
                    f"Última entrada: {valid_entries[-1].get('title')}"
                )

            # Detecção de Mix do YouTube (Geralmente começa com RD... e tem muitas músicas)
            # Se for um Mix e o usuário esperava uma playlist pequena, isso explica os 99 itens.
            if "RD" in search or "list=RD" in search:
                logging.warning(
                    "Detectado YouTube MIX (Lista infinita). Limitando a 25 músicas para evitar spam."
                )
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
                url = (
                    entry.get("url")
                    or entry.get("webpage_url")
                    or entry.get("id")
                )

                # Reconstruir URL se for apenas ID
                if url and not url.startswith("http"):
                    ie_key = entry.get("ie_key", "")
                    if ie_key == "Youtube" or "youtube" in (
                        entry.get("extractor", "") or ""
                    ):
                        url = f"https://www.youtube.com/watch?v={url}"
                    elif ie_key == "SoundCloud" or "soundcloud" in (
                        entry.get("extractor", "") or ""
                    ):
                        url = (
                            f"https://soundcloud.com/{url}"
                            if not url.startswith("soundcloud")
                            else f"https://{url}"
                        )

                # Tentar pegar título de MÚLTIPLAS chaves
                title = (
                    entry.get("title")
                    or entry.get("track")
                    or entry.get("name")
                    or None  # Será resolvido depois se None
                )

                duration = entry.get("duration", 0)
                thumbnail = entry.get("thumbnail", "")

                # Se NÃO tem título (comum em SoundCloud flat), usar URL como temporário
                # O título real será obtido quando a música for tocar (lazy resolve)
                if not title:
                    # Usar parte da URL como título temporário
                    if url:
                        # Extrair algo legível da URL
                        temp_title = url.split("/")[-1].split("?")[0]
                        # Limitar tamanho e limpar
                        temp_title = temp_title.replace("-", " ").replace(
                            "_", " "
                        )[:40]
                        title = f"🎵 {temp_title}..."
                        logging.debug(f"Título temporário criado: {title}")
                    else:
                        title = f"🎵 Música #{idx + 1}"

                song = {
                    "title": title,
                    "url": url,
                    "thumbnail": thumbnail,
                    "duration": self._format_duration(duration),
                    "duration_seconds": duration,
                    "is_lazy": True,  # IMPORTANTE: Será resolvido no play_next
                    "channel": "Playlist",
                    "user": user,
                }

                self.queue.append(song)
                self._cancel_queue_empty_cleanup()
                added_count += 1

                # Iniciar reprodução assim que a primeira música estiver pronta
                if not first_song_added:
                    first_song_added = True
                    logging.info(
                        f"✓ Primeira música da playlist pronta: {song['title']}"
                    )
                    if not self.is_playback_busy:
                        self.loop.create_task(self.play_next())

            logging.info(
                f"✓ Playlist completa: {added_count} músicas adicionadas à fila"
            )

        except Exception as e:
            logging.error(f"Erro ao processar playlist: {e}")
