import discord

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
    def create_now_playing_embed(song_info, queue_length=0, current_seconds=0, total_seconds=0, color=None):
        """Criar embed compacto para música tocando"""
        title = song_info.get('title', 'Desconhecido')
        channel = song_info.get('channel', 'Desconhecido')
        author = song_info.get('author', 'Desconhecido')
        
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
            description += f"\n📋 {queue_length} na fila"
        
        # Usar cor dominante se fornecida, senão usar padrão
        embed_color = color if color else EmbedBuilder.COLOR_MUSIC

        embed = discord.Embed(
            description=description,
            color=embed_color
        )
        
        return embed
    
    @staticmethod
    def create_progress_bar(current_seconds, total_seconds, bar_length=10):
        """Cria uma barra de progresso visual com Unicode.
        
        Args:
            current_seconds: Tempo atual em segundos
            total_seconds: Duração total em segundos
            bar_length: Comprimento da barra (padrão: 10 caracteres)
            
        Returns:
            str: Barra de progresso formatada (ex: "▬▬▬🔘▬▬▬▬▬▬ 1:23 / 3:45")
        """
        if total_seconds <= 0:
            return "▬▬▬▬▬▬▬▬▬▬ 0:00 / 0:00"
        
        # Calcular posição do indicador
        percent = min(100, (current_seconds / total_seconds) * 100)
        filled = int((percent / 100) * bar_length)
        
        # Criar barra visual
        bar = ""
        for i in range(bar_length):
            if i == filled:
                bar += "🔘"
            else:
                bar += "▬"
        
        # Formatar tempos
        def format_time(seconds):
            mins, secs = divmod(int(seconds), 60)
            hours, mins = divmod(mins, 60)
            if hours > 0:
                return f"{hours}:{mins:02d}:{secs:02d}"
            return f"{mins}:{secs:02d}"
        
        current_time = format_time(current_seconds)
        total_time = format_time(total_seconds)
        
        return f"{bar} {current_time} / {total_time}"
    
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
            full_desc += f"\n\n💡 **Sugestão:** {suggestion}"
        
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
        
        description = f"📋 **Fila** ({total_songs} músicas • ~{total_minutes}min)\n\n"
        
        if current_song:
            description += f"🎵 **Tocando:** {current_song.get('title', 'Desconhecido')}\n\n"
        
        # Mostrar apenas as primeiras 10 músicas
        display_limit = min(10, total_songs)
        for i, song in enumerate(queue_list[:display_limit], 1):
            title = song.get('title', 'Desconhecido')
            duration = song.get('duration_formatted', '?:??')
            # Usar emojis numéricos
            number_emoji = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟'][i-1] if i <= 10 else f"{i}."
            description += f"{number_emoji} {title} • {duration}\n"
        
        if total_songs > display_limit:
            remaining = total_songs - display_limit
            description += f"\n... e mais {remaining} música{'s' if remaining > 1 else ''}"
        
        embed = discord.Embed(
            description=description,
            color=EmbedBuilder.COLOR_INFO
        )
        
        return embed
    
    @staticmethod
    def create_radio_embed(radio_info):
        """Criar embed compacto para rádio"""
        name = radio_info.get('name', 'Desconhecido')
        location = radio_info.get('location', 'Desconhecido')
        description = radio_info.get('description', '')
        
        embed_desc = f"📻 **{name}** ao vivo\n"
        if description:
            embed_desc += f"{description}\n\n"
        embed_desc += f"📍 {location} • 🎧 Conectado"
        
        embed = discord.Embed(
            description=embed_desc,
            color=EmbedBuilder.COLOR_RADIO
        )
        
        return embed
