import os
import re

from fastapi import HTTPException

SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,127}$")
SAFE_RESOURCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def validate_upload_filename(
    filename: str,
    *,
    allowed_extensions: tuple[str, ...],
    allow_space: bool = True,
) -> str:
    if not filename:
        raise HTTPException(status_code=400, detail="Nome de arquivo inválido.")

    raw_name = filename.strip()
    safe_name = os.path.basename(raw_name)
    if safe_name != raw_name:
        raise HTTPException(status_code=400, detail="Nome de arquivo inválido.")
    if safe_name.startswith("."):
        raise HTTPException(status_code=400, detail="Nome de arquivo inválido.")
    if not allow_space and " " in safe_name:
        raise HTTPException(status_code=400, detail="Nome de arquivo inválido.")
    if not SAFE_FILENAME_RE.fullmatch(safe_name):
        raise HTTPException(status_code=400, detail="Nome de arquivo inválido.")

    ext = os.path.splitext(safe_name)[1].lower()
    if ext not in allowed_extensions:
        allowed = ", ".join(allowed_extensions)
        raise HTTPException(status_code=400, detail=f"Formato não suportado. Permitidos: {allowed}")

    return safe_name


def ensure_matching_resource_id(path_id: str, body_id: str, *, label: str) -> None:
    if path_id != body_id:
        raise HTTPException(status_code=400, detail=f"{label} do caminho difere do payload.")


def validate_resource_id(value: str, *, label: str) -> str:
    if not value or not SAFE_RESOURCE_ID_RE.fullmatch(value):
        raise HTTPException(status_code=400, detail=f"{label} inválido.")
    return value

