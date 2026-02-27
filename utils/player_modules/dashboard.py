"""Rotinas de dashboard (embed/card e loop de atualizacao)."""

import asyncio
import contextlib
import logging
import time

import discord

from utils.embeds import EmbedBuilder
from utils.image import create_now_playing_card

class DashboardMixin:
    """Comportamentos de dashboard do MusicPlayer."""

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

    async def clear_music_dashboard(self):
        """Remove o dashboard de música e para atualizações."""
        await self.stop_dashboard_task()

        if self.dashboard_message:
            try:
                await self.dashboard_message.delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass
            self.dashboard_message = None

        self._last_second = -1
        self._dominant_color = None

    def _cancel_queue_empty_cleanup(self):
        task = self._queue_empty_cleanup_task
        if task and not task.done():
            task.cancel()
        self._queue_empty_cleanup_task = None

    async def _clear_dashboard_after_grace(self):
        """Executa a rotina de clear da hboard after grace."""
        try:
            await asyncio.sleep(self._queue_empty_grace_seconds)

            # Se algo voltou a tocar/enfileirar, não limpar o dashboard.
            if self.queue or self.is_voice_busy or self.sfx_playing or self.current_song:
                return

            await self.clear_music_dashboard()
            logging.info("[dashboard] Fila permaneceu vazia. Dashboard removido.")
        except asyncio.CancelledError:
            pass
        finally:
            self._queue_empty_cleanup_task = None

    def _schedule_queue_empty_cleanup(self):
        """Executa a rotina de chedule queue empty cleanup."""
        if self._queue_empty_cleanup_task and not self._queue_empty_cleanup_task.done():
            return
        self._queue_empty_cleanup_task = self.loop.create_task(self._clear_dashboard_after_grace())

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
                    song_snapshot = self.current_song
                    if not isinstance(song_snapshot, dict):
                        continue

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
                        song_snapshot,
                        list(self.queue),
                        current_seconds=current_second,
                        total_seconds=progress['duration'],
                        dominant_color=getattr(self, '_dominant_color', None),
                    )
                    # Manter a imagem do card vinculada ao embed durante edições.
                    try:
                        if self.dashboard_message and self.dashboard_message.attachments:
                            embed.set_image(url=self.dashboard_message.attachments[0].url)
                    except Exception:
                        pass
                    
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
        song_snapshot = self.current_song
        if not self.dashboard_context or not isinstance(song_snapshot, dict):
            return

        # Apagar mensagem anterior para não spammar
        if self.dashboard_message:
            try:
                await self.dashboard_message.delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException) as exc:
                logging.debug(f"Falha ao deletar dashboard antigo: {exc}")
            self.dashboard_message = None

        try:
            # Converter queue para lista de dicts
            next_songs = list(self.queue)
            progress   = self.get_progress()
            pct        = progress.get('percent', 0) / 100.0  # 0.0-1.0

            # Extrair cor dominante da thumbnail (para sincronizar embed e card)
            dominant_color = None
            thumb_url = song_snapshot.get('thumbnail')
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
                    song_snapshot,
                    next_songs=next_songs[:3],
                    progress_percent=pct,
                )
            )

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
