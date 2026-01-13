import os
import json
import sys
import logging

def get_app_dir():
    """Returns the directory where the executable or script is located."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller."""
    if getattr(sys, 'frozen', False):
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    return os.path.join(base_path, relative_path)

SETTINGS_PATH = os.path.join(get_app_dir(), "settings.json")
LOG_PATH = os.path.join(get_app_dir(), "app.log")
APP_VERSION = "1.4.0"

# Retry Configuration
MAX_RETRIES = 3
RETRY_DELAY = 1.0

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOG_PATH, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )

def load_settings():
    try:
        if os.path.exists(SETTINGS_PATH):
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading settings: {e}")
    return {}

def save_settings_file(settings):
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving settings: {e}")
        return False

def get_openai_key():
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        print("Warning: OPENAI_API_KEY not found in environment variables.")
    return key

def get_model_config(settings=None):
    if settings is None:
        settings = load_settings()
    return {
        "transcription_model": settings.get("transcription_model", "whisper-1"),
        "correction_model": settings.get("correction_model", "gpt-4o-mini")
    }
