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

def set_autostart(enabled: bool):
    """Sets or removes the application from Windows startup registry."""
    import winreg
    app_name = "S-Flow"
    
    root_dir = get_app_dir()
    
    if getattr(sys, 'frozen', False):
        # We are running as an EXE
        app_path = f'"{sys.executable}"'
    else:
        # We are running as Python script. 
        # But if the user wants the "EXE" to start, we look for it.
        potential_exe_dist = os.path.join(root_dir, "dist", "S-Flow.exe")
        potential_exe_root = os.path.join(root_dir, "S-Flow.exe")
        
        if os.path.exists(potential_exe_dist):
            app_path = f'"{potential_exe_dist}"'
        elif os.path.exists(potential_exe_root):
            app_path = f'"{potential_exe_root}"'
        else:
            # Fallback to current python command if no EXE found
            main_script = os.path.join(root_dir, "src", "main.py")
            if os.path.exists(main_script):
                app_path = f'"{sys.executable}" "{main_script}"'
            else:
                app_path = f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}"'
    
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        if enabled:
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, app_path)
            logging.info(f"Autostart enabled: {app_path}")
        else:
            try:
                winreg.DeleteValue(key, app_name)
                logging.info("Autostart disabled")
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True
    except Exception as e:
        logging.error(f"Error updating registry for autostart: {e}")
        return False
