"""Extra??o de metadados de ?udio via yt-dlp."""

import logging

class ExtractionMixin:
    """Comportamentos de extra??o do MusicPlayer."""

    async def extract_info(self, search, max_entries=None):
        """Extrai informações do YouTube/SoundCloud.
        
        Args:
            search: URL ou termo de busca
            max_entries: Número máximo de entradas a extrair (None = todas)
        
        Retorna lista de tuplas: [(title, url, thumbnail, duration, channel, duration_seconds), ...]
        """
        def run() -> list:
            # Reusar self.ydl ao invés de criar nova instância (economiza RAM/tempo)
            info = None
            entries = []
            
            if search.startswith(('http://', 'https://')):
                # URL direta - pode ser música única ou playlist
                info = self.ydl.extract_info(search, download=False)
                if not info:
                    raise ValueError("yt-dlp retornou None para a URL fornecida.")
                # Verificar se é playlist
                if 'entries' in info:
                    entries = list(info['entries'])
                else:
                    entries = [info]
                    
            elif search.startswith(('scsearch:', 'ytsearch:')):
                # Pesquisa explícita
                info = self.ydl.extract_info(search, download=False)
                entries = info.get('entries', [])
            else:
                # Padrão: Pesquisa do YouTube (apenas primeiro resultado)
                info = self.ydl.extract_info(f"ytsearch:{search}", download=False)
                entries = info.get('entries', [])
            
            if not entries:
                raise ValueError("Nenhum resultado encontrado.")
            
            # Filtrar entradas None
            entries = [e for e in entries if e is not None]
            
            # Limitar número de entradas se especificado
            if max_entries is not None:
                entries = entries[:max_entries]
            
            # Processar todas as entradas
            results = []
            for entry in entries:
                if not entry:  # Pular entradas vazias
                    continue
                
                try:
                    title = entry.get('title', 'Desconhecido')
                    # Priorizar URL canônica para evitar salvar stream efêmero (googlevideo).
                    webpage_url = entry.get('webpage_url') or entry.get('original_url')
                    url = webpage_url or entry.get('url', '')
                    url = str(url) if url else ''

                    if url and not url.startswith('http'):
                        ie_key = str(entry.get('ie_key', '')).lower()
                        extractor = str(entry.get('extractor', '')).lower()
                        if ie_key == 'youtube' or 'youtube' in extractor:
                            url = f"https://www.youtube.com/watch?v={url}"
                        elif ie_key == 'soundcloud' or 'soundcloud' in extractor:
                            url = f"https://soundcloud.com/{url}" if not url.startswith('soundcloud') else f"https://{url}"

                    # Blindagem extra: se ainda vier URL direta de stream e houver webpage_url, usar webpage_url.
                    if self._is_direct_stream_url(url) and webpage_url:
                        url = str(webpage_url)
                    thumbnail = entry.get('thumbnail', '')
                    
                    duration_seconds = entry.get('duration', 0)
                    if duration_seconds:
                        minutes, seconds = divmod(duration_seconds, 60)
                        hours, minutes = divmod(minutes, 60)
                        duration_formatted = f"{int(hours)}:{int(minutes):02d}:{int(seconds):02d}" if hours > 0 else f"{int(minutes)}:{int(seconds):02d}"
                    else:
                        duration_formatted = "Desconhecida"
                    
                    channel = entry.get('uploader', entry.get('channel', 'Desconhecido'))
                    results.append((title, url, thumbnail, duration_formatted, channel, duration_seconds))
                except Exception as e:
                    # Log mas não interrompe o processamento
                    logging.warning(f"Erro ao processar entrada da playlist: {e}")
                    continue
            
            return results

        return await self.loop.run_in_executor(None, run)
