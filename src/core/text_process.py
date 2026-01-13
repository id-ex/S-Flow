import pyperclip
import keyboard
import time
import logging

logger = logging.getLogger(__name__)

class TextProcessor:
    @staticmethod
    def paste_text(text: str):
        if not text:
            return
            
        try:
            # Save current clipboard could be risky if it fails, but let's try
            # original_clipboard = pyperclip.paste()
            
            # Copy new text
            pyperclip.copy(text)
            
            # Simulating Ctrl+V
            # Wait a bit for clipboard update. 
            # 0.1 is usually enough, but 0.2 is safer for slower apps.
            time.sleep(0.2) 
            keyboard.send('ctrl+v')
            logger.info("Text pasted via keyboard simulation.")
            
        except Exception as e:
            logger.error(f"Failed to paste text: {e}")
