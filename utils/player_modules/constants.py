"""Constantes e opcoes usadas pelo sistema de playback."""

YDL_OPTIONS = {
    # Prioriza HLS (m3u8) quando disponível, reduzindo chances de 403 por GVS/PO-token.
    'format': 'bestaudio[protocol*=m3u8]/bestaudio/best',
    'quiet': False,  # Habilitar logs para debug
    'verbose': True, # Verbose explícito
    'noplaylist': False,  # Permitir playlists
    'playlistend': 100,  # Limitar a 100 músicas por playlist
    'socket_timeout': 15,
    'retries': 5,
    'skip_download': True,
    'source_address': '0.0.0.0',
    'cachedir': '/app/.cache',
    'ignoreerrors': True,   # Não abortar em entradas inválidas de playlist
    'extract_flat': False,  # Resolver URLs completas por padrão
    # Permite download automático dos scripts EJS (necessário para web_embedded/web)
    # Precisa ser lista/set, não string; string gera warning de componentes por caractere.
    'remote_components': ['ejs:github'],
    
    # Evita cliente tv (pode cair em DRM total) e prioriza web_safari (HLS),
    # que costuma funcionar melhor sem PO Token.
    'extractor_args': {
        'youtube': {
            'player_client': ['web_safari', 'web', 'mweb'],
        }
    },
}

MAX_PLAYLIST_SIZE = 100  # Limite rígido (Check 4 - User Feedback)
