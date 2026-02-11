from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import requests
from io import BytesIO
import discord
import logging
import os
from functools import lru_cache

# --- Otimização: Cache de Fontes Global ---
FONTS = {}

def get_font(name, size):
    """Carrega e cachea fontes para evitar I/O repetitivo."""
    key = (name, size)
    if key not in FONTS:
        try:
            # Caminho absoluto seguro
            font_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fonts')
            font_path = os.path.join(font_dir, name)
            FONTS[key] = ImageFont.truetype(font_path, size)
        except Exception as e:
            logging.warning(f"Fonte {name} não encontrada, usando padrão: {e}")
            FONTS[key] = ImageFont.load_default()
    return FONTS[key]

# --- Otimização: Cache de Imagens ---
@lru_cache(maxsize=80)
def fetch_image_content(url):
    """Baixa e cachea conteúdo de imagens."""
    if not url:
        return None
    try:
        response = requests.get(url, timeout=(5, 10)) # connect, read
        response.raise_for_status()
        return response.content
    except Exception as e:
        logging.error(f"Erro ao baixar imagem {url}: {e}")
        return None

        return None

@lru_cache(maxsize=80)
def generate_blurred_background(image_bytes, width, height):
    """Gera o background desfocado a partir dos bytes da imagem original."""
    if not image_bytes: return None
    try:
        thumb = Image.open(BytesIO(image_bytes)).convert("RGB")
        bg = thumb.resize((width, height))
        bg = bg.filter(ImageFilter.GaussianBlur(25))
        bg = ImageEnhance.Brightness(bg).enhance(0.35)
        return bg
    except Exception as e:
        logging.error(f"Erro no cache de blur: {e}")
        return None

@lru_cache(maxsize=120)
def generate_thumbnail(image_bytes, size):
    """Gera a thumbnail redimensionada (quadrada)."""
    if not image_bytes: return None
    try:
        thumb = Image.open(BytesIO(image_bytes)).convert("RGB")
        return thumb.resize(size)
    except Exception as e:
        logging.error(f"Erro no cache de thumbnail: {e}")
        return None

def get_dominant_color(image_url):
    """
    Extrai a cor dominante de uma imagem a partir de uma URL.
    Retorna um discord.Color.
    """
    try:
        content = fetch_image_content(image_url)
        if not content:
            return discord.Color.default()

        image = Image.open(BytesIO(content))
        image = image.resize((150, 150))  # Reduzir para processar mais rápido
        
        # Converter para RGB se não for
        if image.mode != "RGB":
            image = image.convert("RGB")

        # Pegar cores mais comuns (limitando a paleta)
        result = image.quantize(colors=10, method=2)
        
        # Correção: Usar getcolors() para garantir a cor mais frequente
        colors = result.convert('RGB').getcolors(maxcolors=256) # convert('RGB') é crucial aqui para getcolors retornar RGB
        if not colors:
             return discord.Color.default()

        # getcolors retorna lista de (count, pixel)
        # Ordenar por count decrescente e pegar o pixel da cor mais comum
        dominant_color = max(colors, key=lambda x: x[0])[1]
        
        return discord.Color.from_rgb(dominant_color[0], dominant_color[1], dominant_color[2])
    except Exception as e:
        logging.error(f"Erro ao extrair cor dominante: {e}")
        return discord.Color.default()


def truncate_text(draw, text, font, max_width, suffix="..."):
    """Trunca texto baseado na largura REAL em pixels usando textbbox."""
    
    # se já cabe, retorna direto
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0]
    if width <= max_width:
        return text

    # busca binária (muito mais rápido que while char por char)
    left, right = 0, len(text)

    while left < right:
        mid = (left + right) // 2
        candidate = text[:mid] + suffix

        bbox = draw.textbbox((0, 0), candidate, font=font)
        width = bbox[2] - bbox[0]

        if width <= max_width:
            left = mid + 1
        else:
            right = mid

    return text[:left-1] + suffix


def apply_side_gradient(base_img, start_x):
    """Adiciona gradient escuro da direita para a esquerda."""
    width, height = base_img.size
    
    # Otimização: Criar 1 linha e redimensionar (mais rápido que iterar pixel a pixel)
    gradient = Image.new("L", (width, 1))
    for x in range(width):
        if x < start_x:
            alpha = 0
        else:
            alpha = int(255 * (x - start_x) / (width - start_x))
        gradient.putpixel((x, 0), alpha)
        
    gradient = gradient.resize((width, height))
    
    black = Image.new("RGBA", (width, height), (0, 0, 0, 200))
    base_img.paste(black, (0, 0), gradient)

def draw_text_shadow(draw, pos, text, font, fill, offset=2):
    x, y = pos
    # Sombra
    draw.text((x+offset, y+offset), text, font=font, fill=(0,0,0))
    # Texto
    draw.text((x, y), text, font=font, fill=fill)

def wrap_two_lines(draw, text, font, max_width):
    """Quebra o texto em no máximo 2 linhas."""
    words = text.split()
    lines = []
    current = ""

    for word in words:
        test_line = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test_line, font=font)
        w = bbox[2] - bbox[0]

        if w <= max_width:
            current = test_line
        else:
            if current:
                lines.append(current)
            current = word
            # Se já temos 1 linha e estamos quebrando para a segunda,
            # a próxima iteração vai definir a segunda linha.
            # Se tentarmos criar uma terceira, paramos.
            if len(lines) >= 1:
                break
    
    if current:
        lines.append(current)

    return lines[:2]

def create_now_playing_card(song_info, next_songs=None, queue_length=0):
    """Gera card estilo Spotify com grid e layout moderno."""
    if next_songs is None:
        next_songs = []

    width, height = 900, 360
    padding = 30

    # Base escura
    card = Image.new("RGB", (width, height), (18,18,18))
    draw = ImageDraw.Draw(card)

    thumb_url = song_info.get('thumbnail')
    content = fetch_image_content(thumb_url)
    
    thumb = None
    if content:
        # Background blur usando cache
        bg = generate_blurred_background(content, width, height)
        if bg:
            card.paste(bg, (0,0))
            
        # Thumbnail usando cache
        thumb = generate_thumbnail(content, (240, 240))  # Tamanho fixo do layout (cover_size)

    # Gradient lateral
    apply_side_gradient(card, start_x=260)

    # ==============================
    # GRID LAYOUT
    # ==============================

    cover_size = 240
    cover_x = padding
    cover_y = (height - cover_size)//2

    if thumb:
        card.paste(thumb, (cover_x, cover_y))

    text_x = cover_x + cover_size + 40
    text_width = width - text_x - padding

    # Fontes
    font_title = get_font("arialbd.ttf", 42)
    font_artist = get_font("arial.ttf", 24)
    font_small = get_font("arial.ttf", 20)

    # ==============================
    # TÍTULO (2 linhas)
    # ==============================

    title = song_info.get("title", "Desconhecido")
    try:
        lines = wrap_two_lines(draw, title, font_title, text_width)
    except Exception:
        lines = [title]

    y = 60
    for line in lines:
        draw_text_shadow(draw, (text_x, y), line, font_title, (255,255,255))
        y += 48

    # ==============================
    # ARTISTA
    # ==============================

    artist = song_info.get("channel", "Desconhecido")
    draw_text_shadow(draw, (text_x, y+5), f"🎙️ {artist}", font_artist, (210,210,210))

    # ==============================
    # USER
    # ==============================

    user = song_info.get("user", "?")
    draw_text_shadow(draw, (text_x, y+35), f"👤 {user}", font_small, (170,170,170))

    # ==============================
    # QUEUE
    # ==============================

    qy = 200
    
    if next_songs:
        draw_text_shadow(draw, (text_x, qy), "UP NEXT", font_small, (255,215,0))
        qy += 28

        for i, song in enumerate(next_songs[:3]):
            t = song.get("title", "")
            try:
                t = truncate_text(draw, t, font_small, text_width)
            except:
                pass
            
            line = f"{i+1}. {t}"
            draw_text_shadow(draw, (text_x, qy), line, font_small, (220,220,220))
            qy += 26
            
        if queue_length > 3:
             draw_text_shadow(draw, (text_x, qy), f"...e mais {queue_length - 3} na fila", font_small, (150,150,150))
    else:
        draw_text_shadow(draw, (text_x, qy), "Fila vazia...", font_small, (150,150,150))

    buffer = BytesIO()
    card.save(buffer, "PNG")
    buffer.seek(0)
    return buffer
