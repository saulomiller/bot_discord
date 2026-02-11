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
@lru_cache(maxsize=50)
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

def create_now_playing_card(song_info, next_songs=None, queue_length=0):
    """
    Gera uma imagem 'Now Playing' personalizada com lista de próximas músicas.
    Retorna um objeto BytesIO pronto para enviar no Discord.
    """
    # Correção: Argumento padrão mutável
    if next_songs is None:
        next_songs = []

    try:
        # Configurações de dimensão
        width, height = 800, 350
        background_color = (20, 20, 20)
        
        # Criar base
        card = Image.new("RGB", (width, height), background_color)
        draw = ImageDraw.Draw(card)
        
        # Carregar Thumbnail (Capa)
        thumb_url = song_info.get('thumbnail')
        content = fetch_image_content(thumb_url)
        
        if content:
            try:
                thumb = Image.open(BytesIO(content)).convert("RGB")
                
                # Fundo desfocado (Artwork Blur)
                bg_thumb = thumb.resize((width, height))
                bg_thumb = bg_thumb.filter(ImageFilter.GaussianBlur(20))
                bg_thumb = ImageEnhance.Brightness(bg_thumb).enhance(0.4)
                card.paste(bg_thumb, (0, 0))
                
                # Arte da capa (CD Style - Circular)
                thumb_size = 260
                thumb = thumb.resize((thumb_size, thumb_size))
                
                # Criar máscara circular
                mask = Image.new("L", (thumb_size, thumb_size), 0)
                draw_mask = ImageDraw.Draw(mask)
                draw_mask.ellipse((0, 0, thumb_size, thumb_size), fill=255)
                
                # Criar furo central (CD/Vinil)
                center = thumb_size // 2
                hole_radius = 25
                draw_mask.ellipse((center - hole_radius, center - hole_radius, center + hole_radius, center + hole_radius), fill=0)
                
                # Aplicar máscara
                thumb.putalpha(mask)
                
                # Sombra simples (circular)
                shadow = Image.new("RGBA", (thumb_size, thumb_size), (0, 0, 0, 0))
                draw_shadow = ImageDraw.Draw(shadow)
                draw_shadow.ellipse((5, 5, thumb_size-5, thumb_size-5), fill=(0, 0, 0, 100))
                
                card.paste(shadow, (45, 50), shadow)
                card.paste(thumb, (40, 45), thumb)
            except Exception as e:
                logging.error(f"Erro ao processar thumbnail: {e}")
        
        # Configurar fontes usando cache
        font_title = get_font('arialbd.ttf', 40)
        font_artist = get_font('arial.ttf', 24)
        font_list_header = get_font('arialbd.ttf', 22)
        font_list_item = get_font('arial.ttf', 20)

        # --- Seção Esquerda: Música Atual ---
        text_x = 320
        
        # Título
        title = song_info.get('title', 'Desconhecido')
        
        # Truncagem inteligente baseada em pixels
        max_title_width = 450
        
        try:
            if font_title.getlength(title) > max_title_width:
                while font_title.getlength(title + "...") > max_title_width and len(title) > 0:
                    title = title[:-1]
                title += "..."
        except AttributeError:
             if len(title) > 30:
                title = title[:27] + "..."
        except Exception as e:
            logging.warning(f"Erro na truncagem de texto: {e}")
            if len(title) > 30:
                title = title[:27] + "..."

        draw.text((text_x, 50), title, font=font_title, fill=(255, 255, 255))
        
        # Artista / Canal
        artist = song_info.get('channel', 'Desconhecido')
        draw.text((text_x, 100), f"🎙️ {artist}", font=font_artist, fill=(200, 200, 200))
        
        # Solicitante
        user = song_info.get('user', 'Desconhecido')
        draw.text((text_x, 130), f"👤 Pedido por: {user}", font=font_artist, fill=(180, 180, 180))
        
        # --- Seção Direita inferior: Próximas Músicas ---
        if next_songs:
            list_y = 190
            draw.text((text_x, list_y), "UP NEXT:", font=font_list_header, fill=(255, 215, 0))
            
            list_y += 30
            for i, song in enumerate(next_songs[:3]):
                song_title = song.get('title', 'Desconhecido')
                duration = song.get('duration', '?:??')
                
                # Truncagem simples nas próximas músicas (pode ser melhorado depois se precisar)
                if len(song_title) > 40:
                    song_title = song_title[:37] + "..."
                    
                line = f"{i+1}. {song_title} ({duration})"
                draw.text((text_x, list_y), line, font=font_list_item, fill=(230, 230, 230))
                list_y += 25
                
            if queue_length > 3:
                draw.text((text_x, list_y), f"...e mais {queue_length - 3} na fila", font=font_list_item, fill=(150, 150, 150))
        else:
            draw.text((text_x, 220), "Fila vazia... Adicione mais músicas!", font=font_artist, fill=(150, 150, 150))

        buffer = BytesIO()
        card.save(buffer, "PNG")
        buffer.seek(0)
        return buffer

    except Exception as e:
        logging.error(f"Erro ao gerar card de música: {e}")
        return None
