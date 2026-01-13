import pyperclip
import keyboard
import time

class TextProcessor:
    @staticmethod
    def paste_text(text):
        if not text:
            return
            
        # Save current clipboard
        original_clipboard = pyperclip.paste()
        
        # Copy new text
        pyperclip.copy(text)
        
        # Simulating Ctrl+V
        # Wait a bit for clipboard update
        time.sleep(0.1)
        keyboard.send('ctrl+v')
        
        # Optional: Restore clipboard? 
        # Usually better to leave the pasted text in clipboard so user can paste again if needed.
