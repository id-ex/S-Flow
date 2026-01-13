import sys
import os
import threading
import json
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtCore import pyqtSignal, QObject, QThread, QTimer, Qt
from dotenv import load_dotenv, set_key

# Enhance search path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ui.overlay import StatusOverlay
from ui.settings_dialog import SettingsDialog
from core.audio_recorder import AudioRecorder
from core.hotkey_manager import HotkeyManager
from core.api_client import ApiClient
from core.text_process import TextProcessor
from core.config import get_openai_key, load_settings, save_settings_file

class ProcessingWorker(QThread):
    finished = pyqtSignal(str, str) # raw_text, corrected_text
    
    def __init__(self, api_client, audio_path, history, system_prompt, context_chars):
        super().__init__()
        self.api_client = api_client
        self.audio_path = audio_path
        self.history = history
        self.system_prompt = system_prompt
        self.context_chars = context_chars
        
    def run(self):
        raw_text = self.api_client.transcribe(self.audio_path)
        if raw_text and not raw_text.startswith("Error"):
            corrected_text = self.api_client.correct_text(raw_text, self.history, self.system_prompt, self.context_chars)
            self.finished.emit(raw_text, corrected_text)
        else:
            # Pass the error string directly
            self.finished.emit("", raw_text if raw_text else "Error: Unknown")

class AppController(QObject):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.settings = load_settings()
        self.api_key = get_openai_key()
        
        # UI Components
        self.overlay = StatusOverlay()
        
        # API & Logic
        self.api_client = ApiClient(self.api_key)
        self.audio_recorder = AudioRecorder()
        self.hotkey_manager = HotkeyManager(self.settings.get("hotkey", "ctrl+alt+s"))
        self.hotkey_manager.triggered.connect(self.toggle_recording)
        self.hotkey_manager.start()
        
        self.history = []

        # System Tray
        self.tray_icon = QSystemTrayIcon(QIcon("assets/icon.png"), self.app)
        self.tray_icon.setToolTip("S-Flow")
        
        # Menu
        menu = QMenu()
        settings_action = QAction("Settings", self.app)
        settings_action.triggered.connect(self.open_settings)
        quit_action = QAction("Quit", self.app)
        quit_action.triggered.connect(self.quit_app)
        
        menu.addAction(settings_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()
        
        self.overlay.show_message("S-Flow Ready", duration=2000)

    def open_settings(self):
        # Current API Key could be obscured or retrieved
        dialog = SettingsDialog(None, self.settings.get("hotkey", "ctrl+alt+s"), self.api_key)
        if dialog.exec():
            # Update Hotkey
            if dialog.new_hotkey != self.settings.get("hotkey"):
                self.settings["hotkey"] = dialog.new_hotkey
                save_settings_file(self.settings)
                self.hotkey_manager.update_hotkey(dialog.new_hotkey)
                
            # Update API Key
            if dialog.new_api_key != self.api_key:
                # Save to .env
                env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
                if not os.path.exists(env_path):
                     with open(env_path, "w") as f: f.write("")
                set_key(env_path, "OPENAI_API_KEY", dialog.new_api_key)
                
                # Update runtime
                self.api_key = dialog.new_api_key
                self.api_client = ApiClient(self.api_key)
                
            self.overlay.show_message("Settings Saved", duration=2000)

    def toggle_recording(self):
        if self.audio_recorder.recording:
            # Stop
            audio_path = self.audio_recorder.stop_recording()
            if audio_path:
                self.overlay.show_message("Recognizing...", animate=True)
                self.process_audio(audio_path)
            else:
                self.overlay.hide_overlay()
        else:
            # Start
            self.audio_recorder.start_recording()
            self.overlay.show_message("Recording...")

    def process_audio(self, audio_path):
        prompt = self.settings.get("system_prompt", "")
        context_chars = self.settings.get("context_window_chars", 3000)
        self.worker = ProcessingWorker(self.api_client, audio_path, self.history, prompt, context_chars)
        self.worker.finished.connect(self.on_processing_finished)
        self.worker.start()
        
    def on_processing_finished(self, raw_text, corrected_text):
        self.overlay.hide_overlay()
        
        if raw_text and not corrected_text.startswith("Error"):
            self.overlay.show_message("Done!", duration=1000)
            
            # History
            self.history.append({'text': corrected_text, 'is_bot': True})
            
            TextProcessor.paste_text(corrected_text)
        else:
            # Show specific error from worker
            error_text = corrected_text if corrected_text.startswith("Error") else "Error: Unknown"
            self.overlay.show_message(error_text, duration=3000)
            
    def quit_app(self):
        self.hotkey_manager.stop()
        self.app.quit()

def main():
    load_dotenv()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    
    controller = AppController(app)
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
