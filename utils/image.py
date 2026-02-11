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

def create_now_playing_card(song_info, next_songs=[], queue_length=0):
    """
    Gera uma imagem 'Now Playing' personalizada com lista de próximas músicas.
    Retorna um objeto BytesIO pronto para enviar no Discord.
    """
    try:
        # Configurações de dimensão
        width, height = 800, 350 # Aumentado altura para caber a lista
        background_color = (20, 20, 20)
        
        # Criar base
        card = Image.new("RGB", (width, height), background_color)
        draw = ImageDraw.Draw(card)
        
        # Carregar Thumbnail (Capa)
        thumb_url = song_info.get('thumbnail')
        if thumb_url:
            try:
                response = requests.get(thumb_url, timeout=5)
                thumb = Image.open(BytesIO(response.content)).convert("RGB")
                
                # Fundo desfocado (Artwork Blur)
                bg_thumb = thumb.resize((width, height))
                bg_thumb = bg_thumb.filter(ImageFilter.GaussianBlur(20)) # Mais blur
                bg_thumb = ImageEnhance.Brightness(bg_thumb).enhance(0.4) # Mais escuro
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
                hole_radius = 25 # Tamanho do furo
                draw_mask.ellipse((center - hole_radius, center - hole_radius, center + hole_radius, center + hole_radius), fill=0)
                
                # Aplicar máscara
                thumb.putalpha(mask)
                
                # Sombra simples (circular)
                shadow = Image.new("RGBA", (thumb_size, thumb_size), (0, 0, 0, 0))
                draw_shadow = ImageDraw.Draw(shadow)
                draw_shadow.ellipse((5, 5, thumb_size-5, thumb_size-5), fill=(0, 0, 0, 100))
                
                # Colar sombra antes (levemente deslocada se quiser, aqui centralizada/trás)
                # Na verdade, colar sombra no card
                card.paste(shadow, (45, 50), shadow) # Deslocado para dar efeito
                
                # Colar o CD
                card.paste(thumb, (40, 45), thumb)
            except Exception as e:
                logging.error(f"Erro ao processar thumbnail: {e}")

        # Configurar fontes
        try:
            # Tenta usar Arial se disponível (Windows/Linux comum), senão default
            font_title = ImageFont.truetype("arial.ttf", 38)
            font_artist = ImageFont.truetype("arial.ttf", 22)
            font_list_header = ImageFont.truetype("arial.ttf", 20)
            font_list_item = ImageFont.truetype("arial.ttf", 18)
        except IOError:
            # Fallback para fonte padrão (feia mas funciona)
            font_title = ImageFont.load_default()
            font_artist = ImageFont.load_default()
            font_list_header = ImageFont.load_default()
            font_list_item = ImageFont.load_default()

        # --- Seção Esquerda: Música Atual ---
        text_x = 320
        
        # Título
        title = song_info.get('title', 'Desconhecido')
        if len(title) > 35:
            title = title[:32] + "..."
        draw.text((text_x, 50), title, font=font_title, fill=(255, 255, 255))
        
        # Artista / Canal
        artist = song_info.get('channel', 'Desconhecido')
        draw.text((text_x, 100), f"🎙️ {artist}", font=font_artist, fill=(200, 200, 200))
        
        # Solicitante
        user = song_info.get('user', 'Desconhecido')
        draw.text((text_x, 130), f"👤 Pedido por: {user}", font=font_artist, fill=(180, 180, 180))
        
        # --- Seção Direita inferior: Próximas Músicas (Mini Lista) ---
        if next_songs:
            list_y = 190
            draw.text((text_x, list_y), "UP NEXT:", font=font_list_header, fill=(255, 215, 0)) # Gold
            
            list_y += 30
            for i, song in enumerate(next_songs[:3]):
                song_title = song.get('title', 'Desconhecido')
                duration = song.get('duration', '?:??')
                
                if len(song_title) > 40:
                    song_title = song_title[:37] + "..."
                    
                line = f"{i+1}. {song_title} ({duration})"
                draw.text((text_x, list_y), line, font=font_list_item, fill=(230, 230, 230))
                list_y += 25
                
            if queue_length > 3:
                draw.text((text_x, list_y), f"...e mais {queue_length - 3} na fila", font=font_list_item, fill=(150, 150, 150))
        else:
            draw.text((text_x, 220), "Fila vazia... Adicione mais músicas!", font=font_artist, fill=(150, 150, 150))

        # Nota: Barra de progresso visual removida da imagem para ser feita via Texto/Embed dinâmico

        buffer = BytesIO()
        card.save(buffer, "PNG")
        buffer.seek(0)
        return buffer

    except Exception as e:
        logging.error(f"Erro ao gerar card de música: {e}")
        return None
