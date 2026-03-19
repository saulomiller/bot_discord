"""Suporte ? reprodu??o de efeitos de soundboard."""

import asyncio
import logging

from .core import SafeFFmpegPCMAudio


class SoundboardMixin:
    """Comportamentos de soundboard do MusicPlayer."""

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
            current_pos = progress["current"]

            logging.info(
                f"Parando música para SFX. Posição salva: {current_pos}s"
            )

            # Salvar posição na música atual e recolocar no início da fila
            self.current_song["seek"] = current_pos
            self.queue.appendleft(self.current_song)

            # Parar playback atual (acionará after_play, que deve ignorar por causa de stopped_for_sfx)
            self.voice_client.stop()

            # Pequeno delay para garantir que o ffmpeg liberou o áudio
            await asyncio.sleep(0.5)

        # Tocar SFX
        ffmpeg_options = {"options": f'-vn -af "volume={volume}"'}

        def after_sfx(error):
            """Callback após SFX terminar."""
            self.sfx_playing = False

            if self.stopped_for_sfx:
                logging.info("SFX finalizado, retomando música...")
                self.stopped_for_sfx = False

                # Retomar música (fire-and-forget — não bloquear a thread do FFmpeg)
                asyncio.run_coroutine_threadsafe(
                    self.play_next(), self.bot.loop
                )

        try:
            executable = "ffmpeg"
            # USAR SafeFFmpegPCMAudio
            source = SafeFFmpegPCMAudio(
                sfx_path, executable=executable, **ffmpeg_options
            )
            self.voice_client.play(source, after=after_sfx)
            logging.info(f"SFX iniciado: {sfx_path}")
        except Exception as e:
            logging.error(f"Erro ao iniciar SFX: {e}")
            self.sfx_playing = False
            if self.stopped_for_sfx:
                self.stopped_for_sfx = False
                self.loop.create_task(self.play_next())
