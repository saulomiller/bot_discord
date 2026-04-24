"""endpoints de configuracao como token, idioma e inicializacao."""

import asyncio
import logging
import os

import discord
from fastapi import APIRouter, Body, Depends, HTTPException, Request

from api.endpoints.models import LanguageRequest
from api.endpoints.security import require_api_key
from config import is_valid_token_value, load_token_from_json, save_token_to_json
from utils.i18n import I18n

router = APIRouter()


def _resolve_runtime_token(payload_token: str | None = None) -> str | None:
    """Resolve token a partir do payload, ambiente e arquivo persistido."""
    token = (payload_token or "").strip()
    if token:
        return token

    env_token = (os.getenv("DISCORD_TOKEN") or "").strip()
    if env_token:
        return env_token

    file_token = (load_token_from_json() or "").strip()
    return file_token or None


def _queue_bot_start(
    request: Request,
    bot,
    token: str,
    *,
    restart_first: bool,
) -> asyncio.Task:
    """Agenda start do bot e evita tarefas concorrentes de inicializacao."""
    existing_task = getattr(request.app.state, "bot_start_task", None)
    if existing_task and not existing_task.done():
        return existing_task

    async def run_bot_task():
        try:
            if restart_first and (bot.is_ready() or not bot.is_closed()):
                await bot.close()
                await asyncio.sleep(1)
            await bot.start(token)
        except discord.errors.LoginFailure as exc:
            logging.error(f"Falha de autenticação do Discord: {exc}")
        except discord.errors.PrivilegedIntentsRequired as exc:
            logging.error(f"Intents privilegiadas não habilitadas: {exc}")
        except Exception as exc:
            logging.error(f"Erro ao iniciar o bot via API: {exc}")

    task = asyncio.create_task(run_bot_task())
    request.app.state.bot_start_task = task

    def clear_task(_: asyncio.Task) -> None:
        if getattr(request.app.state, "bot_start_task", None) is task:
            request.app.state.bot_start_task = None

    task.add_done_callback(clear_task)
    return task


@router.post("/api/set_token")
async def set_token(
    request: Request, body: dict = Body(...), _: str = Depends(require_api_key)
):
    """Set Discord bot token."""
    bot = request.app.state.bot
    token = body.get("token")
    if not is_valid_token_value(token):
        raise HTTPException(status_code=400, detail="Token não fornecido.")

    try:
        save_token_to_json(token)
        os.environ["DISCORD_TOKEN"] = token
        logging.info("Token do Discord foi salvo/atualizado via API.")

        if bot.is_ready():
            logging.info("Bot já está online. Tentando reiniciar com o novo token...")
            await bot.close()
            await asyncio.sleep(1)

        return {
            "status": "success",
            "message": (
                "Token atualizado. Reinicie o bot manualmente se ele não voltar."
            ),
        }
    except Exception as exc:
        logging.error(f"Erro ao salvar token via API: {exc}")
        raise HTTPException(status_code=500, detail="Falha ao salvar o token.") from exc


@router.post("/api/settings/token")
async def set_settings_token(
    request: Request, body: dict = Body(...), _: str = Depends(require_api_key)
):
    """Salva o token Discord e opcionalmente inicia o bot."""
    bot = request.app.state.bot
    token = body.get("token")
    should_start = bool(body.get("start_bot", True))
    if not is_valid_token_value(token):
        raise HTTPException(status_code=400, detail="Token invalido.")

    try:
        save_token_to_json(token)
        os.environ["DISCORD_TOKEN"] = token
        logging.info("Token do Discord foi salvo/atualizado via setup web.")

        if should_start and not bot.is_ready():
            existing_task = getattr(request.app.state, "bot_start_task", None)
            if not existing_task or existing_task.done():
                _queue_bot_start(request, bot, token, restart_first=False)

        return {
            "status": "success",
            "message": (
                "Token salvo. O bot esta inicializando."
                if should_start
                else "Token salvo."
            ),
        }
    except Exception as exc:
        logging.error(f"Erro ao salvar token via setup: {exc}")
        raise HTTPException(status_code=500, detail="Falha ao salvar o token.") from exc


@router.post("/api/restart")
async def restart_bot(request: Request, _: str = Depends(require_api_key)):
    """Reinicia bot."""
    bot = request.app.state.bot
    token = _resolve_runtime_token()
    if not token:
        raise HTTPException(
            status_code=400,
            detail="Nenhum token configurado para reiniciar o bot.",
        )

    existing_task = getattr(request.app.state, "bot_start_task", None)
    if existing_task and not existing_task.done():
        return {"status": "success", "message": "Bot já está inicializando..."}

    try:
        logging.info("Reiniciando bot via API...")
        _queue_bot_start(request, bot, token, restart_first=True)
        return {"status": "success", "message": "Bot reiniciando..."}
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail="Falha ao reiniciar o bot."
        ) from exc


@router.get("/api/settings/language")
async def get_language(_: str = Depends(require_api_key)):
    """Retorna language."""
    return {"language": I18n.get_instance().language}


@router.post("/api/settings/language")
async def set_language(
    body: LanguageRequest,
    _: str = Depends(require_api_key),
):
    """Define language."""
    success = I18n.get_instance().save_language(body.language)
    if success:
        return {
            "status": "success",
            "message": f"Idioma alterado para {body.language}",
        }
    raise HTTPException(status_code=500, detail="Erro ao salvar idioma.")


@router.post("/api/shutdown")
async def shutdown(request: Request, _: str = Depends(require_api_key)):
    """Executa a rotina de shutdown."""
    bot = request.app.state.bot
    pending_start = getattr(request.app.state, "bot_start_task", None)
    if pending_start and not pending_start.done():
        pending_start.cancel()
        request.app.state.bot_start_task = None
    asyncio.ensure_future(bot.close())
    return {"status": "success", "message": "Bot desligando..."}


@router.post("/api/startup")
async def startup(
    request: Request,
    body: dict = Body(default={}),
    _: str = Depends(require_api_key),
):
    """Executa a rotina de startup."""
    bot = request.app.state.bot
    token = _resolve_runtime_token(body.get("token"))
    if not token:
        raise HTTPException(
            status_code=400, detail="Nenhum token fornecido ou configurado."
        )
    if bot.is_ready():
        return {"status": "success", "message": "Bot já está online."}

    existing_task = getattr(request.app.state, "bot_start_task", None)
    if existing_task and not existing_task.done():
        return {"status": "success", "message": "Bot já está inicializando..."}

    try:
        logging.info("Iniciando bot via API...")
        _queue_bot_start(request, bot, token, restart_first=False)
        return {"status": "success", "message": "Bot inicializando..."}
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail="Falha ao inicializar o bot."
        ) from exc
