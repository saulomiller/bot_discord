import discord
from utils.i18n import t

class EmbedBuilder:
    """Classe para criar embeds padronizados e compactos"""
    
    # Cores padronizadas
    COLOR_SUCCESS = discord.Color.from_rgb(87, 242, 135)   # Verde
    COLOR_ERROR = discord.Color.from_rgb(255, 107, 107)    # Vermelho
    COLOR_INFO = discord.Color.from_rgb(116, 185, 255)     # Azul
    COLOR_WARNING = discord.Color.from_rgb(255, 195, 113)  # Laranja
    COLOR_MUSIC = discord.Color.from_rgb(147, 112, 219)    # Roxo
    COLOR_RADIO = discord.Color.from_rgb(255, 154, 162)    # Rosa
    
    @staticmethod
    def _format_time(seconds: float) -> str:
        """Formata segundos para string HH:MM:SS ou MM:SS. Reutilizável e não recriada a cada chamada."""
        mins, secs = divmod(int(seconds), 60)
        hours, mins = divmod(mins, 60)
        if hours > 0:
            return f"{hours}:{mins:02d}:{secs:02d}"
        return f"{mins}:{secs:02d}"
    
    @staticmethod
    def create_now_playing_embed(song_info, queue_length=0, current_seconds=0, total_seconds=0, color=None):
        """Criar embed compacto para música tocando"""
        title = song_info.get('title', t('unknown'))
        channel = song_info.get('channel', t('unknown'))
        author = song_info.get('author', t('unknown'))
        
        # Criar descrição compacta
        description = f"🎵 **{title}**\n"
        description += f"🎤 {channel}"
        
        if hasattr(author, 'mention'):
            description += f" • 👤 {author.mention}"
            
        # Adicionar barra de progresso se houver duração
        if total_seconds > 0:
            progress_bar = EmbedBuilder.create_progress_bar(current_seconds, total_seconds)
            description += f"\n\n{progress_bar}"
        
        if queue_length > 0:
            description += f"\n📋 {queue_length} {t('in_queue')}"
        
        # Usar cor dominante se fornecida, senão usar padrão
        embed_color = EmbedBuilder.COLOR_MUSIC
        if color:
            try:
                # Tuplas/listas iteráveis com 3 valores
                if isinstance(color, (tuple, list)) and len(color) >= 3:
                    r, g, b = int(color[0]), int(color[1]), int(color[2])
                    embed_color = discord.Color.from_rgb(r, g, b)
                # String hex like '#RRGGBB' or 'RRGGBB'
                elif isinstance(color, str):
                    hexc = color.lstrip('#')
                    if len(hexc) == 6:
                        r = int(hexc[0:2], 16)
                        g = int(hexc[2:4], 16)
                        b = int(hexc[4:6], 16)
                        embed_color = discord.Color.from_rgb(r, g, b)
                    else:
                        embed_color = EmbedBuilder.COLOR_MUSIC
                elif isinstance(color, discord.Color):
                    embed_color = color
                elif isinstance(color, int):
                    embed_color = color
                else:
                    embed_color = EmbedBuilder.COLOR_MUSIC
            except Exception as e:
                # Em caso de problema, logar e usar cor padrão
                try:
                    logging = __import__('logging')
                    logging.debug(f"Falha ao converter cor dominante: {e} (valor: {color})")
                except Exception:
                    pass
                embed_color = EmbedBuilder.COLOR_MUSIC

        embed = discord.Embed(
            description=description,
            color=embed_color
        )
        
        return embed
    
    @staticmethod
    def create_progress_bar(current_seconds, total_seconds, bar_length=14):
        """Cria uma barra de progresso visual estilo Spotify (otimizada)."""
        if total_seconds <= 0:
            return f"`{'▱' * bar_length}`  0:00 / 0:00"
        
        # Calcular porcentagem (clamped)
        percent = max(0, min(1, current_seconds / total_seconds))
        
        # Construir barra com tratamento especial para 100%
        if percent >= 1.0:
            # Totalmente preenchido (concluído)
            bar = "▰" * bar_length
        else:
            # Cálculo do preenchimento com cursor
            filled = int(percent * (bar_length - 1))
            bar = "▰" * filled + "●" + "▱" * (bar_length - filled - 1)
        
        # Formatar tempos usando método estático (sem recreação)
        current_time = EmbedBuilder._format_time(current_seconds)
        total_time = EmbedBuilder._format_time(total_seconds)
        
        # Retornar com code block inline + destaque visual (Spotify-style)
        return f"`{bar}`  **{current_time}** / {total_time}"
    
    @staticmethod
    def create_success_embed(title, description=""):
        """Criar embed de sucesso (para mensagens efêmeras)"""
        embed = discord.Embed(
            title=f"✅ {title}",
            description=description,
            color=EmbedBuilder.COLOR_SUCCESS
        )
        return embed
    
    @staticmethod
    def create_error_embed(title, description="", suggestion=""):
        """Criar embed de erro (para mensagens efêmeras)"""
        full_desc = description
        if suggestion:
            full_desc += f"\n\n💡 **{t('suggestion')}:** {suggestion}"
        
        embed = discord.Embed(
            title=f"❌ {title}",
            description=full_desc,
            color=EmbedBuilder.COLOR_ERROR
        )
        return embed
    
    @staticmethod
    def create_info_embed(title, description=""):
        """Criar embed informativo"""
        embed = discord.Embed(
            title=f"ℹ️ {title}",
            description=description,
            color=EmbedBuilder.COLOR_INFO
        )
        return embed
    
    @staticmethod
    def create_queue_embed(current_song, queue_list):
        """Criar embed compacto para fila (efêmero)"""
        total_songs = len(queue_list)
        
        # Calcular duração total estimada
        total_duration = sum(song.get('duration', 0) for song in queue_list)
        total_minutes = int(total_duration / 60)
        
        description = f"📋 **{t('queue')}** ({total_songs} {t('songs')} • ~{total_minutes}{t('minutes_abbr')})\n\n"
        
        if current_song:
            description += f"🎵 **{t('playing_now')}** {current_song.get('title', t('unknown'))}\n\n"
        
        # Mostrar apenas as primeiras 10 músicas
        display_limit = min(10, total_songs)
        for i, song in enumerate(queue_list[:display_limit], 1):
            title = song.get('title', t('unknown'))
            duration = song.get('duration_formatted', '?:??')
            # Usar emojis numéricos
            number_emoji = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟'][i-1] if i <= 10 else f"{i}."
            description += f"{number_emoji} {title} • {duration}\n"
        
        if total_songs > display_limit:
            remaining = total_songs - display_limit
            description += f"\n{t('and_more_songs', count=remaining)}"
        
        embed = discord.Embed(
            description=description,
            color=EmbedBuilder.COLOR_INFO
        )
        
        return embed
    
    @staticmethod
    def create_radio_embed(radio_info):
        """Criar embed compacto para rádio"""
        name = radio_info.get('name', t('unknown'))
        location = radio_info.get('location', t('unknown'))
        description = radio_info.get('description', '')
        
        embed_desc = f"📻 **{name}** {t('live')}\n"
        if description:
            embed_desc += f"{description}\n\n"
        embed_desc += f"📍 {location} • 🎧 {t('connected')}"
        
        embed = discord.Embed(
            description=embed_desc,
            color=EmbedBuilder.COLOR_RADIO
        )
        
        return embed
