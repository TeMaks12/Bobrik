import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# directions
BASE_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = BASE_DIR / "models"
SILERO_MODELS_DIR = BASE_DIR / "silero_models"
VOICE_DIR = BASE_DIR / "bobrik" / "voice_responses"
DATABASES_DIR = BASE_DIR / "bobrik" / "DataBases"

os.makedirs(VOICE_DIR, exist_ok=True)
os.makedirs(DATABASES_DIR, exist_ok=True)

MODELS_LIST = [
    "deepseek-flash",
    "deepseek-v4-pro",
    "claude-sonnet-5-5",
    "glm-5",
    "grok-4.5",
    "gpt-5.4-mini",
    "kimi-k2",
    "mistral-medium",
    "gemini-3.5-flash",
]
MODEL_FILE = BASE_DIR / "bobrik" / "model.json"

def load_api_keys():
    keys = []
    i = 1
    while os.getenv(f"KLINCH_API_KEY_{i}"):
        keys.append(os.environ[f"KLINCH_API_KEY_{i}"].strip())
        i += 1
    return keys


# API
API_KEYS = load_api_keys()
if not API_KEYS:
    raise RuntimeError("Не найдено ни одного KLINCH_API_KEY_1, KLINCH_API_KEY_2, ... в .env")

API_BASE_URL = os.getenv("KLINCH_API_BASE_URL", "https://api.klinch.cloud/v1").rstrip("/")

MODELS_API_URL = f"{API_BASE_URL}/chat/completions"
MODELS_MODEL = "deepseek-flash"

VISION_MODEL = "deepseek-flash"

# TTS silero или api
TTS_MODE = "silero"

TTS_API_URL = f"{API_BASE_URL}/audio/speech"
TTS_MODEL = "tts-1"

BOT_TOKEN = os.environ["BOT_TOKEN"]

# owner
OWNER_ID = int(os.environ["OWNER_ID"])
OWNER_NAME = os.environ["OWNER_NAME"]
OWNER_USERNAME = "@" + os.environ["OWNER_USERNAME"].lstrip("@")
DENIED_TEXT = "Ты не можешь пользоваться ботом"

ADMIN_IDS = {12345678}

NAME_PHRASES = [
    r"меня зовут (\w+)", r"можешь звать меня (\w+)", r"моё имя (\w+)",
    r"запомни меня, я (\w+)", r"запомни меня я (\w+)", r"запомни меня, меня зовут (\w+)",
    r"запомни меня меня зовут (\w+)", r"назови меня (\w+)", r"я представлюсь, я (\w+)", r"мое прозвище (\w+)",
    r"зовут меня (\w+)", r"вот моё имя (\w+)", r"записывай, я (\w+)"
    , r"прими меня как (\w+)", r"знай меня как (\w+)"
]
