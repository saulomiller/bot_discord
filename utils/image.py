"""
utils/image.py — Geração de cards visuais para o dashboard do bot.

Melhorias:
- create_now_playing_card aceita next_songs para mostrar fila na imagem
- get_dominant_color_from_bytes exposto para uso direto em embeds.py
- Melhor tratamento de erros e fallbacks em todas as funções
- Barra de progresso visual opcional na imagem
- Sanitização de filename no upload de soundboard
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from io import BytesIO
import logging
import os
import hashlib
import atexit
from threading import Lock, RLock
from typing import Optional, List, Dict, Tuple, Any, Union

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from cachetools import TTLCache

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Globais, Thread Safety e Cache
# ---------------------------------------------------------------------------

FONTS: dict = {}
_font_lock = Lock()
cache_lock = RLock()

SESSION = requests.Session()
SESSION.trust_env = False
SESSION.headers.update({'User-Agent': 'Mozilla/5.0 (bot)'})
retry_strategy = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"]
)
adapter = HTTPAdapter(max_retries=retry_strategy)
SESSION.mount("https://", adapter)
SESSION.mount("http://", adapter)

def sizeof_image(value):
    if isinstance(value, bytes):
        return len(value)
    if isinstance(value, Image.Image):
        # Estimativa O(1) nativa de complexidade evitando tobytes() excessivo
        return value.width * value.height * len(value.getbands())
    return 1

# O maxsize deve estar alinhado à escala do sizeof (em bytes)
# Fix "value too large" exception capping TTLCache memory to exactly ~50MB cada.
MAX_CACHE_SIZE_BYTES = 50 * 1024 * 1024

image_cache_raw = TTLCache(maxsize=MAX_CACHE_SIZE_BYTES, ttl=300, getsizeof=sizeof_image)
image_cache_processed = TTLCache(maxsize=MAX_CACHE_SIZE_BYTES, ttl=300, getsizeof=sizeof_image)

max_workers = min(8, os.cpu_count() or 4)
executor = ThreadPoolExecutor(max_workers=max_workers)
atexit.register(executor.shutdown)

DEFAULT_BG_COLOR = (18, 18, 18)
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB Limits prevents crashing RAM by huge images

_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fonts')

def get_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    """Carrega e cacheia fontes para evitar I/O repetitivo, thread-safe."""
    key = (name, size)
    with _font_lock:
        if key not in FONTS:
            try:
                font_path = os.path.join(_FONT_DIR, name)
                FONTS[key] = ImageFont.truetype(font_path, size)
            except Exception as e:
                log.warning(f"Fonte '{name}' não encontrada, usando padrão: {e}")
                FONTS[key] = ImageFont.load_default()
        return FONTS[key]

# ---------------------------------------------------------------------------
# DataStructures
# ---------------------------------------------------------------------------

@dataclass
class ImageAssets:
    original: Optional[Image.Image] = None
    thumbnail: Optional[Image.Image] = None
    background: Optional[Image.Image] = None
    dominant_color: Tuple[int, int, int] = DEFAULT_BG_COLOR

    def is_valid(self) -> bool:
        return self.original is not None

def hash_bytes(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()

# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def fetch_image_content(url: str) -> Optional[bytes]:
    """Baixa e cacheia conteúdo de imagens por URL usando raw cache (Anti Stampede)."""
    if not url:
        return None
        
    cache_key = f"fetch_{url}"
    
    with cache_lock:
        if cache_key in image_cache_raw:
            return image_cache_raw[cache_key]
        
    try:
        response = SESSION.get(url, stream=True, timeout=(5, 10))
        response.raise_for_status()

        # Proteção contra ataques de imagens gigantes ou falhas maliciosas do header
        if int(response.headers.get("Content-Length", 0)) > MAX_IMAGE_SIZE:
             log.error(f"Erro: Imagem excede {MAX_IMAGE_SIZE} bytes. {url}")
             return None
             
        data = response.content
        if len(data) > MAX_IMAGE_SIZE:
             log.error(f"Erro Real: Imagem recebida excede limite! {url}")
             return None

        with cache_lock:
            image_cache_raw[cache_key] = data
            
        return data
    except Exception as e:
        log.error(f"Erro ao baixar imagem {url}: {e}")
        return None

# ---------------------------------------------------------------------------
# Processamento de imagens
# ---------------------------------------------------------------------------

def cover_resize(img: Image.Image, width: int, height: int) -> Image.Image:
    """Redimensiona estilo 'cover' preservando proporções (crop)."""
    iw, ih = img.size
    scale = max(width / iw, height / ih)
    new_size = (int(iw * scale), int(ih * scale))
    img = img.resize(new_size, Image.Resampling.LANCZOS)
    left = (img.width - width) // 2
    top  = (img.height - height) // 2
    return img.crop((left, top, left + width, top + height))

def generate_blurred_background(img: Image.Image, width: int, height: int) -> Image.Image:
    """Gera o background desfocado a partir de uma imagem já carregada."""
    bg = cover_resize(img, width, height)
    blur_radius = max(8, int(min(width, height) * 0.06))
    bg = bg.filter(ImageFilter.GaussianBlur(blur_radius))
    bg = ImageEnhance.Brightness(bg).enhance(0.35)
    return bg

def generate_thumbnail(img: Image.Image, size: Tuple[int, int]) -> Image.Image:
    """Gera thumbnail quadrada com crop central usando .thumbnail() para downscale eficiente."""
    w, h = img.size
    min_side = min(w, h)
    left = (w - min_side) // 2
    top = (h - min_side) // 2
    cropped = img.crop((left, top, left + min_side, top + min_side))
    
    cropped.thumbnail(size, Image.Resampling.LANCZOS)
    
    if cropped.size != size:
        new_img = Image.new("RGB", size, (0, 0, 0))
        new_img.paste(cropped, ((size[0] - cropped.size[0]) // 2, (size[1] - cropped.size[1]) // 2))
        return new_img
    return cropped

def is_low_resolution(img: Image.Image, min_size: int = 300) -> bool:
    """Retorna True se a imagem for menor que min_size em qualquer dimensão."""
    w, h = img.size
    return w < min_size or h < min_size

def get_dominant_color_from_bytes(content: bytes) -> tuple[int, int, int]:
    """
    Extrai a cor dominante de uma imagem a partir de bytes.
    Fará um fallback ultra-esmart para o getpixel resizing 1x1.
    """
    if not content:
        return (30, 30, 30)
    
    h = hash_bytes(content)
    cache_key = f"color_{h}"
    
    with cache_lock:
        if cache_key in image_cache_processed:
            return image_cache_processed[cache_key]

    try:
        with Image.open(BytesIO(content)) as img_opened:
            img_opened.load()
            image = img_opened.copy().convert("RGB")
            
        image.thumbnail((100, 100), Image.Resampling.LANCZOS)
        result = image.quantize(colors=8, method=Image.Quantize.FASTOCTREE)
        colors = result.convert('RGB').getcolors(maxcolors=256)

        fallback_color = DEFAULT_BG_COLOR
        try:
            avg_color = image.resize((1, 1)).getpixel((0, 0))
            if isinstance(avg_color, tuple) and len(avg_color) == 3:
                fallback_color = avg_color
        except:
            pass

        if not colors:
            return fallback_color
            
        rgb = max(colors, key=lambda x: x[0])[1]
        final_color = rgb if isinstance(rgb, tuple) and len(rgb) == 3 else fallback_color
        
        with cache_lock:
             image_cache_processed[cache_key] = final_color
        return final_color
    except Exception as e:
        log.error(f"Erro ao extrair cor dominante: {e}")
        return DEFAULT_BG_COLOR

def get_dominant_color(url: str) -> tuple[int, int, int]:
    try:
        content = fetch_image_content(url)
        return get_dominant_color_from_bytes(content)
    except Exception as e:
        log.error(f"Erro ao obter cor dominante de {url}: {e}")
        return DEFAULT_BG_COLOR

# ---------------------------------------------------------------------------
# Utilitários de desenho
# ---------------------------------------------------------------------------

def truncate_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int, suffix: str = "...") -> str:
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
    width, height = base_img.size
    grad_width = max(1, width - start_x)
    
    alpha_grad = Image.linear_gradient("L").resize((grad_width, 1))
    alpha_grad = alpha_grad.resize((grad_width, height))
    
    gradient_mask = Image.new("L", (width, height), 0)
    gradient_mask.paste(alpha_grad, (start_x, 0))
    
    black_layer = Image.new("RGBA", (width, height), (0, 0, 0, 200))
    
    base_rgba = base_img if base_img.mode == "RGBA" else base_img.convert("RGBA")
    base_rgba.paste(black_layer, (0, 0), gradient_mask)
    
    if base_img.mode != "RGBA":
        base_img.paste(base_rgba.convert(base_img.mode))

def get_vignette_layer(width: int, height: int) -> Image.Image:
    vignette = Image.linear_gradient("L").rotate(90).resize((1, height))
    vignette = vignette.resize((width, height))
    
    vignette_mask = vignette.point(lambda p: int(15 + 165 * ((255 - p) / 255.0)))
    
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 255))
    layer.putalpha(vignette_mask)
    return layer

def draw_text_shadow(draw: ImageDraw.ImageDraw, pos: tuple, text: str, font, fill: tuple, offset: int = 2) -> None:
    x, y = pos
    draw.text((x + offset, y + offset), text, font=font, fill=(0, 0, 0, 180))
    draw.text((x, y), text, font=font, fill=fill)

def wrap_two_lines(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
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
                remaining = " ".join(words[i:])
                current = truncate_text(draw, remaining, font, max_width)
                break
            current = word
    if current:
        lines.append(current)

    return lines[:2]

# ---------------------------------------------------------------------------
# Pipeline Helpers e Export
# ---------------------------------------------------------------------------

def normalize_song_info(song_info: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(song_info, dict):
        song_info = {}

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
        'duration_seconds': song_info.get('duration_seconds', 0),
    }
    return normalized

def prepare_image_assets(content: Optional[bytes], cover_size: int, width: int, height: int) -> ImageAssets:
    """ETAPA 2: Processamento - Retorna objeto ImageAssets preenchido."""
    assets = ImageAssets()
    if not content:
        return assets
    
    assets.dominant_color = get_dominant_color_from_bytes(content)
        
    try:
        h = hash_bytes(content)
        cache_key_thumb = f"thumb_{cover_size}_{h}"
        cache_key_bg = f"bg_{width}_{height}_{h}"
        
        with cache_lock:
            # Reconstrói via buffer comprimido (Otimização pesada de Memória cacheada)
            if cache_key_thumb in image_cache_processed and cache_key_bg in image_cache_processed:
                assets.thumbnail = Image.open(BytesIO(image_cache_processed[cache_key_thumb])).convert("RGB")
                assets.background = Image.open(BytesIO(image_cache_processed[cache_key_bg])).convert("RGB")
                return assets
             
        with Image.open(BytesIO(content)) as img_opened:
            img_opened.load()
            img = img_opened.copy().convert("RGB")
            assets.original = img
            
        # Não clona o objeto, a .crop da função original não o destruirá nativamente.
        assets.thumbnail = generate_thumbnail(img, (cover_size, cover_size))
        
        buf_thumb = BytesIO()
        assets.thumbnail.save(buf_thumb, format="JPEG", quality=85)
        
        if is_low_resolution(img):
            r, g, b = assets.dominant_color
            assets.background = Image.new("RGB", (width, height), (r, g, b))
        else:
            assets.background = generate_blurred_background(img, width, height)
            
        buf_bg = BytesIO()
        assets.background.save(buf_bg, format="JPEG", quality=75)
        
        with cache_lock:
             image_cache_processed[cache_key_thumb] = buf_thumb.getvalue()
             image_cache_processed[cache_key_bg] = buf_bg.getvalue()
             
    except Exception as e:
        log.error(f"Erro ao preparar assets da imagem: {e}")
        
    return assets

def draw_card_layout(song_info: dict, assets: ImageAssets, next_songs: list, progress_percent: float | None = None) -> BytesIO:
    """ETAPA 3: Render - Desenha todos os elementos do card a partir dos assets."""
    width, height = 640, 640
    padding = 28
    cover_size = 236

    card = Image.new("RGB", (width, height), DEFAULT_BG_COLOR)
    draw = ImageDraw.Draw(card)

    if assets.background:
        card.paste(assets.background, (0, 0))
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 96))
        card.paste(overlay, (0, 0), overlay)

    vignette = get_vignette_layer(width, height)
    card.paste(vignette, (0, 0), vignette)

    cover_x = (width - cover_size) // 2
    cover_y = 40

    font_badge = get_font("arialbd.ttf", 15)
    badge_text = "TOCANDO AGORA"
    badge_bbox = draw.textbbox((0, 0), badge_text, font=font_badge)
    badge_w = (badge_bbox[2] - badge_bbox[0]) + 22
    badge_h = (badge_bbox[3] - badge_bbox[1]) + 10
    badge_x = (width - badge_w) // 2
    badge_y = 10
    draw.rounded_rectangle([badge_x, badge_y, badge_x + badge_w, badge_y + badge_h], radius=12, fill=(29, 185, 84))
    draw.text((badge_x + 11, badge_y + 5), badge_text, font=font_badge, fill=(15, 15, 15))

    mask = Image.new("L", (cover_size, cover_size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([0, 0, cover_size - 1, cover_size - 1], radius=24, fill=255)

    if assets.thumbnail:
        card.paste(assets.thumbnail, (cover_x, cover_y), mask)
    else:
        placeholder = Image.new("RGB", (cover_size, cover_size), (42, 42, 42))
        ph_draw = ImageDraw.Draw(placeholder)
        ph_font = get_font("arialbd.ttf", 30)
        ph_text = "NO ART"
        ph_bbox = ph_draw.textbbox((0, 0), ph_text, font=ph_font)
        ph_w = ph_bbox[2] - ph_bbox[0]
        ph_h = ph_bbox[3] - ph_bbox[1]
        ph_draw.text(((cover_size - ph_w) // 2, (cover_size - ph_h) // 2), ph_text, font=ph_font, fill=(170, 170, 170))
        card.paste(placeholder, (cover_x, cover_y), mask)

    draw.rounded_rectangle([cover_x - 2, cover_y - 2, cover_x + cover_size + 1, cover_y + cover_size + 1], radius=26, outline=(230, 230, 230), width=2)

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
    artist = song_info.get("channel", "Desconhecido")

    panel_x = padding
    panel_y = y + 24
    panel_w = width - (padding * 2)
    panel_h = height - panel_y - padding

    draw.rounded_rectangle([panel_x, panel_y, panel_x + panel_w, panel_y + panel_h], radius=18, fill=(14, 14, 14), outline=(76, 76, 76), width=1)

    meta_pad = 14
    meta_gap = 12
    meta_y = panel_y + 12
    meta_max_w = max(60, (panel_w - (meta_pad * 2) - meta_gap) // 2)

    left_meta = truncate_text(draw, user_str, font_small, meta_max_w)
    right_meta = truncate_text(draw, str(artist), font_small, meta_max_w)
    draw_text_shadow(draw, (panel_x + meta_pad, meta_y), left_meta, font_small, (175, 175, 175), offset=1)
    
    right_bbox = draw.textbbox((0, 0), right_meta, font=font_small)
    right_w = right_bbox[2] - right_bbox[0]
    right_x = panel_x + panel_w - meta_pad - right_w
    draw_text_shadow(draw, (right_x, meta_y), right_meta, font_small, (206, 206, 206), offset=1)

    meta_h = (right_bbox[3] - right_bbox[1]) if (right_bbox[3] - right_bbox[1]) > 0 else 16
    sep_y = meta_y + meta_h + 10
    draw.line([(panel_x + 12, sep_y), (panel_x + panel_w - 12, sep_y)], fill=(60, 60, 60), width=1)

    queue_y = sep_y + 10
    draw_text_shadow(draw, (panel_x + 14, queue_y), "A seguir", font_small, (154, 154, 154), offset=1)
    queue_y += 26

    queue_text_width = panel_w - 28
    
    # Progress Bar feature
    has_progress = progress_percent is not None and isinstance(progress_percent, (int, float))
    if has_progress:
        progress_percent = max(0, min(1, float(progress_percent))) # clamp
        progress_h = 4
        progress_y = panel_y + panel_h - progress_h - 10
        content_bottom = progress_y - 8
    else:
        content_bottom = panel_y + panel_h - 8

    available_h = max(24, content_bottom - queue_y)
    max_lines = max(1, available_h // 24)

    if next_songs and isinstance(next_songs, list):
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
        draw_text_shadow(draw, (panel_x + 14, queue_y), "Fila vazia no momento", font_queue, (170, 170, 170), offset=1)

    if has_progress:
        # Background bar
        bar_w = panel_w - 28
        bar_x = panel_x + 14
        draw.rounded_rectangle([bar_x, progress_y, bar_x + bar_w, progress_y + progress_h], radius=2, fill=(40, 40, 40))
        # Foreground bar
        fill_w = int(bar_w * progress_percent)
        if fill_w > 0:
            draw.rounded_rectangle([bar_x, progress_y, bar_x + fill_w, progress_y + progress_h], radius=2, fill=(29, 185, 84))

    buffer = BytesIO()
    card.save(buffer, "PNG", optimize=True, compress_level=6)
    buffer.seek(0)
    return buffer

def create_now_playing_card(
    song_info: dict | None,
    next_songs: list | None = None,
    progress_percent: float | None = None,
) -> BytesIO | None:
    try:
        if progress_percent is not None and not isinstance(progress_percent, (int, float)):
             progress_percent = None

        song_info = normalize_song_info(song_info)
        if not isinstance(next_songs, list):
            next_songs = []

        thumb_url = song_info.get('thumbnail')
        content = fetch_image_content(thumb_url) if thumb_url else None
        
        assets = prepare_image_assets(content, cover_size=236, width=640, height=640)
        
        return draw_card_layout(song_info, assets, next_songs, progress_percent)

    except Exception as e:
        log.error(f"Erro fatal ao gerar card: {e}", exc_info=True)
        return None

# ---------------------------------------------------------------------------
# FASE 8 - Async Wrapper
# ---------------------------------------------------------------------------

async def create_now_playing_card_async(
    song_info: dict | None,
    next_songs: list | None = None,
    progress_percent: float | None = None,
) -> BytesIO | None:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        executor, 
        create_now_playing_card, 
        song_info, 
        next_songs, 
        progress_percent
    )
