"""Suporte à reprodução de efeitos de soundboard."""

import asyncio
import logging

from .core import SafeFFmpegPCMAudio, SafeFFmpegOpusAudio, build_ffmpeg_options

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
            # Compensar pipeline_delay/buffer interno do FFmpeg para evitar
            # micro "pulo" na retomada
            current_pos = max(0, progress['current'] - 0.2)
            
            logging.info(f"Parando música para SFX. Posição salva: {current_pos}s")
            
            # Salvar posição na música atual e recolocar no início da fila
            self.current_song['seek'] = current_pos
            self.queue.appendleft(self.current_song)
            
            # Parar playback atual (acionará after_play, que deve ignorar por causa de stopped_for_sfx)
            self.voice_client.stop()
            
            # Aguardar o player realmente parar (polling rápido em vez de delay fixo)
            for _ in range(20):  # máximo ~1s
                if not self.voice_client.is_playing():
                    break
                await asyncio.sleep(0.05)
        
        # Detectar se o SFX local é Opus nativo para usar copy (zero CPU)
        is_opus_sfx = sfx_path.lower().endswith((".ogg", ".opus", ".webm"))
        
        if is_opus_sfx and abs(volume - 1.0) < 0.01:
            # Copy direto: sem re-encode, volume padrão
            sfx_codec = "copy"
            sfx_options = "-vn"
            logging.info(f"[sfx] mode=copy | path={sfx_path}")
        else:
            # Encode com volume ajustado
            sfx_result = build_ffmpeg_options(
                {"acodec": "pcm"},
                volume,
                force_fallback="encode_opus",
            )
            sfx_codec = "libopus"
            sfx_options = sfx_result["options"]
            logging.info(f"[sfx] mode=encode_opus | volume={volume} | path={sfx_path}")

        ffmpeg_options = {
            'options': sfx_options
        }
        
        def after_sfx(error):
            """Callback após SFX terminar."""
            try:
                if error:
                    logging.error(f"SFX error: {error}")
                
                if self.stopped_for_sfx:
                    logging.info("SFX finalizado, retomando música...")
                    self.stopped_for_sfx = False
                    
                    # Retomar música (fire-and-forget — não bloquear a thread do FFmpeg)
                    asyncio.run_coroutine_threadsafe(self.play_next(), self.bot.loop)
            finally:
                # Garantir que sfx_playing é resetado mesmo em caso de erro
                self.sfx_playing = False

        try:
            executable = 'ffmpeg'
            # USAR SafeFFmpegOpusAudio com Fallback PCM
            try:
                source = SafeFFmpegOpusAudio(sfx_path, codec=sfx_codec, executable=executable, **ffmpeg_options)
            except Exception as opus_err:
                logging.warning(f"Fallback para PCM no Soundboard devido a falha Opus: {opus_err}")
                source = SafeFFmpegPCMAudio(sfx_path, executable=executable, **ffmpeg_options)
                
            self.voice_client.play(source, after=after_sfx)
            logging.info(f"SFX iniciado: {sfx_path}")
        except Exception as e:
            logging.error(f"Erro ao iniciar SFX: {e}")
            self.sfx_playing = False
            if self.stopped_for_sfx:
                self.stopped_for_sfx = False
                self.loop.create_task(self.play_next())
