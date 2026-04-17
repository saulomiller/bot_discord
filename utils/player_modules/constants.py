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
    # Permite baixar scripts EJS necessários para web_embedded/web.
    "remote_components": {"ejs:github"},
    "extractor_args": {
        "youtube": {
            "player_client": ["web", "default"],
        }
    },
}

YDL_FALLBACK_CLIENTS = [
    ["ios", "tv_embedded"],
    ["android", "tv_embedded"],
    ["tv_embedded"],
    ["web_creator"],
]

MAX_PLAYLIST_SIZE = 100  # Limite rígido (Check 4 - User Feedback)
