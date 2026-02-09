import os
import json
import logging
from dotenv import load_dotenv

# Carrega variáveis do arquivo .env (se existir) para o ambiente
load_dotenv()

# Configuração do logging
logging.getLogger("uvicorn.error").propagate = False
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# --- Constantes e Caminhos ---
DATA_DIR = "data"
TOKEN_FILE = os.path.join(DATA_DIR, "token.json")
PLAYLIST_DIR = os.path.join(DATA_DIR, "playlist")
RADIOS_FILE = os.path.join(DATA_DIR, "radios.json")
SOUNDBOARD_DIR = os.path.join(DATA_DIR, "soundboard")
SOUNDBOARD_METADATA_FILE = os.path.join(SOUNDBOARD_DIR, "metadata.json")
FFMPEG_PATH = "ffmpeg"

# Garantir que os diretórios existem
for directory in [DATA_DIR, PLAYLIST_DIR, SOUNDBOARD_DIR]:
    if not os.path.exists(directory):
        try:
            os.makedirs(directory)
            logging.info(f"Diretório '{directory}' criado com sucesso")
        except Exception as e:
            logging.error(f"Erro ao criar diretório '{directory}': {e}")

# --- Gerenciamento de Token ---

def load_token_from_json():
    """Carrega o token do arquivo data/token.json."""
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r") as f:
                data = json.load(f)
                return data.get("DISCORD_TOKEN")
        except (json.JSONDecodeError, IOError) as e:
            logging.error(f"Erro ao ler {TOKEN_FILE}: {e}")
            return None
    return None

def save_token_to_json(token: str):
    """Salva o token no arquivo data/token.json."""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    with open(TOKEN_FILE, "w") as f:
        json.dump({"DISCORD_TOKEN": token}, f)
