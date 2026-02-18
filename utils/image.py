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

def normalize_song_info(song_info: dict) -> dict:
    """
    Normaliza os dados de song_info para garantir compatibilidade
    entre diferentes fontes (YouTube, SoundCloud, rádio, etc.)
    """
    title_keys     = ['title', 'name', 'track', 'song']
    artist_keys    = ['channel', 'artist', 'uploader', 'author', 'creator']
    thumbnail_keys = ['thumbnail', 'artwork_url', 'art', 'image', 'cover']
    user_keys      = ['user', 'requested_by', 'requester']

    def _first(keys):
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
    song_info: dict,
    next_songs: list | None = None,
    progress_percent: float | None = None,
) -> BytesIO | None:
    """
    Gera card estilo Spotify com layout moderno.

    Args:
        song_info: Dados da música atual.
        next_songs: Lista de próximas músicas (dicts com 'title' e 'duration').
        progress_percent: Progresso de 0.0 a 1.0 para barra visual (opcional).

    Returns:
        BytesIO com a imagem PNG, ou None em caso de falha.
    """
    try:
        song_info = normalize_song_info(song_info)
        if next_songs is None:
            next_songs = []

        width, height = 900, 360
        padding = 30

        # ── Base escura ──────────────────────────────────────────────────
        card = Image.new("RGB", (width, height), (18, 18, 18))
        draw = ImageDraw.Draw(card)

        # ── Background ───────────────────────────────────────────────────
        thumb_url = song_info.get('thumbnail')
        content   = fetch_image_content(thumb_url) if thumb_url else None
        thumb     = None

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
                    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 80))
                    card.paste(overlay, (0, 0), overlay)
            except Exception as e:
                log.error(f"Erro ao gerar background: {e}")

            thumb = generate_thumbnail(content, (240, 240))

        # ── Gradiente lateral ─────────────────────────────────────────────
        apply_side_gradient(card, start_x=260)

        # ── Layout: thumbnail ─────────────────────────────────────────────
        cover_size = 240
        cover_x    = padding
        cover_y    = (height - cover_size) // 2

        if thumb:
            # Borda arredondada simulada com máscara
            mask = Image.new("L", (cover_size, cover_size), 0)
            mask_draw = ImageDraw.Draw(mask)
            radius = 16
            mask_draw.rounded_rectangle([0, 0, cover_size - 1, cover_size - 1], radius=radius, fill=255)
            card.paste(thumb, (cover_x, cover_y), mask)

        # ── Layout: texto ─────────────────────────────────────────────────
        text_x     = cover_x + cover_size + 40
        text_width = width - text_x - padding

        font_title  = get_font("arialbd.ttf", 40)
        font_artist = get_font("arial.ttf",   24)
        font_small  = get_font("arial.ttf",   19)
        font_queue  = get_font("arial.ttf",   17)

        # Título (até 2 linhas)
        title = song_info.get("title", "Desconhecido")
        try:
            lines = wrap_two_lines(draw, title, font_title, text_width)
        except Exception:
            lines = [truncate_text(draw, title, font_title, text_width)]

        y = 55
        for line in lines:
            draw_text_shadow(draw, (text_x, y), line, font_title, (255, 255, 255))
            y += 50

        # Artista
        artist = song_info.get("channel", "Desconhecido")
        artist_truncated = truncate_text(draw, artist, font_artist, text_width)
        draw_text_shadow(draw, (text_x, y + 6), artist_truncated, font_artist, (200, 200, 200))

        # Usuário que pediu
        user = song_info.get("user", "?")
        user_str = str(user) if not hasattr(user, 'display_name') else user.display_name
        user_label = f"Adicionado por {user_str}"
        draw_text_shadow(draw, (text_x, y + 36), user_label, font_small, (160, 160, 160))

        # ── Barra de progresso visual (opcional) ──────────────────────────
        bar_y = y + 70
        if progress_percent is not None:
            pct = max(0.0, min(1.0, progress_percent))
            bar_x      = text_x
            bar_w      = text_width
            bar_h      = 6
            bar_radius = 3

            # Trilha
            track_draw = ImageDraw.Draw(card)
            track_draw.rounded_rectangle(
                [bar_x, bar_y, bar_x + bar_w, bar_y + bar_h],
                radius=bar_radius, fill=(80, 80, 80)
            )
            # Preenchimento
            fill_w = int(bar_w * pct)
            if fill_w > 0:
                track_draw.rounded_rectangle(
                    [bar_x, bar_y, bar_x + fill_w, bar_y + bar_h],
                    radius=bar_radius, fill=(29, 185, 84)  # Verde Spotify
                )
            bar_y += bar_h + 10

        # ── Próximas músicas ──────────────────────────────────────────────
        if next_songs:
            queue_y = bar_y + 4
            label_text = "A seguir:"
            draw_text_shadow(draw, (text_x, queue_y), label_text, font_small, (140, 140, 140))
            queue_y += 22

            for i, song in enumerate(next_songs[:3], 1):
                if queue_y + 20 > height - padding:
                    break
                s_title    = song.get('title', '?')    if isinstance(song, dict) else str(song)
                s_duration = song.get('duration', '')  if isinstance(song, dict) else ''
                line_text  = f"{i}. {s_title}"
                if s_duration:
                    line_text += f"  {s_duration}"
                line_text = truncate_text(draw, line_text, font_queue, text_width)
                draw_text_shadow(draw, (text_x, queue_y), line_text, font_queue, (180, 180, 180))
                queue_y += 20

        # ── Salvar ────────────────────────────────────────────────────────
        buffer = BytesIO()
        card.save(buffer, "PNG", optimize=True)
        buffer.seek(0)
        return buffer

    except Exception as e:
        log.error(f"Erro fatal ao gerar card: {e}", exc_info=True)
        return None
