from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QHBoxLayout, QMessageBox, QWidget, QComboBox, QPlainTextEdit
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QIcon, QKeyEvent
import os
from core.locale_manager import tr

class HotkeyEdit(QLineEdit):
    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setPlaceholderText(tr("hotkey_placeholder"))
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
    def __init__(self, parent=None, current_hotkey: str = "", current_api_key: str = "", current_lang: str = "ru", cancel_hotkey: str = "ctrl+alt+x", translation_hotkey: str = "ctrl+alt+t"):
        super().__init__(parent)
        self.new_hotkey = current_hotkey
        self.new_cancel_hotkey = cancel_hotkey
        self.new_translation_hotkey = translation_hotkey
        self.new_api_key = current_api_key
        self.new_lang = current_lang
        
        from core.config import APP_VERSION
        self.setWindowTitle(f"{tr('settings_title')} v{APP_VERSION}")
        self.setWindowIcon(QIcon("assets/icon.png"))
        self.setWindowIcon(QIcon("assets/icon.png"))
        self.setFixedSize(400, 520) # Increased height more
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint) 
        
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)
        
        # Hotkey
        self.layout.addWidget(QLabel(tr("hotkey_label")))
        self.hotkey_input = HotkeyEdit(current_hotkey)
        self.layout.addWidget(self.hotkey_input)

        # Cancel Hotkey
        self.layout.addWidget(QLabel(tr("cancel_hotkey_label")))
        self.cancel_hotkey_input = HotkeyEdit(cancel_hotkey)
        self.layout.addWidget(self.cancel_hotkey_input)

        # Translation Hotkey
        self.layout.addWidget(QLabel(tr("translation_hotkey_label")))
        self.translation_hotkey_input = HotkeyEdit(translation_hotkey)
        self.layout.addWidget(self.translation_hotkey_input)
        
        # API Key
        self.layout.addWidget(QLabel(tr("api_key_label")))
        self.api_input = QLineEdit(current_api_key)
        self.api_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.layout.addWidget(self.api_input)

        # User Context
        self.layout.addWidget(QLabel(tr("context_label")))
        self.context_input = QPlainTextEdit(parent.settings.get("user_context", "") if parent else "")
        self.context_input.setPlaceholderText(tr("context_placeholder"))
        self.context_input.setFixedHeight(80)
        # Manually styling for now to match
        self.context_input.setStyleSheet("QPlainTextEdit { background-color: #3d3d3d; color: white; border: 1px solid #555; border-radius: 5px; padding: 5px; font-family: 'Segoe UI'; } QPlainTextEdit:focus { border: 2px solid #0078D4; background-color: #454545; }")
        self.layout.addWidget(self.context_input)

        # Language
        self.layout.addWidget(QLabel(tr("language_label")))
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("Русский", "ru")
        self.lang_combo.addItem("English", "en")
        
        # Set current index
        index = self.lang_combo.findData(current_lang)
        if index >= 0:
            self.lang_combo.setCurrentIndex(index)
            
        self.layout.addWidget(self.lang_combo)
        
        # Buttons
        btn_layout = QHBoxLayout()
        save_btn = QPushButton(tr("save_btn"))
        save_btn.clicked.connect(self.save_settings)
        cancel_btn = QPushButton(tr("cancel_btn"))
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
        new_cancel_hotkey = self.cancel_hotkey_input.text().strip()
        new_translation_hotkey = self.translation_hotkey_input.text().strip()
        new_api_key = self.api_input.text().strip()
        new_lang = self.lang_combo.currentData()
        new_user_context = self.context_input.toPlainText().strip()
        
        if not new_hotkey:
            QMessageBox.warning(self, tr("error_title"), tr("error_empty_hotkey"))
            return
            
        if not new_api_key:
            QMessageBox.warning(self, tr("error_title"), tr("error_empty_api"))
            return
            
        self.new_hotkey = new_hotkey
        self.new_cancel_hotkey = new_cancel_hotkey
        self.new_translation_hotkey = new_translation_hotkey
        self.new_api_key = new_api_key
        self.new_lang = new_lang
        self.new_user_context = new_user_context
        self.accept()
