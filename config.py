"""define configuracoes globais, paths e persistencia de credenciais."""

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
ALLOWED_AUDIO_EXTENSIONS = ('.mp3', '.wav', '.ogg', '.m4a', '.webm')
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

# --- Gerenciamento de API Key ---

API_KEY_FILE = os.path.join(DATA_DIR, "api_key.json")

def _load_or_generate_api_key() -> str:
    """Carrega a API key do arquivo ou gera uma nova."""
    import uuid
    if os.path.exists(API_KEY_FILE):
        try:
            with open(API_KEY_FILE, "r") as f:
                data = json.load(f)
                key = data.get("api_key")
                if key:
                    return key
        except (json.JSONDecodeError, IOError) as e:
            logging.error(f"Erro ao ler {API_KEY_FILE}: {e}")
    # Gerar nova key
    new_key = str(uuid.uuid4())
    try:
        with open(API_KEY_FILE, "w") as f:
            json.dump({"api_key": new_key}, f)
        logging.info(f"Nova API Key gerada e salva em {API_KEY_FILE}")
    except IOError as e:
        logging.error(f"Erro ao salvar API Key: {e}")
    return new_key

API_KEY = _load_or_generate_api_key()
