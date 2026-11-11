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
ACCESS_FILE = BASE_DIR / "bobrik" / "access.json"

os.makedirs(VOICE_DIR, exist_ok=True)
os.makedirs(DATABASES_DIR, exist_ok=True)


def load_api_keys():
    keys = []
    i = 1
    while os.getenv(f"OPENROUTER_API_KEY_{i}"):
        keys.append(os.environ[f"OPENROUTER_API_KEY_{i}"].strip())
        i += 1
    return keys


# API
API_KEYS = load_api_keys()
if not API_KEYS:
    raise RuntimeError("Не найдено ни одного OPENROUTER_API_KEY_1, OPENROUTER_API_KEY_2, ... в .env")

MODELS_API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODELS_MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"

VISION_MODEL = "minimax/minimax-h3-image-highspeed"

# TTS silero или api
TTS_MODE = "silero"

TTS_API_URL = "https://openrouter.ai/api/v1/audio/speech"
TTS_MODEL = "fish-audio/s2.1-pro-free:free"

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
