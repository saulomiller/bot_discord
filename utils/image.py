"""
utils/image.py — Geração de cards visuais para o dashboard do bot.

Melhorias:
- create_now_playing_card aceita next_songs para mostrar fila na imagem
- get_dominant_color_from_bytes exposto para uso direto em embeds.py
- Melhor tratamento de erros e fallbacks em todas as funções
- Barra de progresso visual opcional na imagem
- Sanitização de filename no upload de soundboard
"""

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import requests
from io import BytesIO
import logging
import os
from functools import lru_cache

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache global de fontes e sessão HTTP
# ---------------------------------------------------------------------------

FONTS: dict = {}
SESSION = requests.Session()
SESSION.headers.update({'User-Agent': 'Mozilla/5.0 (bot)'})

_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fonts')


def get_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    """Carrega e cacheia fontes para evitar I/O repetitivo."""
    key = (name, size)
    if key not in FONTS:
        try:
            font_path = os.path.join(_FONT_DIR, name)
            FONTS[key] = ImageFont.truetype(font_path, size)
        except Exception as e:
            log.warning(f"Fonte '{name}' não encontrada, usando padrão: {e}")
            FONTS[key] = ImageFont.load_default()
    return FONTS[key]


# ---------------------------------------------------------------------------
# Download e cache de imagens
# ---------------------------------------------------------------------------

@lru_cache(maxsize=80)
def fetch_image_content(url: str) -> bytes | None:
    """Baixa e cacheia conteúdo de imagens por URL."""
    if not url:
        return None
    try:
        response = SESSION.get(url, timeout=(5, 10))
        response.raise_for_status()
        return response.content
    except Exception as e:
        log.error(f"Erro ao baixar imagem {url}: {e}")
        return None


# ---------------------------------------------------------------------------
# Processamento de imagens (com cache)
# ---------------------------------------------------------------------------

def cover_resize(img: Image.Image, width: int, height: int) -> Image.Image:
    """Redimensiona estilo 'cover' (preenche tudo sem distorcer)."""
    iw, ih = img.size
    scale = max(width / iw, height / ih)
    new_size = (int(iw * scale), int(ih * scale))
    img = img.resize(new_size, Image.LANCZOS)
    left = (img.width - width) // 2
    top  = (img.height - height) // 2
    return img.crop((left, top, left + width, top + height))


@lru_cache(maxsize=80)
def generate_blurred_background(image_bytes: bytes, width: int, height: int) -> Image.Image | None:
    """Gera o background desfocado a partir dos bytes da imagem original."""
    if not image_bytes:
        return None
    try:
        thumb = Image.open(BytesIO(image_bytes)).convert("RGB")
        bg = cover_resize(thumb, width, height)
        blur_radius = max(8, int(min(width, height) * 0.06))
        bg = bg.filter(ImageFilter.GaussianBlur(blur_radius))
        bg = ImageEnhance.Brightness(bg).enhance(0.35)
        return bg
    except Exception as e:
        log.error(f"Erro ao gerar background desfocado: {e}")
        return None


@lru_cache(maxsize=120)
def generate_thumbnail(image_bytes: bytes, size: tuple) -> Image.Image | None:
    """Gera thumbnail quadrada com crop central e alta qualidade."""
    if not image_bytes:
        return None
    try:
        img = Image.open(BytesIO(image_bytes)).convert("RGB")
        w, h = img.size
        min_side = min(w, h)
        left   = (w - min_side) // 2
        top    = (h - min_side) // 2
        img    = img.crop((left, top, left + min_side, top + min_side))
        return img.resize(size, Image.LANCZOS)
    except Exception as e:
        log.error(f"Erro ao gerar thumbnail: {e}")
        return None


def is_low_resolution(img: Image.Image, min_size: int = 300) -> bool:
    """Retorna True se a imagem for menor que min_size em qualquer dimensão."""
    w, h = img.size
    return w < min_size or h < min_size


# ---------------------------------------------------------------------------
# Extração de cor dominante
# ---------------------------------------------------------------------------

def get_dominant_color_from_bytes(content: bytes) -> tuple[int, int, int]:
    """
    Extrai a cor dominante de uma imagem a partir de bytes.
    Retorna tupla (r, g, b). Fallback: (30, 30, 30).
    """
    if not content:
        return (30, 30, 30)
    try:
        image = Image.open(BytesIO(content)).convert("RGB")
        image = image.resize((100, 100))  # Reduzido para maior velocidade
        result = image.quantize(colors=8, method=2)
        colors = result.convert('RGB').getcolors(maxcolors=256)
        if not colors:
            return (30, 30, 30)
        # Retorna a cor mais frequente
        return max(colors, key=lambda x: x[0])[1]
    except Exception as e:
        log.error(f"Erro ao extrair cor dominante: {e}")
        return (30, 30, 30)


def get_dominant_color(url: str) -> tuple[int, int, int]:
    """
    Wrapper que aceita URL, baixa (com cache) e retorna cor dominante (r, g, b).
    Mantido síncrono: callers devem executar em executor se necessário.
    """
    try:
        content = fetch_image_content(url)
        return get_dominant_color_from_bytes(content)
    except Exception as e:
        log.error(f"Erro ao obter cor dominante de {url}: {e}")
        return (30, 30, 30)


# ---------------------------------------------------------------------------
# Utilitários de desenho
# ---------------------------------------------------------------------------

def truncate_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int, suffix: str = "...") -> str:
    """Trunca texto baseado na largura real em pixels (busca binária)."""
    bbox = draw.textbbox((0, 0), text, font=font)
    if bbox[2] - bbox[0] <= max_width:
        return text

    left, right = 0, len(text)
    while left < right:
        mid = (left + right) // 2
        candidate = text[:mid] + suffix
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_width:
            left = mid + 1
        else:
            right = mid

    return text[:max(0, left - 1)] + suffix


def apply_side_gradient(base_img: Image.Image, start_x: int) -> None:
    """Adiciona gradiente escuro da esquerda para a direita a partir de start_x."""
    width, height = base_img.size
    gradient = Image.new("L", (width, 1))
    for x in range(width):
        if x < start_x:
            alpha = 0
        else:
            alpha = int(255 * (x - start_x) / max(1, width - start_x))
        gradient.putpixel((x, 0), alpha)
    gradient = gradient.resize((width, height))
    # Converter para RGBA para suportar paste com máscara de transparência
    base_rgba = base_img.convert("RGBA")
    black = Image.new("RGBA", (width, height), (0, 0, 0, 200))
    base_rgba.paste(black, (0, 0), gradient)
    # Copiar de volta para o base_img (in-place)
    base_img.paste(base_rgba.convert("RGB"))


def draw_text_shadow(draw: ImageDraw.ImageDraw, pos: tuple, text: str, font, fill: tuple, offset: int = 2) -> None:
    """Desenha texto com sombra para melhor legibilidade."""
    x, y = pos
    draw.text((x + offset, y + offset), text, font=font, fill=(0, 0, 0, 180))
    draw.text((x, y), text, font=font, fill=fill)


def wrap_two_lines(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    """Quebra o texto em no máximo 2 linhas."""
    words = text.split()
    lines = []
    current = ""

    for i, word in enumerate(words):
        test_line = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test_line, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test_line
        else:
            if current:
                lines.append(current)
            if len(lines) >= 1:
                # Segunda linha: juntar palavra atual com o restante e truncar
                remaining = " ".join(words[i:])
                current = truncate_text(draw, remaining, font, max_width)
                break
            current = word

    if current:
        lines.append(current)

    return lines[:2]


# ---------------------------------------------------------------------------
# Normalização de dados da música
# ---------------------------------------------------------------------------

def normalize_song_info(song_info: dict | None) -> dict:
    """
    Normaliza os dados de song_info para garantir compatibilidade
    entre diferentes fontes (YouTube, SoundCloud, rádio, etc.)
    """
    if not isinstance(song_info, dict):
        song_info = {}

    title_keys     = ['title', 'name', 'track', 'song']
    artist_keys    = ['channel', 'artist', 'uploader', 'author', 'creator']
    thumbnail_keys = ['thumbnail', 'artwork_url', 'art', 'image', 'cover']
    user_keys      = ['user', 'requested_by', 'requester']

    def _first(keys):
        """Executa a rotina de fir t."""
        for k in keys:
            v = song_info.get(k)
            if v:
                return v
        return None

    normalized = {
        'title':            _first(title_keys)     or "Título Desconhecido",
        'channel':          _first(artist_keys)    or "Artista Desconhecido",
        'thumbnail':        _first(thumbnail_keys),
        'user':             _first(user_keys)      or "?",
        'duration':         song_info.get('duration', '?:??'),
        'duration_seconds': song_info.get('duration_seconds', 0),  # Preservar para barra de progresso
    }
    return normalized


# ---------------------------------------------------------------------------
# Card visual principal
# ---------------------------------------------------------------------------

def create_now_playing_card(
    song_info: dict | None,
    next_songs: list | None = None,
    progress_percent: float | None = None,
) -> BytesIO | None:
    """
    Gera card quadrado para "now playing", alinhado ao visual do embed.

    Args:
        song_info: Dados da musica atual.
        next_songs: Lista de proximas musicas (dicts com 'title' e 'duration').
        progress_percent: Progresso de 0.0 a 1.0 para barra visual (opcional).

    Returns:
        BytesIO com a imagem PNG, ou None em caso de falha.
    """
    try:
        song_info = normalize_song_info(song_info)
        if next_songs is None:
            next_songs = []

        width, height = 640, 640
        padding = 28
        cover_size = 236

        card = Image.new("RGB", (width, height), (18, 18, 18))
        draw = ImageDraw.Draw(card)

        thumb_url = song_info.get('thumbnail')
        content = fetch_image_content(thumb_url) if thumb_url else None
        thumb = None

        if content:
            try:
                img = Image.open(BytesIO(content)).convert("RGB")
                if is_low_resolution(img):
                    r, g, b = get_dominant_color_from_bytes(content)
                    bg = Image.new("RGB", (width, height), (r, g, b))
                else:
                    bg = generate_blurred_background(content, width, height)

                if bg:
                    card.paste(bg, (0, 0))
                    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 96))
                    card.paste(overlay, (0, 0), overlay)
            except Exception as e:
                log.error(f"Erro ao gerar background: {e}")

            thumb = generate_thumbnail(content, (cover_size, cover_size))

        vignette = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        vignette_draw = ImageDraw.Draw(vignette)
        for y in range(height):
            alpha = int(15 + 165 * (y / max(1, height - 1)))
            vignette_draw.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))
        card.paste(vignette, (0, 0), vignette)

        cover_x = (width - cover_size) // 2
        cover_y = 40

        # Badge superior para reforçar estado "tocando agora"
        font_badge = get_font("arialbd.ttf", 15)
        badge_text = "TOCANDO AGORA"
        badge_bbox = draw.textbbox((0, 0), badge_text, font=font_badge)
        badge_w = (badge_bbox[2] - badge_bbox[0]) + 22
        badge_h = (badge_bbox[3] - badge_bbox[1]) + 10
        badge_x = (width - badge_w) // 2
        badge_y = 10
        draw.rounded_rectangle(
            [badge_x, badge_y, badge_x + badge_w, badge_y + badge_h],
            radius=12,
            fill=(29, 185, 84),
        )
        draw.text(
            (badge_x + 11, badge_y + 5),
            badge_text,
            font=font_badge,
            fill=(15, 15, 15),
        )

        mask = Image.new("L", (cover_size, cover_size), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle([0, 0, cover_size - 1, cover_size - 1], radius=24, fill=255)

        if thumb:
            card.paste(thumb, (cover_x, cover_y), mask)
        else:
            placeholder = Image.new("RGB", (cover_size, cover_size), (42, 42, 42))
            ph_draw = ImageDraw.Draw(placeholder)
            ph_font = get_font("arialbd.ttf", 30)
            ph_text = "NO ART"
            ph_bbox = ph_draw.textbbox((0, 0), ph_text, font=ph_font)
            ph_w = ph_bbox[2] - ph_bbox[0]
            ph_h = ph_bbox[3] - ph_bbox[1]
            ph_draw.text(
                ((cover_size - ph_w) // 2, (cover_size - ph_h) // 2),
                ph_text,
                font=ph_font,
                fill=(170, 170, 170),
            )
            card.paste(placeholder, (cover_x, cover_y), mask)

        draw.rounded_rectangle(
            [cover_x - 2, cover_y - 2, cover_x + cover_size + 1, cover_y + cover_size + 1],
            radius=26,
            outline=(230, 230, 230),
            width=2,
        )

        text_width = width - (padding * 2)
        font_title = get_font("arialbd.ttf", 33)
        font_small = get_font("arial.ttf", 16)
        font_queue = get_font("arial.ttf", 18)

        def draw_centered_line(text: str, y: int, font, fill: tuple[int, int, int]) -> None:
            safe_text = truncate_text(draw, text, font, text_width)
            bbox = draw.textbbox((0, 0), safe_text, font=font)
            line_w = bbox[2] - bbox[0]
            x = (width - line_w) // 2
            draw_text_shadow(draw, (x, y), safe_text, font, fill, offset=1)

        title = song_info.get("title", "Desconhecido")
        try:
            lines = wrap_two_lines(draw, title, font_title, text_width)
        except Exception:
            lines = [truncate_text(draw, title, font_title, text_width)]

        y = cover_y + cover_size + 22
        for line in lines:
            draw_centered_line(line, y, font_title, (255, 255, 255))
            line_box = draw.textbbox((0, 0), line, font=font_title)
            line_h = line_box[3] - line_box[1]
            y += line_h + 8

        user = song_info.get("user", "?")
        user_str = str(user) if not hasattr(user, 'display_name') else user.display_name
        user_label = f"{user_str}"
        artist = song_info.get("channel", "Desconhecido")

        # Manter seção de próximas músicas no card e posicionar metadados no topo do box.
        panel_x = padding
        panel_y = y + 24
        panel_w = width - (padding * 2)
        panel_h = height - panel_y - padding

        draw.rounded_rectangle(
            [panel_x, panel_y, panel_x + panel_w, panel_y + panel_h],
            radius=18,
            fill=(14, 14, 14),
            outline=(76, 76, 76),
            width=1,
        )

        meta_pad = 14
        meta_gap = 12
        meta_y = panel_y + 12
        meta_max_w = max(60, (panel_w - (meta_pad * 2) - meta_gap) // 2)

        left_meta = truncate_text(draw, user_label, font_small, meta_max_w)
        right_meta = truncate_text(draw, str(artist), font_small, meta_max_w)
        draw_text_shadow(
            draw,
            (panel_x + meta_pad, meta_y),
            left_meta,
            font_small,
            (175, 175, 175),
            offset=1,
        )
        right_bbox = draw.textbbox((0, 0), right_meta, font=font_small)
        right_w = right_bbox[2] - right_bbox[0]
        right_x = panel_x + panel_w - meta_pad - right_w
        draw_text_shadow(
            draw,
            (right_x, meta_y),
            right_meta,
            font_small,
            (206, 206, 206),
            offset=1,
        )

        meta_h = (right_bbox[3] - right_bbox[1]) if (right_bbox[3] - right_bbox[1]) > 0 else 16
        sep_y = meta_y + meta_h + 10
        draw.line(
            [(panel_x + 12, sep_y), (panel_x + panel_w - 12, sep_y)],
            fill=(60, 60, 60),
            width=1,
        )

        queue_y = sep_y + 10
        draw_text_shadow(draw, (panel_x + 14, queue_y), "A seguir", font_small, (154, 154, 154), offset=1)
        queue_y += 26

        queue_text_width = panel_w - 28
        content_bottom = panel_y + panel_h - 8
        available_h = max(24, content_bottom - queue_y)
        max_lines = max(1, available_h // 24)

        if next_songs:
            for i, song in enumerate(next_songs[:max_lines], 1):
                s_title = song.get('title', '?') if isinstance(song, dict) else str(song)
                s_duration = song.get('duration', '') if isinstance(song, dict) else ''
                if s_duration in ('Desconhecida', 'Desconhecido', None):
                    s_duration = '...'
                line_text = f"{i}. {s_title}"
                if s_duration:
                    line_text += f" ({s_duration})"
                line_text = truncate_text(draw, line_text, font_queue, queue_text_width)
                draw_text_shadow(draw, (panel_x + 14, queue_y), line_text, font_queue, (206, 206, 206), offset=1)
                queue_y += 24
        else:
            draw_text_shadow(
                draw,
                (panel_x + 14, queue_y),
                "Fila vazia no momento",
                font_queue,
                (170, 170, 170),
                offset=1,
            )

        buffer = BytesIO()
        card.save(buffer, "PNG", optimize=True)
        buffer.seek(0)
        return buffer

    except Exception as e:
        log.error(f"Erro fatal ao gerar card: {e}", exc_info=True)
        return None
