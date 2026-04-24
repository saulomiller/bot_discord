"""validacao de API key e controles de acesso da API."""

import secrets
import time

from fastapi import APIRouter, Body, Cookie, Header, HTTPException, Request, Response

from config import (
    ADMIN_LOGIN_LOCKOUT_SECONDS,
    ADMIN_LOGIN_MAX_ATTEMPTS,
    ADMIN_SESSION_COOKIE,
    ADMIN_SESSION_TTL_SECONDS,
    API_KEY,
    is_admin_password_configured,
    verify_admin_password,
)

router = APIRouter()


def _get_sessions(request: Request) -> dict:
    """Retorna o armazenamento em memoria das sessoes admin."""
    sessions = getattr(request.app.state, "admin_sessions", None)
    if sessions is None:
        sessions = {}
        request.app.state.admin_sessions = sessions
    return sessions


def _get_login_failures(request: Request) -> dict:
    """Retorna tentativas de login falhas por cliente."""
    failures = getattr(request.app.state, "admin_login_failures", None)
    if failures is None:
        failures = {}
        request.app.state.admin_login_failures = failures
    return failures


def _client_key(request: Request) -> str:
    """Identifica o cliente para throttle de login."""
    return request.client.host if request.client else "unknown"


def _is_session_valid(request: Request, session_id: str | None) -> bool:
    """Valida e renova a sessao admin em memoria."""
    if not session_id:
        return False

    sessions = _get_sessions(request)
    expires_at = sessions.get(session_id)
    now = time.time()
    if not expires_at or expires_at <= now:
        sessions.pop(session_id, None)
        return False

    sessions[session_id] = now + ADMIN_SESSION_TTL_SECONDS
    return True


def is_request_admin_authenticated(request: Request, session_id: str | None) -> bool:
    """Retorna se a request possui sessao admin valida."""
    return _is_session_valid(request, session_id)


def _register_login_failure(request: Request) -> None:
    """Registra falha e aplica janela de bloqueio apos varias tentativas."""
    failures = _get_login_failures(request)
    key = _client_key(request)
    now = time.time()
    data = failures.get(key, {"count": 0, "locked_until": 0})
    if data.get("locked_until", 0) <= now:
        data = {"count": data.get("count", 0) + 1, "locked_until": 0}
    else:
        data["count"] = data.get("count", 0) + 1
    if data["count"] >= ADMIN_LOGIN_MAX_ATTEMPTS:
        data["locked_until"] = now + ADMIN_LOGIN_LOCKOUT_SECONDS
    failures[key] = data


def _assert_login_allowed(request: Request) -> None:
    """Bloqueia tentativas de login durante lockout."""
    data = _get_login_failures(request).get(_client_key(request))
    if not data:
        return
    locked_until = data.get("locked_until", 0)
    if locked_until > time.time():
        raise HTTPException(
            status_code=429,
            detail="Muitas tentativas de login. Tente novamente mais tarde.",
        )


def _clear_login_failures(request: Request) -> None:
    """Limpa contador de falhas do cliente atual."""
    _get_login_failures(request).pop(_client_key(request), None)


async def require_admin_session(
    request: Request,
    bot_admin_session: str | None = Cookie(None, alias=ADMIN_SESSION_COOKIE),
):
    """Exige login do painel para acoes administrativas."""
    if not is_admin_password_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "Senha do painel nao configurada. Defina WEB_ADMIN_PASSWORD "
                "ou configure pelo terminal."
            ),
        )
    if not _is_session_valid(request, bot_admin_session):
        raise HTTPException(status_code=401, detail="Login do painel necessario.")
    return True


async def require_api_key(
    request: Request,
    x_api_key: str = Header(None),
    bot_admin_session: str | None = Cookie(None, alias=ADMIN_SESSION_COOKIE),
):
    """Valida X-API-Key e a sessao admin para rotas protegidas."""
    if x_api_key != API_KEY:
        raise HTTPException(
            status_code=401,
            detail="API Key invalida ou ausente. Inclua o header X-API-Key.",
        )
    await require_admin_session(request, bot_admin_session)
    return x_api_key


@router.post("/api/auth/login")
async def login(
    request: Request,
    response: Response,
    body: dict = Body(...),
):
    """Cria sessao admin do painel."""
    if not is_admin_password_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "Senha do painel nao configurada. Defina WEB_ADMIN_PASSWORD "
                "ou configure pelo terminal."
            ),
        )

    _assert_login_allowed(request)
    password = str(body.get("password") or "")
    if not verify_admin_password(password):
        _register_login_failure(request)
        raise HTTPException(status_code=401, detail="Senha invalida.")

    _clear_login_failures(request)
    session_id = secrets.token_urlsafe(32)
    _get_sessions(request)[session_id] = time.time() + ADMIN_SESSION_TTL_SECONDS
    response.set_cookie(
        ADMIN_SESSION_COOKIE,
        session_id,
        httponly=True,
        max_age=ADMIN_SESSION_TTL_SECONDS,
        path="/",
        samesite="lax",
        secure=request.url.scheme == "https",
    )
    return {"status": "success"}


@router.post("/api/auth/logout")
async def logout(
    request: Request,
    response: Response,
    bot_admin_session: str | None = Cookie(None, alias=ADMIN_SESSION_COOKIE),
):
    """Encerra a sessao admin atual."""
    if bot_admin_session:
        _get_sessions(request).pop(bot_admin_session, None)
    response.delete_cookie(ADMIN_SESSION_COOKIE, path="/")
    return {"status": "success"}


@router.get("/api/auth/status")
async def auth_status(
    request: Request,
    bot_admin_session: str | None = Cookie(None, alias=ADMIN_SESSION_COOKIE),
):
    """Retorna estado de autenticacao do painel."""
    return {
        "configured": is_admin_password_configured(),
        "authenticated": _is_session_valid(request, bot_admin_session),
    }


@router.get("/api/get_api_key")
async def get_api_key(
    request: Request,
    bot_admin_session: str | None = Cookie(None, alias=ADMIN_SESSION_COOKIE),
):
    """Return API key for local clients or authenticated admins."""
    client_host = request.client.host if request.client else ""
    is_local = client_host in ("127.0.0.1", "::1", "localhost")
    if not is_local and not _is_session_valid(request, bot_admin_session):
        raise HTTPException(status_code=403, detail="Acesso negado.")
    return {"api_key": API_KEY}
