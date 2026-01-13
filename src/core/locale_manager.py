import json
import os
import logging
from .config import load_settings

logger = logging.getLogger(__name__)

class LocaleManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LocaleManager, cls).__new__(cls)
            cls._instance.translations = {}
            cls._instance.current_lang = "ru"
            cls._instance.load_locale("ru")
        return cls._instance

    def load_locale(self, lang_code: str):
        self.current_lang = lang_code
        try:
            from .config import get_resource_path
            locale_path = get_resource_path(os.path.join("assets", "locales", f"{lang_code}.json"))
            if os.path.exists(locale_path):
                with open(locale_path, "r", encoding="utf-8") as f:
                    self.translations = json.load(f)
                logger.info(f"Loaded locale: {lang_code}")
            else:
                logger.error(f"Locale file not found: {locale_path}")
                # Fallback to empty or default?
                # Ideally load default (en or ru) if requested fails, but let's stick to current
        except Exception as e:
            logger.error(f"Failed to load locale {lang_code}: {e}")

    def tr(self, key: str) -> str:
        return self.translations.get(key, key)

# Global instance helper
_manager = LocaleManager()

def tr(key: str) -> str:
    return _manager.tr(key)

def set_language(lang_code: str):
    _manager.load_locale(lang_code)

def get_current_language() -> str:
    return _manager.current_lang
