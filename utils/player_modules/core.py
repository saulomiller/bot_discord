"""Tipos centrais reutilizados pelo player (cache e fonte FFmpeg)."""

import logging
import subprocess
import time
from collections import OrderedDict

import discord

class StreamCache:
    """Cache simples para URLs de stream com TTL, limite de tamanho e limpeza ativa.
    
    Usa time.monotonic() para robustez contra mudanças de clock do sistema."""
    def __init__(self, ttl=600, max_size=100):
        """Inicializa a instancia da classe."""
        self.cache = OrderedDict()
        self.ttl = ttl # 10 minutos
        self.max_size = max_size
        self.insert_count = 0

    def get(self, key):
        """Executa a rotina de get."""
        if key in self.cache:
            data = self.cache[key]
            # Usar monotonic para TTL (robusto ao NTP)
            if time.monotonic() - data['time'] < self.ttl:
                # Move para fim (LRU)
                self.cache.move_to_end(key)
                return data['url']
            else:
                del self.cache[key]
        return None

    def set(self, key, url):
        """Executa a rotina de et."""
        self.insert_count += 1
        
        # Limpeza ativa a cada 50 inserções (Higiene)
        if self.insert_count % 50 == 0:
            self._sweep()

        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = {'url': url, 'time': time.monotonic()}
        
        # Limpar excesso (LRU)
        if len(self.cache) > self.max_size:
            self.cache.popitem(last=False)

    def _sweep(self):
        """Remove itens expirados do cache (usando monotonic)."""
        now = time.monotonic()
        keys_to_remove = [
            k for k, v in self.cache.items()
            if now - v['time'] > self.ttl
        ]
        
        for k in keys_to_remove:
            del self.cache[k]
        
        if keys_to_remove:
            logging.info(f"🧹 Cache Sweep: {len(keys_to_remove)} itens expirados removidos.")

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
                    logging.warning(f"FFmpeg {proc.pid} not terminating, forcing kill.")
                    proc.kill()
            except Exception as e:
                logging.error(f"Error killing FFmpeg process: {e}")
        
        # Chama o cleanup original para fechar pipes
        super().cleanup()
