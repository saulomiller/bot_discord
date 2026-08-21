"""Constantes e opcoes usadas pelo sistema de playback."""

YDL_OPTIONS = {
    "format": "bestaudio/best",
    "quiet": False,  # Habilitar logs para debug
    "verbose": True,  # Verbose explícito
    "noplaylist": False,  # Permitir playlists
    "playlistend": 100,  # Limitar a 100 músicas por playlist
    "socket_timeout": 15,
    "retries": 5,
    "skip_download": True,
    "source_address": "0.0.0.0",  # Força IPv4 no yt-dlp
    "force_ipv4": True,  # Redundância extra para garantir IPv4
    "cachedir": "/app/.cache",
    "ignoreerrors": True,  # Não abortar em entradas inválidas de playlist
    "extract_flat": False,  # Resolver URLs completas por padrão
    # Permite baixar scripts EJS necessários para clientes web.
    "remote_components": {"ejs:github"},
    "extractor_args": {
        "youtube": {
            # visionos é o cliente primário: no ambiente de produção ele
            # fornece streams de áudio sem exigir PO Token.
            "player_client": ["visionos"],
        }
    },
}

YDL_FALLBACK_CLIENTS = [
    ["tv"],
    ["android_vr"],
    ["web_embedded"],
]

MAX_PLAYLIST_SIZE = 100  # Limite rígido (Check 4 - User Feedback)
