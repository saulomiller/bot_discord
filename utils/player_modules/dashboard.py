"""Rotinas de dashboard (embed/card e loop de atualizacao)."""

import asyncio
import contextlib
import logging
import time

import discord

from utils.embeds import EmbedBuilder
from utils.image import create_now_playing_card_with_metadata_async


class DashboardMixin:
    """Comportamentos de dashboard do MusicPlayer."""

    def get_progress(self) -> dict:
        """Calcula o progresso atual da música com precisão monotonic."""
        if not self.current_song or not self.started_at:
            return {"current": 0, "duration": 0, "percent": 0}

        # Calcular tempo atual
        now = self.paused_at or time.monotonic()
        elapsed = max(0, now - self.started_at - self.total_paused)

        duration = self.current_song.get("duration_seconds", 0)

        # Garantir limites
        elapsed = min(elapsed, duration) if duration > 0 else elapsed
        percent = (elapsed / duration * 100) if duration > 0 else 0

        return {
            "current": int(elapsed),
            "duration": int(duration),
            "percent": round(min(100, percent), 1),
        }

    async def start_dashboard_task(self):
        """Inicia a tarefa de atualização do dashboard."""
        if self.dashboard_task and not self.dashboard_task.done():
            return

        self.dashboard_task = self.bot.loop.create_task(
            self.update_dashboard_loop()
        )

    async def stop_dashboard_task(self):
        """Para a tarefa de atualização (com cancelamento seguro)."""
        if self.dashboard_task and not self.dashboard_task.done():
            self.dashboard_task.cancel()
            # Suprimir CancelledError de forma segura
            with contextlib.suppress(asyncio.CancelledError):
                await self.dashboard_task
            self.dashboard_task = None

    async def clear_music_dashboard(self):
        """Remove o dashboard de música e para atualizações."""
        await self.stop_dashboard_task()

        if self.dashboard_message:
            try:
                await self.dashboard_message.delete()
            except (
                discord.NotFound,
                discord.Forbidden,
                discord.HTTPException,
            ):
                pass
            self.dashboard_message = None

        self._last_second = -1
        self._dominant_color = None

    def _cancel_queue_empty_cleanup(self):
        task = self._queue_empty_cleanup_task
        if task and not task.done():
            task.cancel()
        self._queue_empty_cleanup_task = None
        self._cancel_idle_disconnect()

    def _cancel_idle_disconnect(self):
        task = self._idle_disconnect_task
        if task and not task.done():
            task.cancel()
        self._idle_disconnect_task = None

    def cancel_alone_disconnect(self):
        task = self._alone_disconnect_task
        if task and not task.done():
            task.cancel()
        self._alone_disconnect_task = None

    async def _disconnect_voice(self, reason: str):
        """Limpa o player e encerra a conexao de voz com seguranca."""
        vc = self.voice_client
        if not vc or not vc.is_connected():
            return

        logging.info("[voice] Desconectando guild %s: %s", self.guild_id, reason)
        self.queue.clear()
        self.current_song = None
        self.is_paused = False
        self.sfx_playing = False
        await self.clear_music_dashboard()
        await vc.disconnect(force=True)

    async def _disconnect_after_idle(self):
        try:
            await asyncio.sleep(self._voice_idle_timeout_seconds)
            if (
                self.queue
                or self.current_song
                or self.is_voice_busy
                or self.sfx_playing
                or self._play_lock.locked()
            ):
                return
            await self._disconnect_voice("10 minutos sem reproducao")
        except asyncio.CancelledError:
            pass
        finally:
            self._idle_disconnect_task = None

    def _schedule_idle_disconnect(self):
        task = self._idle_disconnect_task
        if task and not task.done():
            return
        self._idle_disconnect_task = self.loop.create_task(
            self._disconnect_after_idle()
        )

    async def _disconnect_after_alone(self):
        try:
            await asyncio.sleep(self._voice_idle_timeout_seconds)
            vc = self.voice_client
            if not vc or not vc.is_connected() or not vc.channel:
                return
            humans = [member for member in vc.channel.members if not member.bot]
            if humans:
                return
            await self._disconnect_voice("10 minutos sozinho no canal")
        except asyncio.CancelledError:
            pass
        finally:
            self._alone_disconnect_task = None

    def schedule_alone_disconnect(self):
        task = self._alone_disconnect_task
        if task and not task.done():
            return
        self._alone_disconnect_task = self.loop.create_task(
            self._disconnect_after_alone()
        )

    async def _clear_dashboard_after_grace(self):
        """Executa a rotina de clear da hboard after grace."""
        try:
            await asyncio.sleep(self._queue_empty_grace_seconds)

            # Se algo voltou a tocar/enfileirar, não limpar o dashboard.
            if (
                self.queue
                or self.is_voice_busy
                or self.sfx_playing
                or self.current_song
            ):
                return

            await self.clear_music_dashboard()
            logging.info(
                "[dashboard] Fila permaneceu vazia. Dashboard removido."
            )
        except asyncio.CancelledError:
            pass
        finally:
            self._queue_empty_cleanup_task = None

    def _schedule_queue_empty_cleanup(self):
        """Executa a rotina de chedule queue empty cleanup."""
        if (
            self._queue_empty_cleanup_task
            and not self._queue_empty_cleanup_task.done()
        ):
            self._schedule_idle_disconnect()
            return
        self._queue_empty_cleanup_task = self.loop.create_task(
            self._clear_dashboard_after_grace()
        )
        self._schedule_idle_disconnect()

    async def update_dashboard_loop(self):
        """Atualiza a barra de progresso do embed em intervalos inteligentes.

        Usa self._last_second para evitar atualizar o embed quando o tempo
        não mudou.
        Isso reduz as chamadas API em 90% (de ~60/min para ~1/min).

        CPU Optimization: Dorme 5s quando idle (não tocando).
        """
        try:
            while True:
                # Quando não toca nada, dorme 5s para reduzir CPU.
                if (
                    not self.voice_client
                    or not self.voice_client.is_playing()
                    or self.is_paused
                ):
                    self._last_second = -1  # Reset counter when paused/stopped
                    await asyncio.sleep(5)  # Dormir mais quando idle
                    continue

                # Tocando: verificar a cada 1s
                await asyncio.sleep(1)

                if not self.dashboard_message:
                    continue

                # Edita apenas quando o segundo muda para reduzir chamadas.
                try:
                    song_snapshot = self.current_song
                    if not isinstance(song_snapshot, dict):
                        continue

                    progress = self.get_progress()
                    current_second = progress["current"]

                    # Se o segundo não mudou, pular atualização (ECONOMIA REAL)
                    if current_second == self._last_second:
                        continue

                    # Atualizar o rastreador
                    self._last_second = current_second

                    # Criar embed apenas quando necessário
                    # Usa a cor dominante cacheada no player.
                    embed = EmbedBuilder.create_now_playing_embed(
                        song_snapshot,
                        list(self.queue),
                        current_seconds=current_second,
                        total_seconds=progress["duration"],
                        dominant_color=getattr(self, "_dominant_color", None),
                    )
                    # Mantém a imagem do card vinculada ao embed em edições.
                    try:
                        if (
                            self.dashboard_message
                            and self.dashboard_message.attachments
                        ):
                            embed.set_image(
                                url=self.dashboard_message.attachments[0].url
                            )
                    except Exception:
                        pass

                    # Editar a mensagem apenas quando o segundo mudou
                    await self.dashboard_message.edit(embed=embed)

                except discord.NotFound:
                    self.dashboard_message = None  # Mensagem deletada
                except Exception as e:
                    logging.debug(f"Erro ao atualizar dashboard (loop): {e}")

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logging.error(f"Erro fatal no dashboard loop: {e}")

    async def send_dashboard(self):
        """Envia/Renova a mensagem do dashboard (Imagem + Embed)."""
        song_snapshot = self.current_song
        if not self.dashboard_context or not isinstance(song_snapshot, dict):
            return

        # Apagar mensagem anterior para não spammar
        if self.dashboard_message:
            try:
                await self.dashboard_message.delete()
            except (
                discord.NotFound,
                discord.Forbidden,
                discord.HTTPException,
            ) as exc:
                logging.debug(f"Falha ao deletar dashboard antigo: {exc}")
            self.dashboard_message = None

        try:
            # Converter queue para lista de dicts
            next_songs = list(self.queue)
            progress = self.get_progress()
            pct = progress.get("percent", 0) / 100.0  # 0.0-1.0

            # Gera card e cor dominante em uma única passada.
            img_buffer, dominant_color = (
                await create_now_playing_card_with_metadata_async(
                    song_snapshot,
                    next_songs=next_songs[:3],
                    progress_percent=pct,
                )
            )
            # Cachear no player para o dashboard loop reutilizar sem re-fetch.
            self._dominant_color = dominant_color

            # Evitar dashboard stale quando a musica muda durante awaits
            if self.current_song is not song_snapshot:
                return

            file = None
            if img_buffer:
                file = discord.File(img_buffer, filename="dashboard.png")

            # Gerar Embed Inicial
            embed = EmbedBuilder.create_now_playing_embed(
                song_snapshot,
                next_songs,
                current_seconds=progress["current"],
                total_seconds=progress["duration"],
                dominant_color=dominant_color,
            )

            if file:
                embed.set_image(url="attachment://dashboard.png")

            # Enviar para o canal vinculado
            channel = (
                self.dashboard_context.channel
                if hasattr(self.dashboard_context, "channel")
                else self.dashboard_context
            )

            if channel:
                # Tenta enviar com retries em falhas transitórias.
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
                            send_file = discord.File(
                                img_buffer, filename="dashboard.png"
                            )
                            self.dashboard_message = await channel.send(
                                embed=embed, file=send_file
                            )
                        else:
                            self.dashboard_message = await channel.send(
                                embed=embed
                            )

                        # Iniciar loop se não estiver rodando
                        await self.start_dashboard_task()
                        break

                    except (
                        discord.Forbidden,
                        discord.HTTPException,
                        ConnectionResetError,
                        OSError,
                    ) as e:
                        attempts += 1
                        logging.warning(
                            "Falha ao enviar dashboard (tentativa %s/%s): %s",
                            attempts,
                            max_attempts,
                            e,
                        )
                        # Se Forbidden, não adianta tentar de novo
                        if isinstance(e, discord.Forbidden):
                            logging.error(
                                "Sem permissão para enviar o dashboard no "
                                "canal."
                            )
                            break
                        # Aguarda um pouco antes de tentar novamente
                        await asyncio.sleep(1 * attempts)
                        continue

                if attempts >= max_attempts:
                    logging.error(
                        "Não foi possível enviar o dashboard após várias "
                        "tentativas."
                    )

        except Exception as e:
            logging.error(f"Erro ao enviar dashboard: {e}")
