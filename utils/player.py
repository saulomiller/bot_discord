"""implementa o player de musica, fila e reproducao com yt-dlp/FFmpeg."""

import asyncio
from collections import deque

import yt_dlp

from utils.player_modules import (
    MAX_PLAYLIST_SIZE,
    YDL_OPTIONS,
    ControlsMixin,
    DashboardMixin,
    ExtractionMixin,
    PlaybackMixin,
    QueueMixin,
    SafeFFmpegPCMAudio,
    SafeFFmpegOpusAudio,
    SoundboardMixin,
    StreamCache,
    build_ffmpeg_options,
)

class MusicPlayer(
    PlaybackMixin,
    SoundboardMixin,
    QueueMixin,
    ExtractionMixin,
    DashboardMixin,
    ControlsMixin,
):
    """Player principal com composicao por mixins especializados."""

    def __init__(self, guild_id, bot):
        """Inicializa a instancia da classe."""
        self.guild_id = guild_id
        self.bot = bot
        self.queue = deque()
        self.current_song = None
        self.volume = 0.5
        self.is_paused = False
        self.is_looping = False
        self.is_shuffling = False
        self.loop = asyncio.get_running_loop()
        
        # Cache de Streams
        self.stream_cache = StreamCache()
        
        # Cache de vídeos que falharam com UNPLAYABLE — evita re-tentativas
        # redundantes na mesma sessão. Resetado quando o player é recriado.
        self._failed_ids: set = set()
        
        # Reutilizar instância do YoutubeDL (Otimização)
        self.ydl = yt_dlp.YoutubeDL(YDL_OPTIONS)

        # Progress tracking
        self.started_at = None
        self.paused_at = None 
        self.total_paused = 0
        
        # Soundboard state
        self.sfx_playing = False
        self.stopped_for_sfx = False
        self.consecutive_errors = 0
        
        # Concurrency safety: Lock para evitar múltiplos play_next simultâneos
        self._play_lock = asyncio.Lock()

        # Dashboard (Card Vivo)
        self.dashboard_message = None
        self.dashboard_context = None # ctx ou interaction
        self.dashboard_task = None
        self.last_img_url = None
        self._last_second = -1  # Rastreador para smart updates (evita recria desnecessária)
        self._queue_empty_cleanup_task = None
        self._queue_empty_grace_seconds = 8

    @property
    def is_voice_busy(self) -> bool:
        """Retorna True quando o voice client já está ocupado (tocando/pausado)."""
        vc = self.voice_client
        return bool(vc and (vc.is_playing() or vc.is_paused()))

    @property
    def is_playback_busy(self) -> bool:
        """Retorna True quando há reprodução ativa ou transição de play em andamento."""
        return self._play_lock.locked() or self.is_voice_busy or self.sfx_playing

    @property
    def guild(self):
        """Executa a rotina de guild."""
        return self.bot.get_guild(self.guild_id)

    @property
    def voice_client(self):
        """Executa a rotina de voice client."""
        return self.guild.voice_client if self.guild else None

    @property
    def is_playing(self) -> bool:
        """Retorna True se estiver tocando áudio."""
        return bool(self.voice_client and self.voice_client.is_playing())

    def _format_duration(self, duration_seconds: int) -> str:
        """Formata duração em segundos para string HH:MM:SS ou MM:SS."""
        if not duration_seconds:
            return "Desconhecida"
        
        minutes, seconds = divmod(int(duration_seconds), 60)
        hours, minutes = divmod(minutes, 60)
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes}:{seconds:02d}"

    @staticmethod
    def _is_direct_stream_url(url: str) -> bool:
        """Detecta URLs diretas de mídia (ex.: googlevideo/videoplayback ou m3u8 playlists)."""
        if not url:
            return False
        lower = str(url).lower()
        return (
            '.googlevideo.com/' in lower
            or 'googlevideo.com/videoplayback' in lower
            or 'sndcdn.com/' in lower
        )

    @staticmethod
    def _is_resolvable_service_url(url: str) -> bool:
        """Detecta páginas canônicas de serviços que devem passar por resolve."""
        if not url:
            return False
        lower = str(url).lower()
        return (
            'youtube.com/watch' in lower
            or 'youtu.be/' in lower
            or 'music.youtube.com/' in lower
            or 'soundcloud.com/' in lower
        )

__all__ = [
    'MAX_PLAYLIST_SIZE',
    'YDL_OPTIONS',
    'MusicPlayer',
    'SafeFFmpegPCMAudio',
    'SafeFFmpegOpusAudio',
    'StreamCache',
    'build_ffmpeg_options',
]
