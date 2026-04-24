"""ponto de entrada que inicia o bot Discord e a API FastAPI."""

import discord
from discord.ext import commands
import logging
import asyncio
import os
import sys
import uvicorn
from getpass import getpass

from config import (
    ADMIN_SESSION_COOKIE,
    is_valid_token_value,
    is_admin_password_configured,
    resolve_configured_token,
    save_admin_password,
    save_token_to_json,
)
from api.routes import router as api_router
from api.endpoints.security import is_request_admin_authenticated
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from fastapi import Cookie, Request

# Inicializar FastAPI
app = FastAPI(
    title="Discord Music Bot API",
    description="API para controlar o bot de música do Discord.",
    version="1.0.0",
)

# Servir arquivos estáticos
if not os.path.exists("static"):
    os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def read_index(
    request: Request,
    bot_admin_session: str | None = Cookie(None, alias=ADMIN_SESSION_COOKIE),
):
    """Retorna a pagina principal do dashboard web."""
    if not is_request_admin_authenticated(request, bot_admin_session):
        return RedirectResponse("/login")
    if not resolve_configured_token():
        return RedirectResponse("/setup")
    if os.path.exists("static/index.html"):
        return FileResponse("static/index.html")
    return {
        "message": (
            "Interface web não encontrada. Verifique se o arquivo "
            "static/index.html existe."
        )
    }


@app.get("/login")
async def read_login(
    request: Request,
    bot_admin_session: str | None = Cookie(None, alias=ADMIN_SESSION_COOKIE),
):
    """Retorna tela de login do painel."""
    if is_request_admin_authenticated(request, bot_admin_session):
        return RedirectResponse("/" if resolve_configured_token() else "/setup")
    if os.path.exists("static/login.html"):
        return FileResponse("static/login.html")
    return {"message": "Tela de login nao encontrada."}


@app.get("/setup")
async def read_setup(
    request: Request,
    bot_admin_session: str | None = Cookie(None, alias=ADMIN_SESSION_COOKIE),
):
    """Retorna tela de configuracao inicial do token."""
    if not is_request_admin_authenticated(request, bot_admin_session):
        return RedirectResponse("/login")
    if os.path.exists("static/setup.html"):
        return FileResponse("static/setup.html")
    return {"message": "Tela de setup nao encontrada."}


# Incluir rotas da API
app.include_router(api_router)

# Configurar intents
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True


class MusicBot(commands.Bot):
    """Bot principal com registro de players por servidor."""

    def __init__(self):
        """Inicializa o bot e o registro de players por servidor."""
        super().__init__(command_prefix="!", intents=intents)
        self.players = {}  # Dict[guild_id, MusicPlayer]

    async def setup_hook(self):
        """Carrega cogs e sincroniza os comandos slash no startup."""
        # Carregar Cogs
        await self.load_extension("cogs.music")
        await self.load_extension("cogs.soundboard")

        # Sincronizar comandos slash
        try:
            synced = await self.tree.sync()
            logging.info(f"Sincronizados {len(synced)} comandos slash")
        except Exception as e:
            logging.error(f"Erro ao sincronizar comandos: {e}")

    async def on_ready(self):
        """Registra no log quando a conexao com o Discord estiver pronta."""
        logging.info(f"O bot fez login como: {self.user}")

    async def on_command_error(self, ctx, error):
        """Centraliza tratamento de erro para comandos prefixados."""
        if isinstance(error, commands.errors.CommandNotFound):
            pass
        else:
            logging.error(f"Erro em comando: {error}")


# Inicializar o bot
bot = MusicBot()

# Passar a instância do bot para a API
app.state.bot = bot


def prompt_admin_password_terminal():
    """Configura a senha admin do painel via terminal quando possivel."""
    if is_admin_password_configured():
        return

    if not sys.stdin.isatty():
        logging.warning(
            "Senha do painel nao configurada. Em Docker/headless, defina "
            "WEB_ADMIN_PASSWORD no .env para proteger o painel web."
        )
        return

    print("\n" + "=" * 60)
    print("PAINEL WEB - CONFIGURACAO DE SENHA ADMIN")
    print("=" * 60)
    print("Nenhuma senha do painel web foi encontrada.")
    print("Defina uma senha para proteger o dashboard em http://localhost:8000.")
    print("Em Docker/headless, use WEB_ADMIN_PASSWORD no arquivo .env.")

    try:
        choice = input("\nDefinir senha agora? (s/N): ").strip().lower()
    except (EOFError, OSError):
        logging.warning(
            "Ambiente nao interativo detectado. Defina WEB_ADMIN_PASSWORD "
            "no .env para proteger o painel web."
        )
        return

    if choice not in ("s", "sim", "y", "yes"):
        logging.warning(
            "Senha do painel nao configurada. A interface web exigira "
            "WEB_ADMIN_PASSWORD ou nova configuracao pelo terminal."
        )
        return

    for _ in range(3):
        try:
            password = getpass("Senha do painel (min. 8 caracteres): ")
            confirm = getpass("Confirme a senha: ")
        except (EOFError, OSError):
            return

        if password != confirm:
            logging.error("As senhas nao conferem.")
            continue
        try:
            save_admin_password(password)
            logging.info("Senha admin do painel salva em data/auth.json.")
            return
        except ValueError as exc:
            logging.error(str(exc))

    logging.warning("Senha do painel nao configurada apos 3 tentativas.")


def prompt_token_terminal():
    """Solicita token via terminal apenas em execucao interativa."""
    if not sys.stdin.isatty():
        logging.info(
            "Token do Discord nao configurado. Em Docker/headless, use "
            "DISCORD_TOKEN no .env ou configure pela interface web."
        )
        return None

    print("\n" + "=" * 60)
    print("DISCORD MUSIC BOT - CONFIGURACAO DE TOKEN")
    print("=" * 60)
    print("\nNenhum token valido encontrado no sistema.")
    print("Voce pode inserir o token agora ou configurar depois pela web.")
    print("\nInstrucoes para obter o token:")
    print("- Acesse: https://discord.com/developers/applications")
    print("- Clique em 'New Application'")
    print("- Va para 'Bot' e clique em 'Add Bot'")
    print("- Clique em 'Copy Token'")
    print("=" * 60)

    try:
        choice = input("\nInserir token agora? (s/N): ").strip().lower()
    except (EOFError, OSError):
        return None

    if choice not in ("s", "sim", "y", "yes"):
        logging.info(
            "Pulando token no terminal. Acesse http://localhost:8000 para "
            "configurar pela interface web."
        )
        return None

    try:
        token = input("\nCole o token do Discord: ").strip()
    except (EOFError, OSError):
        return None

    if is_valid_token_value(token):
        save_token_to_json(token)
        logging.info("Token salvo com sucesso.")
        return token

    logging.error("Token invalido ou muito curto.")
    return None


async def run_bot_and_api():
    """Inicia o bot do Discord e o servidor da API."""
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, prompt_admin_password_terminal)
    except Exception as e:
        logging.error(f"Erro ao configurar senha do painel: {e}")

    token = resolve_configured_token()

    # Se ainda não tem token, perguntar no terminal
    if not token or not token.strip():
        try:
            loop = asyncio.get_running_loop()
            token = await loop.run_in_executor(None, prompt_token_terminal)
        except Exception as e:
            logging.error(f"Erro ao solicitar token: {e}")

    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="warning")
    server = uvicorn.Server(config)

    # Inicia o servidor uvicorn em uma tarefa de fundo
    api_task = asyncio.create_task(server.serve())

    # Verifica se o token é válido antes de tentar iniciar o bot
    if is_valid_token_value(token):

        async def run_bot_safe():
            """Tenta iniciar o bot, mas não deixa a API morrer se falhar."""
            try:
                logging.info("Token do Discord encontrado. Iniciando o bot...")
                # Remover token do log para segurança
                await bot.start(token)
            except discord.errors.LoginFailure as e:
                logging.error(f"❌ Falha de autenticação do Discord: {e}")
                logging.warning(
                    "Token inválido. A API web continua rodando, mas o bot "
                    "está offline."
                )
                logging.warning(
                    "Acesse a interface web para configurar um token válido."
                )
            except discord.errors.PrivilegedIntentsRequired as e:
                logging.error(f"❌ Intents não habilitados no Developer Portal: {e}")
                logging.warning("📌 Acesse https://discord.com/developers/applications")
                logging.warning("📌 Habilite: Message Content Intent e Presence Intent")
                logging.warning(
                    "⏳ Aguardando token válido via interface web ou terminal..."
                )
            except Exception as e:
                logging.error(f"❌ Erro ao iniciar o bot: {e}")
                logging.warning(
                    "⏳ A API web continua rodando. Você pode tentar "
                    "novamente via interface web."
                )

        # Iniciar o bot em background, NÃO bloquear a API
        asyncio.create_task(run_bot_safe())
        # Apenas aguardarmos a API rodar - o bot roda independentemente
        await api_task
    else:
        logging.warning(
            "⏳ Nenhum token válido do Discord encontrado. A API web está "
            "rodando, mas o bot está offline."
        )
        logging.warning(
            "✨ Acesse a interface web (http://localhost:8000) para configurar o token."
        )
        await api_task


if __name__ == "__main__":
    try:
        asyncio.run(run_bot_and_api())
    except KeyboardInterrupt:
        logging.info("Bot finalizado pelo usuário.")
