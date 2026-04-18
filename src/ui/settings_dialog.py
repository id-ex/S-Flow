from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QToolButton,
    QHBoxLayout,
    QMessageBox,
    QComboBox,
    QPlainTextEdit,
    QCheckBox,
)
from PyQt6.QtCore import pyqtSignal, Qt, QThread
from PyQt6.QtGui import QKeySequence, QIcon, QKeyEvent
import os
from core.locale_manager import tr
from core.config import get_resource_path, LOG_PATH


class MagicContextWorker(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, openai_key: str, groq_key: str):
        super().__init__()
        self.openai_key = openai_key
        self.groq_key = groq_key

    def run(self):
        try:
            from core.stats_manager import StatsManager
            from core.api_client import ApiClient

            stats = StatsManager()
            history = stats.get_history()

            if not history:
                self.error.emit(tr("error_no_history"))
                return

            client = ApiClient(openai_key=self.openai_key, groq_key=self.groq_key)
            result = client.generate_magic_context(history, self.openai_key, self.groq_key)

            if result:
                self.finished.emit(result)
            else:
                self.error.emit(tr("error_generation_failed"))
        except Exception as e:
            self.error.emit(str(e))


class HotkeyEdit(QLineEdit):
    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setPlaceholderText(tr("hotkey_placeholder"))
        self.setReadOnly(True)  # Prevent manual typing, only capture

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        modifiers = event.modifiers()

        if key == Qt.Key.Key_Backspace or key == Qt.Key.Key_Delete:
            self.clear()
            return

        # Ignore modifier-only presses
        if key in (
            Qt.Key.Key_Control,
            Qt.Key.Key_Shift,
            Qt.Key.Key_Alt,
            Qt.Key.Key_Meta,
        ):
            return

        # Build string
        keys = []
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            keys.append("ctrl")
        if modifiers & Qt.KeyboardModifier.AltModifier:
            keys.append("alt")
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            keys.append("shift")

        # Get key text - use event.text() for alphanumeric keys (better for Ctrl+Alt+letter combos)
        # Otherwise use QKeySequence for special keys (F1, space, etc.)
        key_text = event.text().lower()

        # If event.text() is empty or not a simple character, use QKeySequence
        if not key_text or not key_text.isalnum():
            key_text = QKeySequence(key).toString().lower()

        if key_text:
            keys.append(key_text)

        final_hotkey = "+".join(keys)
        self.setText(final_hotkey)


class SettingsDialog(QDialog):
    def __init__(
        self,
        parent=None,
        current_hotkey: str = "",
        openai_key: str = "",
        groq_key: str = "",
        current_lang: str = "ru",
        cancel_hotkey: str = "ctrl+alt+x",
        translation_hotkey: str = "ctrl+alt+t",
        current_startup: bool = False,
        use_llm_correction: bool = True,
        correction_model: str = "gpt-4o-mini",
    ):
        super().__init__(parent)
        self.new_hotkey = current_hotkey
        self.new_cancel_hotkey = cancel_hotkey
        self.new_translation_hotkey = translation_hotkey
        self.new_openai_key = openai_key
        self.new_groq_key = groq_key
        self.new_lang = current_lang
        self.new_startup = current_startup
        self.use_llm_correction = use_llm_correction
        self.correction_model = correction_model

        from core.config import APP_VERSION

        self.setWindowTitle(f"{tr('settings_title')} v{APP_VERSION}")
        self.setWindowIcon(QIcon(get_resource_path("assets/icon.ico")))
        self.setFixedSize(400, 620)  # Increased height for extra API input
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        # Hotkey
        self.layout.addWidget(QLabel(tr("hotkey_label")))
        self.hotkey_input = HotkeyEdit(current_hotkey)
        self.layout.addWidget(self.hotkey_input)

        # Translation Hotkey
        self.layout.addWidget(QLabel(tr("translation_hotkey_label")))
        self.translation_hotkey_input = HotkeyEdit(translation_hotkey)
        self.layout.addWidget(self.translation_hotkey_input)

        # Cancel Hotkey
        self.layout.addWidget(QLabel(tr("cancel_hotkey_label")))
        self.cancel_hotkey_input = HotkeyEdit(cancel_hotkey)
        self.layout.addWidget(self.cancel_hotkey_input)
        self.layout.addSpacing(15) # Gap after hotkeys group

        # Groq API Key
        groq_label_layout = QHBoxLayout()
        groq_label = QLabel("Groq API Key (Primary)")
        groq_link = QLabel('<a href="https://console.groq.com/keys" style="color: #4da6ff; text-decoration: none;">(Groq Cloud)</a>')
        groq_link.setOpenExternalLinks(True)
        groq_link.setCursor(Qt.CursorShape.PointingHandCursor)
        groq_label_layout.addWidget(groq_label)
        groq_label_layout.addWidget(groq_link)
        groq_label_layout.addStretch()
        self.layout.addLayout(groq_label_layout)
        
        self.groq_input = QLineEdit(groq_key)
        self.groq_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.groq_input.setPlaceholderText("gsk_...")
        self.layout.addWidget(self.groq_input)

        # OpenAI API Key
        openai_label_layout = QHBoxLayout()
        openai_label = QLabel("OpenAI API Key (Fallback)")
        openai_link = QLabel('<a href="https://platform.openai.com/api-keys" style="color: #4da6ff; text-decoration: none;">(OpenAI Platform)</a>')
        openai_link.setOpenExternalLinks(True)
        openai_link.setCursor(Qt.CursorShape.PointingHandCursor)
        openai_label_layout.addWidget(openai_label)
        openai_label_layout.addWidget(openai_link)
        openai_label_layout.addStretch()
        self.layout.addLayout(openai_label_layout)

        self.openai_input = QLineEdit(openai_key)
        self.openai_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.openai_input.setPlaceholderText("sk-...")
        self.layout.addWidget(self.openai_input)

        llm_layout = QHBoxLayout()
        llm_label = QLabel(tr("correction_model_label"))
        llm_layout.addWidget(llm_label)

        self.model_combo = QComboBox()
        self.populate_models(openai_key, groq_key)
        
        
        if not use_llm_correction:
            idx = self.model_combo.findData("none")
        else:
            idx = self.model_combo.findData(correction_model)
            
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
            
        self.groq_input.textChanged.connect(self._update_models)
        self.openai_input.textChanged.connect(self._update_models)

        llm_layout.addWidget(self.model_combo)
        llm_layout.addStretch()
        self.layout.addLayout(llm_layout)

        self.layout.addSpacing(15) # Gap after API/AI group

        # User Context
        context_label_layout = QHBoxLayout()
        context_label_layout.setContentsMargins(0, 0, 0, 0)
        context_label_layout.setSpacing(8)

        context_label = QLabel(tr("context_label"))
        context_label.setMinimumWidth(0)
        context_label_layout.addWidget(context_label, 1)

        self.magic_btn = QToolButton()
        self.magic_btn.setObjectName("magicContextButton")
        self.magic_btn.setText("✨")
        self.magic_btn.setFixedSize(28, 28)
        self.magic_btn.setToolTip(tr("magic_context_tooltip"))
        self.magic_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.magic_btn.clicked.connect(self.generate_magic_context)
        context_label_layout.addWidget(
            self.magic_btn,
            0,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )

        self.layout.addLayout(context_label_layout)
        
        self.context_input = QPlainTextEdit("")
        self.context_input.setPlaceholderText(tr("context_placeholder"))
        self.context_input.setFixedHeight(90)
        self.context_input.setStyleSheet(
            "QPlainTextEdit { background-color: #3d3d3d; color: white; border: 1px solid #555; border-radius: 5px; padding: 5px; font-family: 'Segoe UI'; } QPlainTextEdit:focus { border: 2px solid #0078D4; background-color: #454545; }"
        )
        self.layout.addWidget(self.context_input)
        self.layout.addSpacing(10)

        # Language & Startup Row
        lang_startup_layout = QHBoxLayout()

        lang_startup_layout.addWidget(QLabel(tr("language_label")))
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("Русский", "ru")
        self.lang_combo.addItem("English", "en")
        index = self.lang_combo.findData(current_lang)
        if index >= 0:
            self.lang_combo.setCurrentIndex(index)
        lang_startup_layout.addWidget(self.lang_combo)

        lang_startup_layout.addSpacing(15)

        self.startup_check = QCheckBox(tr("startup_label"))
        self.startup_check.setChecked(current_startup)
        lang_startup_layout.addWidget(self.startup_check)

        lang_startup_layout.addStretch()

        self.layout.addLayout(lang_startup_layout)
        self.layout.addSpacing(10)

        # Buttons
        btn_layout = QHBoxLayout()
        save_btn = QPushButton(tr("save_btn"))
        save_btn.clicked.connect(self.save_settings)

        logs_btn = QPushButton(tr("logs_btn"))
        logs_btn.clicked.connect(self.open_logs)

        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(logs_btn)
        self.layout.addLayout(btn_layout)

        self.load_styles()

    def _update_models(self):
        current_model = self.model_combo.currentData()
        self.populate_models(self.openai_input.text().strip(), self.groq_input.text().strip())
        idx = self.model_combo.findData(current_model)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)

    def populate_models(self, openai_key: str, groq_key: str):
        self.model_combo.clear()
        
        self.model_combo.addItem(tr("model_none"), "none")
        
        if groq_key:
            self.model_combo.addItem("Llama 3.3 70B (Free)", "llama-3.3-70b-versatile")
            self.model_combo.addItem("Llama 3.2 3B (Free)", "llama-3.2-3b-preview")
            self.model_combo.addItem("Llama 3 8B (Free)", "llama3-8b-8192")
        if openai_key:
            self.model_combo.addItem("GPT-4o Mini", "gpt-4o-mini")
            self.model_combo.addItem("GPT-5 Mini", "gpt-5-mini")
            self.model_combo.addItem("GPT-5 Nano", "gpt-5-nano")
        if not groq_key and not openai_key:
            self.model_combo.setEnabled(False)
        else:
            self.model_combo.setEnabled(True)

    def load_styles(self):
        style_path = get_resource_path(os.path.join("assets", "style.qss"))
        if os.path.exists(style_path):
            with open(style_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())

    def save_settings(self):
        from core.hotkey_manager import HotkeyManager

        new_hotkey = self.hotkey_input.text().strip()
        new_cancel_hotkey = self.cancel_hotkey_input.text().strip()
        new_translation_hotkey = self.translation_hotkey_input.text().strip()
        new_groq_key = self.groq_input.text().strip()
        new_openai_key = self.openai_input.text().strip()
        new_lang = self.lang_combo.currentData()
        new_user_context = self.context_input.toPlainText().strip()
        new_startup = self.startup_check.isChecked()
        
        new_correction_model = self.model_combo.currentData()
        new_use_llm = (new_correction_model != "none")

        if not new_hotkey:
            QMessageBox.warning(self, tr("error_title"), tr("error_empty_hotkey"))
            return

        hotkeys_to_validate = (
            new_hotkey,
            new_translation_hotkey,
            new_cancel_hotkey,
        )
        try:
            if any(
                hotkey and not HotkeyManager.is_focus_safe_combination(hotkey)
                for hotkey in hotkeys_to_validate
            ):
                QMessageBox.warning(
                    self,
                    tr("error_title"),
                    tr("error_unsafe_alt_hotkey"),
                )
                return
        except ValueError as e:
            QMessageBox.warning(self, tr("error_title"), str(e))
            return

        if not new_groq_key and not new_openai_key:
             QMessageBox.warning(self, tr("error_title"), "Please enter at least one API key (Groq or OpenAI).")
             return

        self.new_hotkey = new_hotkey
        self.new_cancel_hotkey = new_cancel_hotkey
        self.new_translation_hotkey = new_translation_hotkey
        self.new_openai_key = new_openai_key
        self.new_groq_key = new_groq_key
        self.new_lang = new_lang
        self.new_user_context = new_user_context
        self.new_startup = new_startup
        self.use_llm_correction = new_use_llm
        if new_use_llm and new_correction_model:
            self.correction_model = new_correction_model
        self.accept()

    def generate_magic_context(self):
        """Asynchronously triggers context generation via LLM using recent history."""
        openai_key = self.openai_input.text().strip()
        groq_key = self.groq_input.text().strip()
        
        if not openai_key and not groq_key:
            QMessageBox.warning(
                self,
                tr("error_title"),
                tr("error_magic_context_api_key"),
            )
            return

        self.magic_btn.setEnabled(False)
        self.magic_btn.setText("…")
        
        self.magic_worker = MagicContextWorker(openai_key=openai_key, groq_key=groq_key)
        self.magic_worker.finished.connect(self._on_magic_success)
        self.magic_worker.error.connect(self._on_magic_error)
        self.magic_worker.start()

    def _on_magic_success(self, context_str: str):
        self.magic_btn.setEnabled(True)
        self.magic_btn.setText("✨")
        
        current_text = self.context_input.toPlainText().strip()
        if current_text:
            # Append uniquely
            existing_items = [item.strip() for item in current_text.split(",") if item.strip()]
            new_items = [item.strip() for item in context_str.split(",") if item.strip()]
            combined = existing_items
            for item in new_items:
                if item not in combined:
                    combined.append(item)
            self.context_input.setPlainText(", ".join(combined))
        else:
            self.context_input.setPlainText(context_str)

    def _on_magic_error(self, err_msg: str):
        self.magic_btn.setEnabled(True)
        self.magic_btn.setText("✨")
        QMessageBox.warning(self, tr("error_title"), err_msg)


    def open_logs(self):
        if os.path.exists(LOG_PATH):
            os.startfile(LOG_PATH)
        else:
            QMessageBox.information(self, tr("app_name"), "Log file not found yet.")
