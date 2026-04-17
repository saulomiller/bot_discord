"""endpoints de soundboard para listar, uploadar e reproduzir SFX."""

import logging
import os
import time

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from api.endpoints.common import get_player_for_guild, get_voice_client
from api.endpoints.models import (
    SoundboardFavoriteRequest,
    SoundboardPlayRequest,
    SoundboardVolumeRequest,
)
from api.endpoints.validators import (
    ensure_matching_resource_id,
    validate_resource_id,
    validate_upload_filename,
)
from config import ALLOWED_AUDIO_EXTENSIONS, SOUNDBOARD_DIR
from utils.helpers import (
    get_sfx_metadata,
    load_soundboard_metadata,
    save_soundboard_metadata,
    update_sfx_metadata,
)

router = APIRouter()
MAX_SFX_UPLOAD_BYTES = 20 * 1024 * 1024


@router.get("/api/soundboard")
async def get_soundboard():
    """Retorna soundboard."""
    try:
        if not os.path.exists(SOUNDBOARD_DIR):
            os.makedirs(SOUNDBOARD_DIR)

        files = [
            name
            for name in os.listdir(SOUNDBOARD_DIR)
            if name.lower().endswith(ALLOWED_AUDIO_EXTENSIONS)
        ]
        soundboard_list = []

        for filename in files:
            sfx_id = os.path.splitext(filename)[0]
            meta = get_sfx_metadata(sfx_id)
            soundboard_list.append(
                {
                    "id": sfx_id,
                    "name": sfx_id.replace("_", " ").title(),
                    "filename": filename,
                    "favorite": meta.get("favorite", False),
                    "volume": meta.get("volume", 1.0),
                }
            )

        soundboard_list.sort(
            key=lambda item: (not item["favorite"], item["name"])
        )
        return {"soundboard": soundboard_list}
    except Exception as exc:
        logging.error(f"Erro ao listar soundboard: {exc}")
        raise HTTPException(
            status_code=500, detail="Erro ao listar soundboard."
        ) from exc


@router.get("/api/soundboard/file/{filename}")
async def get_soundboard_file(filename: str):
    """Retorna soundboard file."""
    try:
        safe_filename = validate_upload_filename(
            filename,
            allowed_extensions=ALLOWED_AUDIO_EXTENSIONS,
        )

        file_path = os.path.join(SOUNDBOARD_DIR, safe_filename)
        if not os.path.exists(file_path):
            raise HTTPException(
                status_code=404, detail="Arquivo não encontrado."
            )
        return FileResponse(file_path, filename=safe_filename)
    except HTTPException:
        raise
    except Exception as exc:
        logging.error(f"Erro ao servir arquivo do soundboard: {exc}")
        raise HTTPException(
            status_code=500, detail="Erro ao carregar arquivo de áudio."
        ) from exc


@router.post("/api/soundboard/play")
async def play_soundboard(request: Request, body: SoundboardPlayRequest):
    """Inicia reproducao de soundboard."""
    bot = request.app.state.bot
    voice_client = get_voice_client(bot, body.guild_id)
    if not voice_client:
        raise HTTPException(
            status_code=400,
            detail="Bot não está conectado ao canal de voz neste servidor.",
        )

    player = get_player_for_guild(bot, body.guild_id)

    safe_sfx_id = validate_resource_id(body.sfx_id, label="sfx_id")
    sfx_path = None
    for ext in ALLOWED_AUDIO_EXTENSIONS:
        candidate = os.path.join(SOUNDBOARD_DIR, f"{safe_sfx_id}{ext}")
        if os.path.exists(candidate):
            sfx_path = candidate
            break
    if not sfx_path:
        raise HTTPException(
            status_code=404, detail="Efeito sonoro não encontrado."
        )

    try:
        meta = get_sfx_metadata(safe_sfx_id)
        volume = meta.get("volume", 1.0)
        await player.play_soundboard(sfx_path, volume)
        return {"status": "success", "message": f"Tocando {safe_sfx_id}"}
    except Exception as exc:
        logging.error(f"Erro ao tocar SFX: {exc}")
        raise HTTPException(
            status_code=500, detail=f"Erro ao tocar efeito: {str(exc)}"
        ) from exc


@router.post("/api/soundboard/upload")
async def upload_soundboard_file(file: UploadFile = File(...)):
    """Faz upload de soundboard file."""
    try:
        if not os.path.exists(SOUNDBOARD_DIR):
            os.makedirs(SOUNDBOARD_DIR)

        if not file.filename:
            raise HTTPException(
                status_code=400, detail="Nome de arquivo inválido."
            )
        safe_filename = validate_upload_filename(
            file.filename,
            allowed_extensions=ALLOWED_AUDIO_EXTENSIONS,
        )

        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(
                status_code=400, detail="Arquivo de áudio vazio."
            )
        if len(file_bytes) > MAX_SFX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Arquivo excede o limite de {MAX_SFX_UPLOAD_BYTES} bytes."
                ),
            )

        file_path = os.path.join(SOUNDBOARD_DIR, safe_filename)
        with open(file_path, "wb") as stream:
            stream.write(file_bytes)

        sfx_id = os.path.splitext(safe_filename)[0]
        update_sfx_metadata(sfx_id, {"favorite": False, "volume": 1.0})
        return {"status": "success", "message": "Upload concluído."}
    except HTTPException:
        raise
    except Exception as exc:
        logging.error(f"Erro no upload SFX: {exc}")
        raise HTTPException(
            status_code=500, detail=f"Erro no upload: {str(exc)}"
        ) from exc


@router.delete("/api/soundboard/{sfx_id}")
async def delete_soundboard(sfx_id: str):
    """Remove soundboard."""
    try:
        safe_sfx_id = validate_resource_id(sfx_id, label="sfx_id")
        deleted = False
        for ext in ALLOWED_AUDIO_EXTENSIONS:
            candidate = os.path.join(SOUNDBOARD_DIR, f"{safe_sfx_id}{ext}")
            if os.path.exists(candidate):
                last_exc = None
                # OneDrive/Windows can temporarily lock recently-written files.
                for attempt in range(5):
                    try:
                        os.remove(candidate)
                        deleted = True
                        break
                    except PermissionError as exc:
                        last_exc = exc
                        time.sleep(0.15 * (attempt + 1))
                if not deleted and last_exc:
                    raise last_exc
                break

        if not deleted:
            raise HTTPException(
                status_code=404, detail="Arquivo não encontrado."
            )

        metadata = load_soundboard_metadata()
        metadata["soundboard"] = [
            entry
            for entry in metadata.get("soundboard", [])
            if not (isinstance(entry, dict) and entry.get("id") == safe_sfx_id)
        ]
        save_soundboard_metadata(metadata)
        return {"status": "success", "message": "Efeito deletado."}
    except HTTPException:
        raise
    except Exception as exc:
        logging.error(f"Erro ao deletar SFX: {exc}")
        raise HTTPException(
            status_code=500, detail="Erro ao deletar arquivo."
        ) from exc


@router.patch("/api/soundboard/{sfx_id}/favorite")
async def toggle_favorite_soundboard(
    sfx_id: str, body: SoundboardFavoriteRequest
):
    """Alterna favorite soundboard."""
    try:
        safe_sfx_id = validate_resource_id(sfx_id, label="sfx_id")
        ensure_matching_resource_id(safe_sfx_id, body.sfx_id, label="sfx_id")
        update_sfx_metadata(safe_sfx_id, {"favorite": body.favorite})
        return {"status": "success", "message": "Favorito atualizado."}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail="Erro ao atualizar favorito."
        ) from exc


@router.patch("/api/soundboard/{sfx_id}/volume")
async def volume_soundboard(sfx_id: str, body: SoundboardVolumeRequest):
    """Executa a rotina de volume soundboard."""
    try:
        safe_sfx_id = validate_resource_id(sfx_id, label="sfx_id")
        ensure_matching_resource_id(safe_sfx_id, body.sfx_id, label="sfx_id")
        update_sfx_metadata(safe_sfx_id, {"volume": body.volume})
        return {"status": "success", "message": "Volume atualizado."}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail="Erro ao atualizar volume."
        ) from exc
