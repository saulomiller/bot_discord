from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import requests
from io import BytesIO
import discord
import logging

def get_dominant_color(image_url):
    """
    Extrai a cor dominante de uma imagem a partir de uma URL.
    Retorna um discord.Color.
    """
    try:
        if not image_url:
            return discord.Color.default()

        response = requests.get(image_url, timeout=5)
        image = Image.open(BytesIO(response.content))
        image = image.resize((150, 150))  # Reduzir para processar mais rápido
        
        # Converter para RGB se não for
        if image.mode != "RGB":
            image = image.convert("RGB")

        # Pegar cores mais comuns (limitando a paleta)
        result = image.quantize(colors=10, method=2)
        dominant_color = result.getpalette()[:3]
        
        return discord.Color.from_rgb(dominant_color[0], dominant_color[1], dominant_color[2])
    except Exception as e:
        logging.error(f"Erro ao extrair cor dominante: {e}")
        return discord.Color.default()

def create_now_playing_card(song_info, progress_percent=0):
    """
    Gera uma imagem 'Now Playing' personalizada.
    Retorna um objeto BytesIO pronto para enviar no Discord.
    """
    try:
        # Configurações de dimensão
        width, height = 800, 300
        background_color = (20, 20, 20)
        
        # Criar base
        card = Image.new("RGB", (width, height), background_color)
        draw = ImageDraw.Draw(card)
        
        # Carregar Thumbnail
        thumb_url = song_info.get('thumbnail')
        if thumb_url:
            response = requests.get(thumb_url, timeout=5)
            thumb = Image.open(BytesIO(response.content)).convert("RGB")
            
            # Fundo desfocado
            bg_thumb = thumb.resize((width, height))
            bg_thumb = bg_thumb.filter(ImageFilter.GaussianBlur(15))
            bg_thumb = ImageEnhance.Brightness(bg_thumb).enhance(0.5) # Escurecer
            card.paste(bg_thumb, (0, 0))
            
            # Arte da capa (quadrada à esquerda)
            thumb_size = 220
            thumb = thumb.resize((thumb_size, thumb_size))
            card.paste(thumb, (40, 40))
        
        # Configurar fontes (usando padrão se custom não existir)
        # Tentar carregar fonte do sistema ou fallback
        try:
            # Caminho para fonte customizada (se tiver) ou padrão
            font_title = ImageFont.truetype("arial.ttf", 40)
            font_artist = ImageFont.truetype("arial.ttf", 25)
        except IOError:
            font_title = ImageFont.load_default()
            font_artist = ImageFont.load_default()

        # Textos
        title = song_info.get('title', 'Desconhecido')
        # Limitar tamanho do título
        if len(title) > 30:
            title = title[:27] + "..."
            
        artist = song_info.get('channel', 'Desconhecido')
        user = song_info.get('user', 'Desconhecido')
        
        # Posições
        text_x = 290
        draw.text((text_x, 50), title, font=font_title, fill=(255, 255, 255))
        draw.text((text_x, 100), artist, font=font_artist, fill=(200, 200, 200))
        draw.text((text_x, 140), f"Pedido por: {user}", font=font_artist, fill=(180, 180, 180))

        # Barra de Progresso
        bar_x = text_x
        bar_y = 220
        bar_width = 450
        bar_height = 10
        
        # Fundo da barra
        draw.rectangle(
            (bar_x, bar_y, bar_x + bar_width, bar_y + bar_height), 
            fill=(60, 60, 60)
        )
        
        # Progresso atual
        fill_width = int(bar_width * (progress_percent / 100))
        draw.rectangle(
            (bar_x, bar_y, bar_x + fill_width, bar_y + bar_height),
            fill=(87, 242, 135) # Verde do Discord
        )
        
        # Retornar buffer
        buffer = BytesIO()
        card.save(buffer, "PNG")
        buffer.seek(0)
        return buffer

    except Exception as e:
        logging.error(f"Erro ao gerar card de música: {e}")
        return None
