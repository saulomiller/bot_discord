import discord
from discord.ext import commands
from discord import app_commands
import logging
import os
import asyncio
from pathlib import Path
from config import SOUNDBOARD_DIR, ALLOWED_AUDIO_EXTENSIONS
from utils.helpers import get_sfx_metadata
from utils.i18n import t

class SoundboardCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def get_player(self, guild_id):
        if guild_id not in self.bot.players:
            # Importar MusicPlayer aqui para evitar import circular se necessário, 
            # mas como cogs são carregados depois, deve estar ok.
            from utils.player import MusicPlayer
            self.bot.players[guild_id] = MusicPlayer(guild_id, self.bot)
        return self.bot.players[guild_id]

    async def sfx_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """Autocomplete para listar SFX disponíveis"""
        choices = []
        try:
            for file in Path(SOUNDBOARD_DIR).glob("*"):
                if file.suffix.lower() in ALLOWED_AUDIO_EXTENSIONS:
                    name = file.stem
                    if current.lower() in name.lower():
                        choices.append(app_commands.Choice(name=name, value=name))
        except Exception as e:
            logging.error(f"Erro no autocomplete de SFX: {e}")
        
        return choices[:25]  # Discord limita a 25

    @app_commands.command(name="sfx", description="Plays a sound effect")
    @app_commands.describe(nome="Sound effect name")
    @app_commands.autocomplete(nome=sfx_autocomplete)
    async def sfx_command(self, interaction: discord.Interaction, nome: str):
        """Comando para tocar SFX - COM EMBED EFÊMERO"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Verificar se bot está em canal de voz
            player = self.get_player(interaction.guild_id)
            if not player or not player.voice_client:
                await interaction.followup.send(
                    t('user_must_be_in_voice'),
                    ephemeral=True
                )
                return
            
            # Buscar arquivo
            sfx_path = None
            for ext in ALLOWED_AUDIO_EXTENSIONS:
                path = Path(SOUNDBOARD_DIR) / f"{nome}{ext}"
                if path.exists():
                    sfx_path = str(path)
                    break
            
            if not sfx_path:
                await interaction.followup.send(
                    t('sfx_not_found', name=nome),
                    ephemeral=True
                )
                return
            
            # Obter volume configurado
            metadata = get_sfx_metadata(nome)
            volume = metadata.get("volume", 1.0)
            
            # Tocar SFX
            await player.play_soundboard(sfx_path, volume=volume)
            
            # EMBED EFÊMERO mostrando quem pediu
            embed = discord.Embed(
                description=t('sfx_requested_by', user=interaction.user.mention, name=nome),
                color=discord.Color.from_rgb(147, 112, 219)
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            
            logging.info(f"SFX '{nome}' tocado por {interaction.user.name}")
            
        except Exception as e:
            logging.error(f"Erro ao tocar SFX: {e}")
            await interaction.followup.send(
                t('error'),
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(SoundboardCog(bot))
