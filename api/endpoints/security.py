"""validacao de API key e controles de acesso da API."""

from fastapi import APIRouter, Header, HTTPException, Request

from config import API_KEY

router = APIRouter()


async def require_api_key(x_api_key: str = Header(None)):
    """Validate X-API-Key header for protected routes."""
    if x_api_key != API_KEY:
        raise HTTPException(
            status_code=401,
            detail="API Key inválida ou ausente. Inclua o header X-API-Key.",
        )
    return x_api_key


@router.get("/api/get_api_key")
async def get_api_key(request: Request):
    """Return API key only for local clients."""
    client_host = request.client.host if request.client else ""
    if client_host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(status_code=403, detail="Acesso negado.")
    return {"api_key": API_KEY}

