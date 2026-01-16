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
from core.config import get_openai_key, load_settings, save_settings_file, setup_logging, get_model_config, get_resource_path, get_app_dir, set_autostart
from core.locale_manager import tr, set_language, get_current_language

logger = logging.getLogger(__name__)

class ProcessingWorker(QThread):
    finished = pyqtSignal(str, str) # raw_text, corrected_text
    
    def __init__(self, api_client: ApiClient, audio_path: str, history: list, system_prompt: str, context_chars: int, user_context: str = "", is_translation: bool = False):
        super().__init__()
        self.api_client = api_client
        self.audio_path = audio_path
        self.history = history
        self.system_prompt = system_prompt
        self.context_chars = context_chars
        self.user_context = user_context
        self.is_translation = is_translation
        
    def run(self):
        try:
            logger.info("Transcribing audio...")
            raw_text = self.api_client.transcribe(self.audio_path)
            
            if raw_text and not raw_text.startswith("Error"):
                logger.info(f"Transcription result: {raw_text[:50]}...")
                corrected_text = self.api_client.correct_text(
                    raw_text, 
                    self.history, 
                    self.system_prompt, 
                    self.context_chars, 
                    self.user_context,
                    is_translation=self.is_translation
                )
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
        self.api_client = ApiClient(self.api_key) if self.api_key else ApiClient()
        self.audio_recorder = AudioRecorder()
        
        # Activation Hotkey
        self.hotkey_manager = HotkeyManager(self.settings.get("hotkey", "ctrl+alt+s"))
        self.hotkey_manager.triggered.connect(self.toggle_standard_recording)
        self.hotkey_manager.start()

        # Translation Hotkey
        self.translation_hotkey_manager = HotkeyManager(self.settings.get("translation_hotkey", "ctrl+alt+t"))
        self.translation_hotkey_manager.triggered.connect(self.toggle_translation_recording)
        self.translation_hotkey_manager.start()

        # Cancellation Hotkey
        self.cancel_hotkey_manager = HotkeyManager(self.settings.get("cancel_hotkey", "ctrl+alt+x"))
        self.cancel_hotkey_manager.triggered.connect(self.cancel_operation)
        self.cancel_hotkey_manager.start()
        
        self.history = []
        self.current_mode = "correction" # or "translation"

        # System Tray
        self.tray_icon = QSystemTrayIcon(QIcon(get_resource_path("assets/icon.ico")), self.app)
        self.update_tray_menu()
        self.tray_icon.show()
        
        self.overlay.show_message(tr("ready"), duration=2000)
        logger.info(f"Application started (Language: {lang})")

    def update_tray_menu(self):
        from core.config import APP_VERSION
        self.tray_icon.setToolTip(f"{tr('app_name')} v{APP_VERSION}")
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
        # Stop all hotkeys to prevent triggering while typing in settings
        self.hotkey_manager.stop()
        self.translation_hotkey_manager.stop()
        self.cancel_hotkey_manager.stop()
        logger.info("Hotkeys stopped for settings dialog")

        current_lang = get_current_language()
        dialog = SettingsDialog(
            None,
            self.settings.get("hotkey", "ctrl+alt+s"),
            self.api_key,
            current_lang,
            self.settings.get("cancel_hotkey", "ctrl+alt+x"),
            self.settings.get("translation_hotkey", "ctrl+alt+t"),
            self.settings.get("startup", False)
        )
        # Manually set context because we passed None as parent
        dialog.context_input.setPlainText(self.settings.get("user_context", ""))

        if dialog.exec():
            changes = False

            # Update Hotkey
            if dialog.new_hotkey != self.settings.get("hotkey"):
                self.settings["hotkey"] = dialog.new_hotkey
                self.hotkey_manager.combination = dialog.new_hotkey  # Update combination
                logger.info(f"Hotkey updated to {dialog.new_hotkey}")
                changes = True

            # Update Cancel Hotkey
            if dialog.new_cancel_hotkey != self.settings.get("cancel_hotkey", ""):
                self.settings["cancel_hotkey"] = dialog.new_cancel_hotkey
                self.cancel_hotkey_manager.combination = dialog.new_cancel_hotkey  # Update combination
                logger.info(f"Cancel Hotkey updated to {dialog.new_cancel_hotkey}")
                changes = True

            # Update API Key
            if dialog.new_api_key != self.api_key:
                env_path = os.path.join(get_app_dir(), ".env")
                if not os.path.exists(env_path):
                     with open(env_path, "w") as f: f.write("")
                set_key(env_path, "OPENAI_API_KEY", dialog.new_api_key)
                self.api_key = dialog.new_api_key
                self.api_client = ApiClient(self.api_key)
                logger.info("API Key updated")
                changes = True

            # Update Translation Hotkey
            if dialog.new_translation_hotkey != self.settings.get("translation_hotkey"):
                self.settings["translation_hotkey"] = dialog.new_translation_hotkey
                self.translation_hotkey_manager.combination = dialog.new_translation_hotkey  # Update combination
                logger.info(f"Translation Hotkey updated to {dialog.new_translation_hotkey}")
                changes = True

            # Update Language
            if dialog.new_lang != current_lang:
                self.settings["app_language"] = dialog.new_lang
                set_language(dialog.new_lang)
                self.update_tray_menu() # Refresh tray menu
                logger.info(f"Language updated to {dialog.new_lang}")
                changes = True

            # Update User Context
            if dialog.new_user_context != self.settings.get("user_context", ""):
                 self.settings["user_context"] = dialog.new_user_context
                 logger.info("User context updated")
                 changes = True

            # Update Startup
            if dialog.new_startup != self.settings.get("startup", False):
                self.settings["startup"] = dialog.new_startup
                set_autostart(dialog.new_startup)
                logger.info(f"Startup setting updated to {dialog.new_startup}")
                changes = True

            if changes:
                save_settings_file(self.settings)
                self.overlay.show_message(tr("settings_saved"), duration=2000)

        # Restart hotkeys after dialog closes (regardless of Save/Cancel)
        self.hotkey_manager.start()
        self.translation_hotkey_manager.start()
        self.cancel_hotkey_manager.start()
        logger.info("Hotkeys restarted after settings dialog")

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
            except (TypeError, RuntimeError) as e:
                # TypeError: signal not connected
                # RuntimeError: signal disconnect failed (wrapped C++ object deleted)
                logger.debug(f"Signal disconnect warning: {e}")
            self.is_processing = False
            self.overlay.show_message(tr("canceled"), duration=1000)
            logger.info("Processing cancelled.")

    def toggle_standard_recording(self):
        self.current_mode = "correction"
        self.toggle_recording()

    def toggle_translation_recording(self):
        self.current_mode = "translation"
        self.toggle_recording()

    def toggle_recording(self):
        if self.is_processing:
            logger.warning("Already processing, ignore toggle")
            return

        if self.audio_recorder.recording:
            # Stop
            audio_path = self.audio_recorder.stop_recording()
            if audio_path:
                msg_key = "translating" if self.current_mode == "translation" else "recognizing"
                self.overlay.show_message(tr(msg_key), animate=True)
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
        is_translation = (self.current_mode == "translation")
        
        prompt_key = "translation_prompt" if is_translation else "system_prompt"
        prompt = self.settings.get(prompt_key, "")
        
        context_chars = self.settings.get("context_window_chars", 3000)
        user_context = self.settings.get("user_context", "")
        
        self.worker = ProcessingWorker(
            self.api_client, 
            audio_path, 
            self.history, 
            prompt, 
            context_chars, 
            user_context,
            is_translation=is_translation
        )
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
        self.translation_hotkey_manager.stop()
        self.cancel_hotkey_manager.stop()
        self.app.quit()

def main():
    setup_logging()
    
    # Single instance check
    import ctypes
    mutex_name = "Global\\S-Flow-Single-Instance-Mutex"
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, mutex_name)
    if ctypes.windll.kernel32.GetLastError() == 183: # ERROR_ALREADY_EXISTS
        logger.warning("Another instance is already running. Exiting.")
        return

    load_dotenv(os.path.join(get_app_dir(), ".env"))
    
    # Set AppUserModelID for Windows Taskbar Icon
    myappid = 'sflow.recognition.app.1.0' # arbitrary string
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(QIcon(get_resource_path("assets/icon.ico")))
    
    controller = AppController(app)
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
