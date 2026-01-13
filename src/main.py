import sys
import os
import threading
import json
import logging
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtCore import pyqtSignal, QObject, QThread, QTimer, Qt
from dotenv import load_dotenv, set_key

from ui.overlay import StatusOverlay
from ui.settings_dialog import SettingsDialog
from core.audio_recorder import AudioRecorder
from core.hotkey_manager import HotkeyManager
from core.api_client import ApiClient
from core.text_process import TextProcessor
from core.config import get_openai_key, load_settings, save_settings_file, setup_logging, get_model_config
from core.locale_manager import tr, set_language, get_current_language

logger = logging.getLogger(__name__)

class ProcessingWorker(QThread):
    finished = pyqtSignal(str, str) # raw_text, corrected_text
    
    def __init__(self, api_client: ApiClient, audio_path: str, history: list, system_prompt: str, context_chars: int):
        super().__init__()
        self.api_client = api_client
        self.audio_path = audio_path
        self.history = history
        self.system_prompt = system_prompt
        self.context_chars = context_chars
        
    def run(self):
        try:
            logger.info("Transcribing audio...")
            raw_text = self.api_client.transcribe(self.audio_path)
            
            if raw_text and not raw_text.startswith("Error"):
                logger.info(f"Transcription result: {raw_text[:50]}...")
                corrected_text = self.api_client.correct_text(raw_text, self.history, self.system_prompt, self.context_chars)
                self.finished.emit(raw_text, corrected_text)
            else:
                self.finished.emit("", raw_text if raw_text else tr("error_transcription"))
        except Exception as e:
            logger.exception("Worker thread error")
            self.finished.emit("", tr("error_unknown"))

class AppController(QObject):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.settings = load_settings()
        self.api_key = get_openai_key()
        self.is_processing = False
        
        # Initialize Locale
        lang = self.settings.get("app_language", "ru")
        set_language(lang)
        
        # UI Components
        self.overlay = StatusOverlay()
        
        # API & Logic
        self.api_client = ApiClient(self.api_key)
        self.audio_recorder = AudioRecorder()
        
        # Activation Hotkey
        self.hotkey_manager = HotkeyManager(self.settings.get("hotkey", "ctrl+alt+s"))
        self.hotkey_manager.triggered.connect(self.toggle_recording)
        self.hotkey_manager.start()

        # Cancellation Hotkey
        self.cancel_hotkey_manager = HotkeyManager(self.settings.get("cancel_hotkey", "ctrl+alt+x"))
        self.cancel_hotkey_manager.triggered.connect(self.cancel_operation)
        self.cancel_hotkey_manager.start()
        
        self.history = []

        # System Tray
        self.tray_icon = QSystemTrayIcon(QIcon("assets/icon.png"), self.app)
        self.update_tray_menu()
        self.tray_icon.show()
        
        self.overlay.show_message(tr("ready"), duration=2000)
        logger.info(f"Application started (Language: {lang})")

    def update_tray_menu(self):
        self.tray_icon.setToolTip(tr("app_name"))
        menu = QMenu()
        
        settings_action = QAction(tr("menu_settings"), self.app)
        settings_action.triggered.connect(self.open_settings)
        
        quit_action = QAction(tr("menu_quit"), self.app)
        quit_action.triggered.connect(self.quit_app)
        
        menu.addAction(settings_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray_icon.setContextMenu(menu)

    def open_settings(self):
        current_lang = get_current_language()
        dialog = SettingsDialog(
            None, 
            self.settings.get("hotkey", "ctrl+alt+s"), 
            self.api_key, 
            current_lang,
            self.settings.get("cancel_hotkey", "ctrl+alt+x")
        )
        
        if dialog.exec():
            changes = False
            
            # Update Hotkey
            if dialog.new_hotkey != self.settings.get("hotkey"):
                self.settings["hotkey"] = dialog.new_hotkey
                self.hotkey_manager.update_hotkey(dialog.new_hotkey)
                logger.info(f"Hotkey updated to {dialog.new_hotkey}")
                changes = True

            # Update Cancel Hotkey
            if dialog.new_cancel_hotkey != self.settings.get("cancel_hotkey", ""):
                self.settings["cancel_hotkey"] = dialog.new_cancel_hotkey
                self.cancel_hotkey_manager.update_hotkey(dialog.new_cancel_hotkey)
                logger.info(f"Cancel Hotkey updated to {dialog.new_cancel_hotkey}")
                changes = True
                
            # Update API Key
            if dialog.new_api_key != self.api_key:
                env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
                if not os.path.exists(env_path):
                     with open(env_path, "w") as f: f.write("")
                set_key(env_path, "OPENAI_API_KEY", dialog.new_api_key)
                self.api_key = dialog.new_api_key
                self.api_client = ApiClient(self.api_key)
                logger.info("API Key updated")
                changes = True
                
            # Update Language
            if dialog.new_lang != current_lang:
                self.settings["app_language"] = dialog.new_lang
                set_language(dialog.new_lang)
                self.update_tray_menu() # Refresh tray menu
                logger.info(f"Language updated to {dialog.new_lang}")
                changes = True

            if changes:
                save_settings_file(self.settings)
                self.overlay.show_message(tr("settings_saved"), duration=2000)

    def cancel_operation(self):
        logger.info("Cancellation requested.")
        
        if self.audio_recorder.recording:
            # Stop recording without processing
            path = self.audio_recorder.stop_recording()
            logger.info(f"Recording cancelled. File {path} discarded/ignored.")
            self.overlay.show_message(tr("canceled"), duration=1000)
            
        elif self.is_processing:
            # Invalidate current processing
            # We can't kill the thread easily, but we can ignore result.
            # Best way: set a flag or disconnect signal
            try:
                self.worker.finished.disconnect(self.on_processing_finished)
            except:
                pass
            self.is_processing = False
            self.overlay.show_message(tr("canceled"), duration=1000)
            logger.info("Processing cancelled.")

    def toggle_recording(self):
        if self.is_processing:
            logger.warning("Already processing, ignore toggle")
            return

        if self.audio_recorder.recording:
            # Stop
            audio_path = self.audio_recorder.stop_recording()
            if audio_path:
                self.overlay.show_message(tr("recognizing"), animate=True)
                self.process_audio(audio_path)
            else:
                self.overlay.hide_overlay()
                logger.warning("Recording stopped but no audio path returned")
        else:
            # Start
            self.audio_recorder.start_recording()
            self.overlay.show_message(tr("recording_started"))

    def process_audio(self, audio_path):
        self.is_processing = True
        prompt = self.settings.get("system_prompt", "")
        context_chars = self.settings.get("context_window_chars", 3000)
        self.worker = ProcessingWorker(self.api_client, audio_path, self.history, prompt, context_chars)
        self.worker.finished.connect(self.on_processing_finished)
        self.worker.start()
        
    def on_processing_finished(self, raw_text, corrected_text):
        self.is_processing = False
        self.overlay.hide_overlay()
        
        if raw_text and not corrected_text.startswith("Error"):
            self.overlay.show_message(tr("done"), duration=1000)
            
            # History
            self.history.append({'text': corrected_text, 'is_bot': True})
            
            TextProcessor.paste_text(corrected_text)
            logger.info("Processing finished successfully")
        else:
            # Show specific error from worker
            # Check if it is a localized error key or raw error
            # For now, worker returns localized strings for known errors
            error_text = corrected_text 
            
            # If startswith Error: and not known key... simplistic check
            # Realistically, api_client should return keys or we map them here. 
            # But api_client string returns are mixed.
            # Let's map common ones if they match exactly
            
            map_errors = {
                "Error: Invalid API Key": "error_auth",
                "Error: Rate Limit Exceeded": "error_rate_limit",
                "Error: No Connection": "error_connection",
                "Error: Transcription Failed": "error_transcription",
                "Error: Unknown": "error_unknown"
            }
            
            if error_text in map_errors:
                error_text = tr(map_errors[error_text])
            
            self.overlay.show_message(error_text, duration=3000)
            logger.error(f"Processing failed: {error_text}")
            
    def quit_app(self):
        logger.info("Quitting application")
        self.hotkey_manager.stop()
        self.cancel_hotkey_manager.stop()
        self.app.quit()

def main():
    setup_logging()
    load_dotenv()
    
    # Set AppUserModelID for Windows Taskbar Icon
    import ctypes
    myappid = 'sflow.recognition.app.1.0' # arbitrary string
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(QIcon("assets/icon.png"))
    
    controller = AppController(app)
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
