"""Controles diretos de reprodu??o (stop/skip/pause/resume/volume)."""

import time

class ControlsMixin:
    """Controles de sess?o do MusicPlayer."""

    def stop(self):
        """Executa a rotina de top."""
        self._cancel_queue_empty_cleanup()
        self.queue.clear()
        self.current_song = None
        self._last_second = -1  # Reset contador de atualização
        # Limpar embeds/dashboard em background.
        self.loop.create_task(self.clear_music_dashboard())
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()

    def skip(self):
        """Executa a rotina de kip."""
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()

    def pause(self):
        """Executa a rotina de pau e."""
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.pause()
            self.is_paused = True

            if not self.paused_at:
                self.paused_at = time.monotonic()

    def resume(self):
        """Executa a rotina de re ume."""
        if self.voice_client and self.voice_client.is_paused():
            self.voice_client.resume()
            self.is_paused = False

            if self.paused_at:
                self.total_paused += time.monotonic() - self.paused_at
                self.paused_at = None

    def set_volume(self, volume):
        """Define o volume. Aceita 0.0 a 1.5 (acima de 1.0 = amplificação)."""
        self.volume = max(0.0, min(1.5, volume))
