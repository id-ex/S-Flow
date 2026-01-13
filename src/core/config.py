import os
import json
import sys
import logging

SETTINGS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "settings.json")
LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "app.log")

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
