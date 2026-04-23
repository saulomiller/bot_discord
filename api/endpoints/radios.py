"""endpoints para listar, adicionar, remover e tocar radios."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

from api.endpoints.common import get_player_for_guild, require_voice_client
from api.endpoints.models import (
    RadioPlayRequest,
    RadioRemoveRequest,
    RadioRequest,
)
from api.endpoints.security import require_api_key
from utils.helpers import load_radios, save_radios

router = APIRouter()


@router.get("/api/radios")
async def get_radios():
    """Retorna radios."""
    try:
        radios_data = load_radios()
        return {"status": "success", "radios": radios_data.get("radios", [])}
    except Exception as exc:
        logging.error(f"Erro ao listar rádios: {exc}")
        raise HTTPException(
            status_code=500, detail="Erro ao listar rádios."
        ) from exc


@router.post("/api/radios/add")
async def add_radio(
    request: Request,
    body: RadioRequest,
    _: str = Depends(require_api_key),
):
    """Adiciona radio."""
    bot = request.app.state.bot
    try:
        radio_manager = load_radios()
        radios_list = radio_manager.get("radios", [])
        normalized_name = body.name.casefold()
        normalized_url = str(body.url)

        duplicate = next(
            (
                radio
                for radio in radios_list
                if str(radio.get("name", "")).casefold() == normalized_name
                or str(radio.get("url", "")) == normalized_url
            ),
            None,
        )
        if duplicate:
            raise HTTPException(
                status_code=409,
                detail="Já existe uma rádio com o mesmo nome ou URL.",
            )

        new_radio = {
            "id": str(uuid.uuid4()),
            "name": body.name,
            "url": normalized_url,
            "location": body.location,
            "description": body.description,
            "custom": True,
        }
        radios_list.append(new_radio)
        radio_manager["radios"] = radios_list
        if not save_radios(radio_manager):
            raise RuntimeError("Falha ao salvar rádios.")

        music_cog = bot.get_cog("MusicCog")
        if music_cog:
            music_cog.RADIOS = radio_manager

        return {
            "status": "success",
            "message": "Rádio adicionada com sucesso.",
            "radio": new_radio,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logging.error(f"Erro ao adicionar rádio: {exc}")
        raise HTTPException(
            status_code=500, detail="Erro ao adicionar rádio."
        ) from exc


@router.post("/api/radios/remove")
async def remove_radio(
    request: Request,
    body: RadioRemoveRequest,
    _: str = Depends(require_api_key),
):
    """Remove radio."""
    bot = request.app.state.bot
    try:
        radio_manager = load_radios()
        radios_list = radio_manager.get("radios", [])
        updated_radios = [
            radio for radio in radios_list if radio.get("id") != body.radio_id
        ]
        if len(updated_radios) == len(radios_list):
            raise HTTPException(
                status_code=404, detail="Rádio não encontrada."
            )
        radio_manager["radios"] = updated_radios
        if not save_radios(radio_manager):
            raise RuntimeError("Falha ao salvar rádios.")

        music_cog = bot.get_cog("MusicCog")
        if music_cog:
            music_cog.RADIOS = radio_manager

        return {"status": "success", "message": "Rádio removida."}
    except HTTPException:
        raise
    except Exception as exc:
        logging.error(f"Erro ao remover rádio: {exc}")
        raise HTTPException(
            status_code=500, detail="Erro ao remover rádio."
        ) from exc


@router.post("/api/radios/play")
async def play_radio(
    request: Request,
    body: RadioPlayRequest,
    _: str = Depends(require_api_key),
):
    """Inicia reproducao de radio."""
    bot = request.app.state.bot
    vc = require_voice_client(bot, body.guild_id)
    player = get_player_for_guild(bot, vc.guild.id)

    try:
        radio_manager = load_radios()
        radios_list = radio_manager.get("radios", [])
        radio = next(
            (
                entry
                for entry in radios_list
                if entry.get("id") == body.radio_id
            ),
            None,
        )
        if not radio:
            raise HTTPException(
                status_code=404, detail="Rádio não encontrada."
            )

        song = await player.add_to_queue(radio["url"], bot.user)
        if isinstance(song, dict):
            song["title"] = radio["name"]
            song["channel"] = "Radio"

        if not vc.is_playing() and not player.is_paused:
            await player.play_next()

        return {
            "status": "success",
            "message": f"Tocando rádio: '{radio['name']}'",
        }
    except HTTPException:
        raise
    except Exception as exc:
        logging.error(f"Erro ao tocar rádio via API: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
