"""ponto de entrada que inicia o bot Discord e a API FastAPI."""

import discord
from discord.ext import commands
import logging
import asyncio
import os
import uvicorn
from config import load_token_from_json
from utils.helpers import prompt_token_terminal
from api.routes import router as api_router
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

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


@app.get("/", response_class=FileResponse)
async def read_index():
    """Retorna a pagina principal do dashboard web."""
    if os.path.exists("static/index.html"):
        return FileResponse("static/index.html")
    return {
        "message": "Interface web não encontrada. Verifique se o arquivo static/index.html existe."
    }


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


async def run_bot_and_api():
    """Inicia o bot do Discord e o servidor da API."""
    # Prioriza o token do token.json, depois do .env
    token = load_token_from_json()
    if not token:
        token = os.getenv("DISCORD_TOKEN")

    # Se ainda não tem token, perguntar no terminal
    if not token or not token.strip():
        try:
            loop = asyncio.get_running_loop()
            token = await loop.run_in_executor(None, prompt_token_terminal)
        except Exception as e:
            logging.error(f"Erro ao solicitar token: {e}")

    config = uvicorn.Config(
        app, host="0.0.0.0", port=8000, log_level="warning"
    )
    server = uvicorn.Server(config)

    # Inicia o servidor uvicorn em uma tarefa de fundo
    api_task = asyncio.create_task(server.serve())

    # Verifica se o token é válido antes de tentar iniciar o bot
    if (
        token
        and token.strip()
        and token
        not in [
            "SEU_TOKEN_AQUI",
            "SEU_TOKEN_DO_DISCORD_AQUI",
            "your_discord_token_here",
        ]
    ):

        async def run_bot_safe():
            """Tenta iniciar o bot, mas não deixa a API morrer se falhar"""
            try:
                logging.info("Token do Discord encontrado. Iniciando o bot...")
                # Remover token do log para segurança
                await bot.start(token)
            except discord.errors.LoginFailure as e:
                logging.error(f"❌ Falha de autenticação do Discord: {e}")
                logging.warning(
                    "Token inválido. A API web continua rodando, mas o bot está offline."
                )
                logging.warning(
                    "Acesse a interface web para configurar um token válido."
                )
            except discord.errors.PrivilegedIntentsRequired as e:
                logging.error(
                    f"❌ Intents não habilitados no Developer Portal: {e}"
                )
                logging.warning(
                    "📌 Acesse https://discord.com/developers/applications"
                )
                logging.warning(
                    "📌 Habilite: Message Content Intent e Presence Intent"
                )
                logging.warning(
                    "⏳ Aguardando token válido via interface web ou terminal..."
                )
            except Exception as e:
                logging.error(f"❌ Erro ao iniciar o bot: {e}")
                logging.warning(
                    "⏳ A API web continua rodando. Você pode tentar novamente via interface web."
                )

        # Iniciar o bot em background, NÃO bloquear a API
        bot_task = asyncio.create_task(run_bot_safe())
        # Apenas aguardarmos a API rodar - o bot roda independentemente
        await api_task
    else:
        logging.warning(
            "⏳ Nenhum token válido do Discord encontrado. A API web está rodando, mas o bot está offline."
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
