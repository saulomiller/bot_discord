"""endpoints para gerenciar playlists salvas e uploads."""

import base64
import logging
import os

from fastapi import APIRouter, Depends, HTTPException

from api.endpoints.models import PlaylistUploadRequest
from api.endpoints.security import require_api_key
from api.endpoints.validators import validate_upload_filename
from config import PLAYLIST_DIR

router = APIRouter()
MAX_PLAYLIST_BYTES = 1_000_000
MAX_PLAYLIST_LINES = 5000
MAX_PLAYLIST_LINE_CHARS = 4096


@router.get("/api/playlists")
async def get_playlists():
    """Return saved playlist files."""
    try:
        if not os.path.exists(PLAYLIST_DIR):
            os.makedirs(PLAYLIST_DIR)
        files = [
            name for name in os.listdir(PLAYLIST_DIR) if name.endswith(".txt")
        ]
        return {"status": "success", "playlists": files}
    except Exception as exc:
        logging.error(f"Erro ao obter playlists: {exc}")
        raise HTTPException(
            status_code=500, detail="Erro ao obter playlists."
        ) from exc


@router.post("/api/upload_playlist")
async def upload_playlist(
    payload: PlaylistUploadRequest,
    _: str = Depends(require_api_key),
):
    """Upload de arquivo de playlist .txt."""
    try:
        safe_filename = validate_upload_filename(
            payload.filename,
            allowed_extensions=(".txt",),
        )

        if not os.path.exists(PLAYLIST_DIR):
            os.makedirs(PLAYLIST_DIR)

        if payload.encoding == "base64":
            try:
                decoded = base64.b64decode(payload.file, validate=True)
                content = decoded.decode("utf-8")
            except Exception as exc:
                raise HTTPException(
                    status_code=400, detail="Conteúdo de playlist inválido."
                ) from exc
        else:
            content = payload.file

        encoded_content = content.encode("utf-8")
        if len(encoded_content) > MAX_PLAYLIST_BYTES:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Playlist excede o limite de {MAX_PLAYLIST_BYTES} bytes."
                ),
            )
        if "\x00" in content:
            raise HTTPException(
                status_code=400, detail="Conteúdo de playlist inválido."
            )

        lines = content.splitlines()
        if len(lines) > MAX_PLAYLIST_LINES:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Playlist excede o máximo de {MAX_PLAYLIST_LINES} linhas."
                ),
            )
        if any(len(line) > MAX_PLAYLIST_LINE_CHARS for line in lines):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Cada linha deve ter no máximo "
                    f"{MAX_PLAYLIST_LINE_CHARS} caracteres."
                ),
            )

        normalized_content = "\n".join(lines).strip() + ("\n" if lines else "")
        file_path = os.path.join(PLAYLIST_DIR, safe_filename)
        with open(file_path, "w", encoding="utf-8") as stream:
            stream.write(normalized_content)

        logging.info(f"Playlist '{safe_filename}' salva com sucesso via API")
        return {
            "status": "success",
            "message": f"Playlist '{safe_filename}' salva com sucesso.",
        }
    except HTTPException:
        raise
    except Exception as exc:
        logging.error(f"Erro no upload de playlist: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
