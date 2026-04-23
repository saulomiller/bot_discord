"""Tipos centrais reutilizados pelo player (cache e fonte FFmpeg)."""

import logging
import subprocess
import time
from collections import OrderedDict

import discord


class StreamCache:
    """Cache simples para URLs de stream com TTL e limpeza ativa.

    Usa ``time.monotonic()`` para robustez contra mudanças de clock do sistema.
    """

    def __init__(self, ttl=600, max_size=100):
        """Inicializa a instancia da classe."""
        self.cache = OrderedDict()
        self.ttl = ttl  # 10 minutos
        self.max_size = max_size
        self.insert_count = 0

    def get(self, key):
        """Retorna o entry completo do cache.

        Retornar o dict inteiro em vez de só 'url' garante que metadados
        como acodec e format_id fiquem disponíveis para detecção de Opus
        em replays/loops.
        """
        if key in self.cache:
            data = self.cache[key]
            # Usar monotonic para TTL (robusto ao NTP)
            if time.monotonic() - data["time"] < self.ttl:
                # Move para fim (LRU)
                self.cache.move_to_end(key)
                return data["value"]
            else:
                del self.cache[key]
        return None

    def set(self, key, value):
        """Armazena um entry no cache com timestamp monotonic.

        Args:
            key: chave de lookup (normalmente a URL original).
            value: dict com url, headers, acodec, format_id, etc.

        """
        self.insert_count += 1

        # Limpeza ativa a cada 50 inserções (Higiene)
        if self.insert_count % 50 == 0:
            self._sweep()

        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = {"value": value, "time": time.monotonic()}

        # Limpar excesso (LRU)
        if len(self.cache) > self.max_size:
            self.cache.popitem(last=False)

    def _sweep(self):
        """Remove itens expirados do cache (usando monotonic)."""
        now = time.monotonic()
        keys_to_remove = [
            k for k, v in self.cache.items() if now - v["time"] > self.ttl
        ]

        for k in keys_to_remove:
            del self.cache[k]

        if keys_to_remove:
            logging.info(
                "🧹 Cache Sweep: %s itens expirados removidos.",
                len(keys_to_remove),
            )


class SafeFFmpegPCMAudio(discord.FFmpegPCMAudio):
    """FFmpegPCMAudio com cleanup robusto para evitar processos zumbis."""

    def cleanup(self):
        """Executa a rotina de cleanup."""
        proc = self._process
        if proc:
            try:
                logging.info(f"Killing FFmpeg process {proc.pid}...")
                proc.terminate()
                try:
                    proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    logging.warning(
                        f"FFmpeg {proc.pid} not terminating, forcing kill."
                    )
                    proc.kill()
            except Exception as e:
                logging.error(f"Error killing FFmpeg process: {e}")
            # Fechar pipes explicitamente para evitar leak em casos extremos
            try:
                if proc.stdout:
                    proc.stdout.close()
                if proc.stderr:
                    proc.stderr.close()
            except Exception:
                pass

        # Chama o cleanup original para fechar pipes
        super().cleanup()


class SafeFFmpegOpusAudio(discord.FFmpegOpusAudio):
    """FFmpegOpusAudio com cleanup robusto para evitar processos zumbis."""

    def cleanup(self):
        """Executa a rotina de cleanup."""
        proc = self._process
        if proc:
            try:
                logging.info(f"Killing FFmpeg process {proc.pid} (OPUS)...")
                proc.terminate()
                try:
                    proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    logging.warning(
                        "FFmpeg %s (OPUS) not terminating, forcing kill.",
                        proc.pid,
                    )
                    proc.kill()
            except Exception as e:
                logging.error(f"Error killing FFmpeg process: {e}")
            # Fechar pipes explicitamente para evitar leak em casos extremos
            try:
                if proc.stdout:
                    proc.stdout.close()
                if proc.stderr:
                    proc.stderr.close()
            except Exception:
                pass

        # Chama o cleanup original para fechar pipes
        super().cleanup()


def _detect_opus(info_dict: dict) -> bool:
    """Detecta se a stream de áudio é Opus usando múltiplas heurísticas.

    YouTube moderno (HLS/SABR/m3u8) nem sempre retorna 'acodec' corretamente,
    então usamos fallbacks:
      1. acodec contém 'opus'
      2. format_id é 249/250/251 (formatos Opus padrão do YouTube)
      3. URL do stream contém '.webm' ou '.opus'
    """
    acodec = (info_dict.get("acodec") or "").lower()
    if acodec and acodec != "none" and "opus" in acodec:
        return True

    # format_ids 249/250/251 = YouTube Opus (baixa/média/alta qualidade)
    format_id = str(info_dict.get("format_id", ""))
    if format_id in ("249", "250", "251"):
        return True

    # .webm ou .opus em URL → quase sempre Opus
    # Verificar tanto stream_url (URL resolvida) quanto url (original)
    stream_url = info_dict.get("stream_url", "") or ""
    url = info_dict.get("url", "") or ""
    if any(ext in stream_url for ext in (".webm", ".opus")):
        return True
    if any(ext in url for ext in (".webm", ".opus")):
        return True

    return False


def build_ffmpeg_options(
    info_dict: dict,
    volume: float,
    force_fallback: str = None,
    seek_position: float = 0,
) -> dict:
    """Constrói opções do FFmpeg otimizadas verificando o codec.

    Retorna dict com:
      - 'options': string de output options para FFmpeg
      - 'is_opus': bool indicando se a fonte é Opus nativo
        para usar codec='copy' no FFmpegOpusAudio
      - 'mode': string descritiva do modo escolhido

    IMPORTANTE: NÃO inclui -c:a no 'options' pois FFmpegOpusAudio já gerencia
    o codec internamente via seu parâmetro 'codec'. Passar -c:a aqui causa
    o warning 'Multiple -codec options specified' do FFmpeg.
    """
    acodec = (info_dict.get("acodec") or "").lower()
    is_opus = _detect_opus(info_dict)

    if force_fallback == "encode_opus":
        logging.info(
            "[audio] codec=%s | is_opus=%s | mode=encode_opus "
            "(fallback) | seek=%s",
            acodec,
            is_opus,
            seek_position,
        )
        return {
            "options": (
                f'-vn -vbr on -compression_level 10 -af "volume={volume}"'
            ),
            "is_opus": False,
            "mode": "encode_opus",
        }

    if force_fallback == "encode_pcm":
        logging.info(
            "[audio] codec=%s | is_opus=%s | mode=encode_pcm "
            "(fallback) | seek=%s",
            acodec,
            is_opus,
            seek_position,
        )
        return {
            "options": f'-vn -b:a 192k -af "volume={volume}"',
            "is_opus": False,
            "mode": "encode_pcm",
        }

    if is_opus and abs(volume - 1.0) < 0.01:
        # Modo copy: volume == 1.0, sem necessidade de -af volume.
        # FFmpegOpusAudio produz pacotes Opus diretos → zero re-encode.
        logging.info(
            "[audio] codec=%s | is_opus=True | mode=copy | seek=%s",
            acodec,
            seek_position,
        )
        return {
            "options": "-vn",
            "is_opus": True,
            "mode": "copy",
        }
    elif is_opus:
        # Opus nativo mas volume != 1.0 → precisa de -af, então encode.
        logging.info(
            "[audio] codec=%s | is_opus=True | mode=encode_opus "
            "(volume=%s) | seek=%s",
            acodec,
            volume,
            seek_position,
        )
        return {
            "options": (
                f'-vn -vbr on -compression_level 10 -af "volume={volume}"'
            ),
            "is_opus": False,
            "mode": "encode_opus",
        }
    else:
        logging.info(
            "[audio] codec=%s | is_opus=False | mode=encode_opus | seek=%s",
            acodec,
            seek_position,
        )
        return {
            "options": (
                f'-vn -vbr on -compression_level 10 -af "volume={volume}"'
            ),
            "is_opus": False,
            "mode": "encode_opus",
        }
