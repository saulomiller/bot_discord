"""Constantes e opcoes usadas pelo sistema de playback."""

YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'quiet': False,  # Habilitar logs para debug
    'verbose': True, # Verbose explícito
    'noplaylist': False,  # Permitir playlists
    'playlistend': 100,  # Limitar a 100 músicas por playlist
    'socket_timeout': 15,
    'retries': 5,
    'skip_download': True,
    'source_address': '0.0.0.0',
    'cachedir': '/app/.cache',
    'geo_bypass': True,
    'geo_bypass_country': 'US',
    'ignoreerrors': True,   # Não abortar em entradas inválidas de playlist
    'extract_flat': False,  # Resolver URLs completas por padrão
    # Permite download automático dos scripts EJS (necessário para web_embedded/web)
    # Precisa ser lista/set, não string; string gera warning de componentes por caractere.
    'remote_components': ['ejs:github'],
    
    # web_embedded: cliente mais estável com EJS (não requer PO Token para a maioria dos vídeos)
    # web: fallback padrão
    'extractor_args': {
        'youtube': {
            'player_client': ['web_embedded', 'web'],
        }
    },
}

MAX_PLAYLIST_SIZE = 100  # Limite rígido (Check 4 - User Feedback)
