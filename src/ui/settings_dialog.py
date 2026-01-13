from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QHBoxLayout, QMessageBox, QWidget
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QIcon, QKeyEvent
import os

class HotkeyEdit(QLineEdit):
    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setPlaceholderText("Нажмите сочетание клавиш...")
        self.setReadOnly(True) # Prevent manual typing, only capture
        
    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        modifiers = event.modifiers()
        
        if key == Qt.Key.Key_Backspace or key == Qt.Key.Key_Delete:
            self.clear()
            return
            
        # Ignore modifier-only presses
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
            return

        # Build string
        keys = []
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            keys.append("ctrl")
        if modifiers & Qt.KeyboardModifier.AltModifier:
            keys.append("alt")
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            keys.append("shift")
            
        # Get key text (e.g. 'S', 'F1')
        key_text = QKeySequence(key).toString().lower()
        if key_text:
            keys.append(key_text)
            
        final_hotkey = "+".join(keys)
        self.setText(final_hotkey)

class SettingsDialog(QDialog):
    def __init__(self, parent=None, current_hotkey: str = "", current_api_key: str = ""):
        super().__init__(parent)
        self.new_hotkey = current_hotkey
        self.new_api_key = current_api_key
        
        self.setWindowTitle("Настройки S-Flow")
        self.setWindowIcon(QIcon("assets/icon.png"))
        self.setFixedSize(400, 200)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint) 
        
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)
        
        # Hotkey
        self.layout.addWidget(QLabel("Клавиша активации (нажмите для изменения):"))
        self.hotkey_input = HotkeyEdit(current_hotkey) # Use Custom Widget
        self.layout.addWidget(self.hotkey_input)
        
        # API Key
        self.layout.addWidget(QLabel("OpenAI API Key:"))
        self.api_input = QLineEdit(current_api_key)
        self.api_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.layout.addWidget(self.api_input)
        
        # Buttons
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Сохранить")
        save_btn.clicked.connect(self.save_settings)
        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        self.layout.addLayout(btn_layout)
        
        self.load_styles()

    def load_styles(self):
        style_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "assets", "style.qss")
        if os.path.exists(style_path):
            with open(style_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())

    def save_settings(self):
        new_hotkey = self.hotkey_input.text().strip()
        new_api_key = self.api_input.text().strip()
        
        if not new_hotkey:
            QMessageBox.warning(self, "Ошибка", "Хоткей не может быть пустым")
            return
            
        if not new_api_key:
            QMessageBox.warning(self, "Ошибка", "API Key не может быть пустым")
            return
            
        self.new_hotkey = new_hotkey
        self.new_api_key = new_api_key
        self.accept()
