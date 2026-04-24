"""define configuracoes globais, paths e persistencia de credenciais."""

import os
import json
import logging
import hashlib
import hmac
import secrets
from dotenv import load_dotenv

# Carrega variáveis do arquivo .env (se existir) para o ambiente
load_dotenv()

# Configuração do logging
logging.getLogger("uvicorn.error").propagate = False
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# --- Constantes e Caminhos ---
DATA_DIR = "data"
TOKEN_FILE = os.path.join(DATA_DIR, "token.json")
LEGACY_TOKEN_FILE = "token.json"
TOKEN_KEYS = ("DISCORD_TOKEN", "token")
PLACEHOLDER_TOKENS = {
    "SEU_TOKEN_AQUI",
    "SEU_TOKEN_DO_DISCORD_AQUI",
    "your_discord_token_here",
}
ADMIN_AUTH_FILE = os.path.join(DATA_DIR, "auth.json")
ADMIN_PASSWORD_ENV = "WEB_ADMIN_PASSWORD"
ADMIN_SESSION_COOKIE = "bot_admin_session"
ADMIN_SESSION_TTL_SECONDS = 60 * 60 * 24
ADMIN_LOGIN_MAX_ATTEMPTS = 5
ADMIN_LOGIN_LOCKOUT_SECONDS = 5 * 60
PLAYLIST_DIR = os.path.join(DATA_DIR, "playlist")
RADIOS_FILE = os.path.join(DATA_DIR, "radios.json")
SOUNDBOARD_DIR = os.path.join(DATA_DIR, "soundboard")
SOUNDBOARD_METADATA_FILE = os.path.join(SOUNDBOARD_DIR, "metadata.json")
ALLOWED_AUDIO_EXTENSIONS = (".mp3", ".wav", ".ogg", ".m4a", ".webm")
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
    """Carrega o token do arquivo data/token.json ou do token.json legado."""
    for token_file in (TOKEN_FILE, LEGACY_TOKEN_FILE):
        if not os.path.exists(token_file):
            continue
        try:
            with open(token_file, "r") as f:
                data = json.load(f)
            for key in TOKEN_KEYS:
                token = data.get(key)
                if token:
                    if token_file == LEGACY_TOKEN_FILE:
                        logging.warning(
                            "Token carregado de token.json legado. "
                            "Prefira salvar em data/token.json ou .env."
                        )
                    return token
        except (json.JSONDecodeError, IOError) as e:
            logging.error(f"Erro ao ler {token_file}: {e}")
    return None


def save_token_to_json(token: str):
    """Salva o token no arquivo data/token.json."""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    with open(TOKEN_FILE, "w") as f:
        json.dump({"DISCORD_TOKEN": token}, f, indent=2)


def is_valid_token_value(token: str | None) -> bool:
    """Retorna se o token parece configurado, sem validar login no Discord."""
    clean = (token or "").strip()
    return bool(clean and clean not in PLACEHOLDER_TOKENS and len(clean) >= 50)


def resolve_configured_token() -> str | None:
    """Resolve token persistido para decidir o fluxo inicial da interface."""
    token = load_token_from_json()
    if not token:
        token = os.getenv("DISCORD_TOKEN")
    return token if is_valid_token_value(token) else None


# --- Autenticacao do painel web ---


def _hash_password(password: str, *, salt: str | None = None) -> dict:
    """Gera hash PBKDF2-SHA256 para senha do painel."""
    iterations = 260_000
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations
    ).hex()
    return {
        "algorithm": "pbkdf2_sha256",
        "iterations": iterations,
        "salt": salt,
        "hash": digest,
    }


def _load_admin_auth() -> dict | None:
    """Carrega metadados de autenticacao do painel."""
    if not os.path.exists(ADMIN_AUTH_FILE):
        return None
    try:
        with open(ADMIN_AUTH_FILE, "r") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, IOError) as e:
        logging.error(f"Erro ao ler {ADMIN_AUTH_FILE}: {e}")
        return None


def save_admin_password(password: str) -> None:
    """Salva a senha admin do painel como hash."""
    if not password or len(password) < 8:
        raise ValueError("A senha do painel deve ter pelo menos 8 caracteres.")
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    with open(ADMIN_AUTH_FILE, "w") as f:
        json.dump(_hash_password(password), f, indent=2)


def is_admin_password_configured() -> bool:
    """Retorna se existe senha admin via .env ou arquivo."""
    return bool((os.getenv(ADMIN_PASSWORD_ENV) or "").strip() or _load_admin_auth())


def verify_admin_password(password: str) -> bool:
    """Valida a senha admin contra .env ou hash persistido."""
    submitted = password or ""
    env_password = os.getenv(ADMIN_PASSWORD_ENV)
    if env_password:
        return hmac.compare_digest(submitted, env_password)

    data = _load_admin_auth()
    if not data or data.get("algorithm") != "pbkdf2_sha256":
        return False

    try:
        salt = str(data["salt"])
        iterations = int(data["iterations"])
        expected = str(data["hash"])
        digest = hashlib.pbkdf2_hmac(
            "sha256", submitted.encode("utf-8"), bytes.fromhex(salt), iterations
        ).hex()
        return hmac.compare_digest(digest, expected)
    except (KeyError, TypeError, ValueError):
        return False


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
