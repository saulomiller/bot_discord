"""Base compartilhada do cog de musica."""

import asyncio

import discord

from utils.helpers import load_radios
from utils.player import MusicPlayer


class MusicBaseMixin:
    """Mixin de comandos de musica."""

    def __init__(self, bot):
        """Inicializa a instancia da classe."""
        self.bot = bot
        self.RADIOS = load_radios()
        if not isinstance(self.RADIOS, dict):
            self.RADIOS = {"radios": []}

    def get_player(self, guild_id) -> MusicPlayer:
        """Retorna player."""
        if guild_id not in self.bot.players:
            self.bot.players[guild_id] = MusicPlayer(guild_id, self.bot)
        return self.bot.players[guild_id]

    def _radio_items(self):
        if not isinstance(self.RADIOS, dict):
            return []
        radios = self.RADIOS.get("radios", [])
        return radios if isinstance(radios, list) else []

    def _find_radio(self, radio_id: str):
        target_id = (radio_id or "").strip().lower()
        for radio in self._radio_items():
            if str(radio.get("id", "")).strip().lower() == target_id:
                return radio
        return None

    async def _send_embed_message(
        self, ctx_or_interaction, embed, *, wait_message: bool = False
    ):
        """Envia embed e opcionalmente retorna o objeto da mensagem."""
        if isinstance(ctx_or_interaction, discord.Interaction):
            if wait_message:
                return await ctx_or_interaction.followup.send(
                    embed=embed, wait=True
                )
            await ctx_or_interaction.followup.send(embed=embed)
            return None
        return await ctx_or_interaction.send(embed=embed)

    def _schedule_message_delete(self, message, delay: float | None = None):
        """Agenda remoção silenciosa da mensagem para manter o chat limpo."""
        if not message:
            return
        ttl = delay if delay is not None else self.FEEDBACK_DELETE_AFTER

        async def _delete_later():
            await asyncio.sleep(ttl)
            try:
                await message.delete()
            except Exception:
                pass

        self.bot.loop.create_task(_delete_later())
