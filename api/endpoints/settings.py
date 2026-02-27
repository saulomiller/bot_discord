"""endpoints de configuracao como token, idioma e inicializacao."""

import asyncio
import logging
import os

import discord
from fastapi import APIRouter, Body, Depends, HTTPException, Request

from api.endpoints.models import LanguageRequest
from api.endpoints.security import require_api_key
from config import save_token_to_json
from utils.i18n import I18n

router = APIRouter()


@router.post("/api/set_token")
async def set_token(request: Request, body: dict = Body(...), _: str = Depends(require_api_key)):
    """Set Discord bot token."""
    bot = request.app.state.bot
    token = body.get("token")
    if not token or len(token) < 50:
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
            "message": "Token atualizado. Reinicie o bot manualmente se ele não voltar.",
        }
    except Exception as exc:
        logging.error(f"Erro ao salvar token via API: {exc}")
        raise HTTPException(status_code=500, detail="Falha ao salvar o token.") from exc


@router.post("/api/restart")
async def restart_bot(request: Request, _: str = Depends(require_api_key)):
    """Reinicia bot."""
    bot = request.app.state.bot
    try:
        logging.info("Reiniciando bot via API...")
        if bot.is_ready() or not bot.is_closed():
            await bot.close()
        return {"status": "success", "message": "Bot reiniciando..."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Falha ao reiniciar o bot.") from exc


@router.get("/api/settings/language")
async def get_language():
    """Retorna language."""
    return {"language": I18n.get_instance().language}


@router.post("/api/settings/language")
async def set_language(request: LanguageRequest):
    """Define language."""
    success = I18n.get_instance().save_language(request.language)
    if success:
        return {"status": "success", "message": f"Idioma alterado para {request.language}"}
    raise HTTPException(status_code=500, detail="Erro ao salvar idioma.")


@router.post("/api/shutdown")
async def shutdown(request: Request, _: str = Depends(require_api_key)):
    """Executa a rotina de shutdown."""
    bot = request.app.state.bot
    asyncio.ensure_future(bot.close())
    return {"status": "success", "message": "Bot desligando..."}


@router.post("/api/startup")
async def startup(request: Request, body: dict = Body(default={}), _: str = Depends(require_api_key)):
    """Executa a rotina de startup."""
    bot = request.app.state.bot
    token = body.get("token") or os.getenv("DISCORD_TOKEN")
    if not token:
        raise HTTPException(status_code=400, detail="Nenhum token fornecido ou configurado.")
    if bot.is_ready():
        return {"status": "success", "message": "Bot já está online."}

    try:
        logging.info("Iniciando bot via API...")

        async def run_bot_task():
            try:
                await bot.start(token)
            except discord.errors.LoginFailure as exc:
                logging.error(f"Falha de autenticação do Discord: {exc}")
            except Exception as exc:
                logging.error(f"Erro ao iniciar o bot via API: {exc}")

        asyncio.create_task(run_bot_task())
        return {"status": "success", "message": "Bot inicializando..."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Falha ao inicializar o bot.") from exc

