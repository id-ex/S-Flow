import sys
import os
import threading
import json
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtCore import pyqtSignal, QObject, QThread, QTimer, Qt
from dotenv import load_dotenv

# Enhance search path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ui.overlay import StatusOverlay
from core.audio_recorder import AudioRecorder
from core.hotkey_manager import HotkeyManager
from core.api_client import ApiClient
from core.text_process import TextProcessor
from core.config import get_openai_key, load_settings

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
        if raw_text:
            corrected_text = self.api_client.correct_text(raw_text, self.history, self.system_prompt, self.context_chars)
            self.finished.emit(raw_text, corrected_text)
        else:
            self.finished.emit("", "Error: Transcription failed")

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
        quit_action = QAction("Quit", self.app)
        quit_action.triggered.connect(self.quit_app)
        
        menu.addAction(quit_action)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()
        
        # Welcome message
        self.overlay.show_message("S-Flow Ready", duration=2000)

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
            
            # History (Keep only for internal context)
            self.history.append({'text': corrected_text, 'is_bot': True})
            
            TextProcessor.paste_text(corrected_text)
        else:
            self.overlay.show_message("Error", duration=2000)
            
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
