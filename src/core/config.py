import os
import json
import sys

SETTINGS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "settings.json")

def load_settings():
    try:
        if os.path.exists(SETTINGS_PATH):
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading settings: {e}")
    return {}

def get_openai_key():
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        print("Warning: OPENAI_API_KEY not found in environment variables.")
    return key
