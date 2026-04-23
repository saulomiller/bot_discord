"""centraliza a montagem de embeds e feedback visual do bot."""

import logging
import discord
from utils.i18n import t

log = logging.getLogger(__name__)


def _parse_color(color) -> discord.Color:
    """
    Converte qualquer representação de cor para discord.Color.

    Aceita: tuple/list (r,g,b), str hex '#RRGGBB', discord.Color, int.
    Retorna COLOR_MUSIC como fallback.
    """
    try:
        if isinstance(color, discord.Color):
            return color
        if isinstance(color, int):
            return discord.Color(color)
        if isinstance(color, (tuple, list)) and len(color) >= 3:
            r, g, b = int(color[0]), int(color[1]), int(color[2])
            # Clamp para evitar ValueError no discord.py
            r, g, b = (
                max(0, min(255, r)),
                max(0, min(255, g)),
                max(0, min(255, b)),
            )
            return discord.Color.from_rgb(r, g, b)
        if isinstance(color, str):
            hexc = color.lstrip("#")
            if len(hexc) == 6:
                r = int(hexc[0:2], 16)
                g = int(hexc[2:4], 16)
                b = int(hexc[4:6], 16)
                return discord.Color.from_rgb(r, g, b)
    except Exception as e:
        log.debug(f"Falha ao converter cor: {e} (valor: {color!r})")
    return EmbedBuilder.COLOR_MUSIC


class EmbedBuilder:
    """Classe para criar embeds padronizados e compactos."""

    # Paleta de cores padronizada
    COLOR_SUCCESS = discord.Color.from_rgb(87, 242, 135)  # Verde
    COLOR_ERROR = discord.Color.from_rgb(255, 107, 107)  # Vermelho
    COLOR_INFO = discord.Color.from_rgb(116, 185, 255)  # Azul
    COLOR_WARNING = discord.Color.from_rgb(255, 195, 113)  # Laranja
    COLOR_MUSIC = discord.Color.from_rgb(147, 112, 219)  # Roxo
    COLOR_RADIO = discord.Color.from_rgb(255, 154, 162)  # Rosa

    # ------------------------------------------------------------------ #
    # Helpers internos                                                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _format_time(seconds: float) -> str:
        """Formata segundos em HH:MM:SS ou MM:SS."""
        seconds = max(0, int(seconds))
        mins, secs = divmod(seconds, 60)
        hours, mins = divmod(mins, 60)
        if hours > 0:
            return f"{hours}:{mins:02d}:{secs:02d}"
        return f"{mins}:{secs:02d}"

    # ------------------------------------------------------------------ #
    # Barra de progresso                                                   #
    # ------------------------------------------------------------------ #

    @staticmethod
    def create_progress_bar(
        current_seconds: float, total_seconds: float, bar_length: int = 18
    ) -> str:
        """Cria barra ASCII para evitar problemas de encoding."""
        bar_length = max(6, int(bar_length))
        current_time = EmbedBuilder._format_time(current_seconds)

        if total_seconds <= 0:
            return f"`{'-' * bar_length}`  **{current_time}** / ??:??"

        percent = max(0.0, min(1.0, current_seconds / total_seconds))
        total_time = EmbedBuilder._format_time(total_seconds)
        cursor_pos = min(
            bar_length - 1, int(round(percent * (bar_length - 1)))
        )

        bar_chars = []
        for i in range(bar_length):
            if i < cursor_pos:
                bar_chars.append("=")
            elif i == cursor_pos:
                bar_chars.append("o")
            else:
                bar_chars.append("-")
        bar = "".join(bar_chars)

        return f"`{bar}`  **{current_time}** / {total_time}"

    # ------------------------------------------------------------------ #
    # Now Playing                                                          #
    # ------------------------------------------------------------------ #

    @staticmethod
    def create_now_playing_embed(
        song_info: dict | None,
        queue_list: list | None = None,
        current_seconds: float = 0,
        total_seconds: float = 0,
        color=None,
        dominant_color=None,
    ) -> discord.Embed:
        """
        Cria embed compacto para musica tocando.

        Args:
            song_info: Dicionario com dados da musica.
            queue_list: Lista de musicas na fila (opcional).
            current_seconds: Posicao atual em segundos.
            total_seconds: Duracao total em segundos.
            color: Cor explicita (sobrescreve dominant_color).
            dominant_color: Cor dominante extraida da thumbnail (tuple RGB).

        """
        if queue_list is None:
            queue_list = []
        if not isinstance(song_info, dict):
            song_info = {}

        # Resolucao de cor: color explicita > dominant_color > padrao
        if color is not None:
            embed_color = _parse_color(color)
        elif dominant_color is not None:
            embed_color = _parse_color(dominant_color)
        else:
            embed_color = EmbedBuilder.COLOR_MUSIC

        embed = discord.Embed(color=embed_color)

        progress_bar = EmbedBuilder.create_progress_bar(
            current_seconds, total_seconds
        )
        progress_value = progress_bar
        if total_seconds > 0:
            pct = int(
                max(0.0, min(1.0, current_seconds / total_seconds)) * 100
            )
            progress_value = f"{progress_bar}\n`{pct}% concluido`"
        # Sem rótulo "Tempo" para evitar redundância com o canvas da imagem.
        embed.add_field(name="\u200b", value=progress_value, inline=False)

        queue_length = len(queue_list)
        if queue_length > 0:
            embed.set_footer(text=t("next_songs_in_queue", count=queue_length))
        else:
            embed.set_footer(text=t("queue_empty"))

        return embed

    # ------------------------------------------------------------------ #
    # Embeds simples                                                       #
    # ------------------------------------------------------------------ #

    @staticmethod
    def create_success_embed(
        title: str, description: str = ""
    ) -> discord.Embed:
        """Embed de sucesso."""
        return discord.Embed(
            title=f"✅ {title}",
            description=description,
            color=EmbedBuilder.COLOR_SUCCESS,
        )

    @staticmethod
    def create_error_embed(
        title: str, description: str = "", suggestion: str = ""
    ) -> discord.Embed:
        """Embed de erro com sugestão opcional."""
        full_desc = description
        if suggestion:
            full_desc += f"\n\n💡 **{t('suggestion')}:** {suggestion}"
        return discord.Embed(
            title=f"❌ {title}",
            description=full_desc,
            color=EmbedBuilder.COLOR_ERROR,
        )

    @staticmethod
    def create_warning_embed(
        title: str, description: str = ""
    ) -> discord.Embed:
        """Embed de aviso."""
        return discord.Embed(
            title=f"⚠️ {title}",
            description=description,
            color=EmbedBuilder.COLOR_WARNING,
        )

    @staticmethod
    def create_info_embed(title: str, description: str = "") -> discord.Embed:
        """Embed informativo."""
        return discord.Embed(
            title=f"ℹ️ {title}",
            description=description,
            color=EmbedBuilder.COLOR_INFO,
        )

    # ------------------------------------------------------------------ #
    # Fila                                                                 #
    # ------------------------------------------------------------------ #

    @staticmethod
    def create_queue_embed(
        current_song: dict | None, queue_list: list
    ) -> discord.Embed:
        """Embed compacto para fila (efêmero)."""
        total_songs = len(queue_list)

        # Duração total: aceita int/float (segundos) e string "MM:SS".
        total_seconds = 0
        for song in queue_list:
            if not isinstance(song, dict):
                continue
            dur = song.get("duration", 0)
            if isinstance(dur, (int, float)):
                total_seconds += dur
            elif isinstance(dur, str):
                # Tenta converter "MM:SS" ou "HH:MM:SS".
                # Ignora durações desconhecidas e lazy.
                try:
                    parts = [int(p) for p in dur.split(":")]
                    if len(parts) == 2:
                        total_seconds += parts[0] * 60 + parts[1]
                    elif len(parts) == 3:
                        total_seconds += (
                            parts[0] * 3600 + parts[1] * 60 + parts[2]
                        )
                except (ValueError, AttributeError):
                    pass  # Duração desconhecida/lazy — ignorar na soma

        total_minutes = int(total_seconds / 60)
        description = (
            f"📋 **{t('queue')}** ({total_songs} {t('songs')} • "
            f"~{total_minutes}{t('minutes_abbr')})\n\n"
        )

        if current_song:
            description += (
                f"🎵 **{t('playing_now')}** "
                f"{current_song.get('title', t('unknown'))}\n\n"
            )

        number_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        display_limit = min(10, total_songs)
        for i, song in enumerate(queue_list[:display_limit], 1):
            title = (
                song.get("title", t("unknown"))
                if isinstance(song, dict)
                else str(song)
            )
            duration = (
                song.get("duration", "?:??")
                if isinstance(song, dict)
                else "?:??"
            )
            emoji = number_emojis[i - 1] if i <= 10 else f"{i}."
            description += f"{emoji} {title} • {duration}\n"

        if total_songs > display_limit:
            remaining = total_songs - display_limit
            description += f"\n{t('and_more_songs', count=remaining)}"

        return discord.Embed(
            description=description, color=EmbedBuilder.COLOR_INFO
        )

    # ------------------------------------------------------------------ #
    # Rádio                                                                #
    # ------------------------------------------------------------------ #

    @staticmethod
    def create_radio_embed(radio_info: dict) -> discord.Embed:
        """Embed compacto para rádio ao vivo."""
        name = radio_info.get("name", t("unknown"))
        location = radio_info.get("location", t("unknown"))
        description = radio_info.get("description", "")

        embed_desc = f"📻 **{name}** {t('live')}\n"
        if description:
            embed_desc += f"{description}\n\n"
        embed_desc += f"📍 {location} • 🎧 {t('connected')}"

        return discord.Embed(
            description=embed_desc, color=EmbedBuilder.COLOR_RADIO
        )
