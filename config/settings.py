import os
from pathlib import Path

# directions
BASE_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = BASE_DIR / "models"
SILERO_MODELS_DIR = BASE_DIR / "silero_models"
VOICE_DIR = BASE_DIR / "bobrik" / "voice_responses"
DATABASES_DIR = BASE_DIR / "bobrik" / "DataBases"

os.makedirs(VOICE_DIR, exist_ok=True)
os.makedirs(DATABASES_DIR, exist_ok=True)

# API


# VISION_MODEL = "nvidia/nemotron-3.5-super-vl:free"
# VISION_MODEL = "dots-studio/dots-3-note-preview:free"
VISION_MODEL = "liquid/lfm-2.5-2.6b:free"

# TTS silero или api
TTS_MODE = "silero"

TTS_API_URL = "https://openrouter.ai/api/v1/audio/speech"
TTS_MODEL = "fish-audio/s2.1-pro-free:free"
TTS_API_KEY = MODELS_API_KEY

# BOT_TOKEN = '7834137663:AAEAU5Tgkfyjlm9ytkpGymq4wPgMp0lKmyU' # Первый
BOT_TOKEN = '7983667693:AAHDNSm7YFdzL2e6mwesrj0x-X2Z4gS-crs' # Второй

ADMIN_IDS = {5973554102, 5987155879}

NAME_PHRASES = [
    r"меня зовут (\w+)", r"можешь звать меня (\w+)", r"моё имя (\w+)",
    r"запомни меня, я (\w+)", r"запомни меня я (\w+)", r"запомни меня, меня зовут (\w+)",
    r"запомни меня меня зовут (\w+)", r"назови меня (\w+)", r"я представлюсь, я (\w+)", r"мое прозвище (\w+)",
    r"зовут меня (\w+)", r"вот моё имя (\w+)", r"записывай, я (\w+)"
    , r"прими меня как (\w+)", r"знай меня как (\w+)"
]