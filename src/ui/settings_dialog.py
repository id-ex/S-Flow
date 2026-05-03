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
    QWidget,
    QFrame,
    QTabWidget,
)
from PyQt6.QtCore import pyqtSignal, Qt, QThread
from PyQt6.QtGui import QColor, QKeySequence, QIcon, QKeyEvent, QPainter, QPen, QPixmap
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


class EyeToggleButton(QToolButton):
    """Password visibility button rendered in the app style."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(34, 34)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_icon = QPixmap(get_resource_path("assets/icons/eye-open.png"))
        self.closed_icon = QPixmap(get_resource_path("assets/icons/eye-off.png"))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint_background(painter)

        icon = self.open_icon if self.isChecked() else self.closed_icon
        self._paint_icon(painter, icon)

    def _paint_icon(self, painter: QPainter, icon: QPixmap) -> None:
        if icon.isNull():
            return

        size = 20
        x = (self.width() - size) // 2
        y = (self.height() - size) // 2
        painter.setOpacity(1.0 if self.isEnabled() else 0.45)
        painter.drawPixmap(x, y, size, size, icon)
        painter.setOpacity(1.0)

    def _paint_background(self, painter: QPainter) -> None:
        rect = self.rect().adjusted(1, 1, -1, -1)
        bg = QColor("#252b42") if not self.underMouse() else QColor("#2d3552")
        border = QColor("#4a5680") if not self.underMouse() else QColor("#68d6ff")
        painter.setPen(QPen(border, 1))
        painter.setBrush(bg)
        painter.drawRoundedRect(rect, 10, 10)


class MagicContextButton(QToolButton):
    """Subtle magic-context action button matching the settings palette."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(34, 34)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.icon_pixmap = QPixmap(get_resource_path("assets/icons/magic-context.png"))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(1, 1, -1, -1)
        bg = QColor("#252b42") if self.isEnabled() else QColor("#1d2336")
        if self.underMouse() and self.isEnabled():
            bg = QColor("#2d3552")
        border = QColor("#4a5680") if self.isEnabled() else QColor("#384263")
        if self.underMouse() and self.isEnabled():
            border = QColor("#68d6ff")

        painter.setPen(QPen(border, 1))
        painter.setBrush(bg)
        painter.drawRoundedRect(rect, 10, 10)

        if self.icon_pixmap.isNull():
            return

        size = 20
        x = (self.width() - size) // 2
        y = (self.height() - size) // 2
        painter.setOpacity(1.0 if self.isEnabled() else 0.45)
        painter.drawPixmap(x, y, size, size, self.icon_pixmap)
        painter.setOpacity(1.0)


class PromptEditorDialog(QDialog):
    """Dialog for editing advanced prompt settings."""

    def __init__(
        self,
        parent,
        system_prompt: str,
        translation_prompt: str,
    ):
        super().__init__(parent)
        self.setWindowTitle(tr("prompts_dialog_title"))
        self.setWindowIcon(QIcon(get_resource_path("assets/icon.ico")))
        self.setFixedSize(560, 560)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        warning = QLabel(tr("prompts_warning"))
        warning.setObjectName("warningLabel")
        warning.setWordWrap(True)
        layout.addWidget(warning)

        tabs = QTabWidget(self)
        self.system_edit = self._create_prompt_editor(system_prompt)
        self.translation_edit = self._create_prompt_editor(translation_prompt)
        tabs.addTab(self.system_edit, tr("correction_prompt_tab"))
        tabs.addTab(self.translation_edit, tr("translation_prompt_tab"))
        layout.addWidget(tabs, 1)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        ok_btn = QPushButton("OK")
        ok_btn.setObjectName("primaryButton")
        ok_btn.clicked.connect(self.accept)

        cancel_btn = QPushButton(tr("cancel_btn"))
        cancel_btn.setObjectName("secondaryButton")
        cancel_btn.clicked.connect(self.reject)

        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _create_prompt_editor(self, text: str) -> QPlainTextEdit:
        editor = QPlainTextEdit(self)
        editor.setObjectName("promptEditor")
        editor.setPlainText(text)
        return editor

    def prompts(self) -> tuple[str, str]:
        return (
            self.system_edit.toPlainText().strip(),
            self.translation_edit.toPlainText().strip(),
        )


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
        system_prompt: str = "",
        translation_prompt: str = "",
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
        self.system_prompt = system_prompt
        self.translation_prompt = translation_prompt

        from core.config import APP_VERSION

        self.setWindowTitle(f"{tr('settings_title')} v{APP_VERSION}")
        self.setWindowIcon(QIcon(get_resource_path("assets/icon.ico")))
        self.setFixedSize(432, 748)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )

        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(11, 10, 11, 10)
        self.layout.setSpacing(9)
        self.setLayout(self.layout)

        hotkeys_section, hotkeys_layout = self._create_section()
        hotkeys_layout.addWidget(QLabel(tr("hotkey_label")))
        self.hotkey_input = HotkeyEdit(current_hotkey)
        hotkeys_layout.addWidget(self.hotkey_input)

        hotkeys_layout.addWidget(QLabel(tr("translation_hotkey_label")))
        self.translation_hotkey_input = HotkeyEdit(translation_hotkey)
        hotkeys_layout.addWidget(self.translation_hotkey_input)

        hotkeys_layout.addWidget(QLabel(tr("cancel_hotkey_label")))
        self.cancel_hotkey_input = HotkeyEdit(cancel_hotkey)
        hotkeys_layout.addWidget(self.cancel_hotkey_input)
        self.layout.addWidget(hotkeys_section)

        api_section, api_layout = self._create_section()

        groq_label_layout = QHBoxLayout()
        groq_label_layout.setSpacing(4)
        groq_label = QLabel("Groq API Key")
        groq_link = QLabel('<a href="https://console.groq.com/keys">(Groq Cloud)</a>')
        groq_link.setOpenExternalLinks(True)
        groq_link.setCursor(Qt.CursorShape.PointingHandCursor)
        groq_label_layout.addWidget(groq_label)
        groq_label_layout.addWidget(groq_link)
        groq_label_layout.addStretch()
        api_layout.addLayout(groq_label_layout)
        
        self.groq_input = self._create_password_input(groq_key, "gsk_...", api_layout)
        self.groq_input.setPlaceholderText("gsk_...")

        openai_label_layout = QHBoxLayout()
        openai_label_layout.setSpacing(4)
        openai_label = QLabel("OpenAI API Key")
        openai_link = QLabel('<a href="https://platform.openai.com/api-keys">(OpenAI Platform)</a>')
        openai_link.setOpenExternalLinks(True)
        openai_link.setCursor(Qt.CursorShape.PointingHandCursor)
        openai_label_layout.addWidget(openai_label)
        openai_label_layout.addWidget(openai_link)
        openai_label_layout.addStretch()
        api_layout.addLayout(openai_label_layout)

        self.openai_input = self._create_password_input(openai_key, "sk-...", api_layout)
        self.openai_input.setPlaceholderText("sk-...")

        llm_layout = QHBoxLayout()
        llm_layout.setContentsMargins(0, 2, 0, 0)
        llm_layout.setSpacing(10)
        llm_label = QLabel(tr("correction_model_label"))
        llm_layout.addWidget(llm_label, 1)

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

        self.model_combo.setMinimumWidth(164)
        llm_layout.addWidget(self.model_combo)
        api_layout.addLayout(llm_layout)
        self.layout.addWidget(api_section)

        context_section, context_layout = self._create_section()
        context_label_layout = QHBoxLayout()
        context_label_layout.setContentsMargins(0, 0, 0, 0)
        context_label_layout.setSpacing(8)

        context_label = QLabel(tr("context_label"))
        context_label.setMinimumWidth(0)
        context_label_layout.addWidget(context_label, 1)

        self.magic_btn = MagicContextButton(self)
        self.magic_btn.setObjectName("magicContextButton")
        self.magic_btn.setToolTip(tr("magic_context_tooltip"))
        self.magic_btn.clicked.connect(self.generate_magic_context)
        context_label_layout.addWidget(
            self.magic_btn,
            0,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )

        context_layout.addLayout(context_label_layout)
        
        self.context_input = QPlainTextEdit("")
        self.context_input.setPlaceholderText(tr("context_placeholder"))
        self.context_input.setFixedHeight(116)
        context_layout.addWidget(self.context_input)
        self.layout.addWidget(context_section)

        language_section, language_layout = self._create_section()
        lang_startup_layout = QHBoxLayout()
        lang_startup_layout.setSpacing(10)

        lang_startup_layout.addWidget(QLabel(tr("language_label")))
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("Русский", "ru")
        self.lang_combo.addItem("English", "en")
        index = self.lang_combo.findData(current_lang)
        if index >= 0:
            self.lang_combo.setCurrentIndex(index)
        self.lang_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.lang_combo.setFixedWidth(126)
        lang_startup_layout.addWidget(self.lang_combo)

        prompts_btn = QPushButton(tr("edit_prompts_btn"))
        prompts_btn.setObjectName("secondaryButton")
        prompts_btn.clicked.connect(self.open_prompt_editor)
        lang_startup_layout.addWidget(prompts_btn, 1)

        language_layout.addLayout(lang_startup_layout)

        self.startup_check = QCheckBox(tr("startup_label"))
        self.startup_check.setChecked(current_startup)
        language_layout.addWidget(self.startup_check)
        self.layout.addWidget(language_section)

        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(8)
        save_btn = QPushButton(tr("save_btn"))
        save_btn.setObjectName("primaryButton")
        save_btn.clicked.connect(self.save_settings)

        logs_btn = QPushButton(tr("logs_btn"))
        logs_btn.setObjectName("secondaryButton")
        logs_btn.clicked.connect(self.open_logs)

        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(logs_btn)
        self.layout.addLayout(btn_layout)

        self.load_styles()

    def _create_section(self) -> tuple[QFrame, QVBoxLayout]:
        section = QFrame(self)
        section.setObjectName("settingsSection")
        layout = QVBoxLayout(section)
        layout.setContentsMargins(10, 9, 10, 9)
        layout.setSpacing(6)
        return section, layout

    def _create_password_input(
        self,
        value: str,
        placeholder: str,
        parent_layout: QVBoxLayout,
    ) -> QLineEdit:
        row = QWidget(self)
        row.setObjectName("passwordRow")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(7)

        line_edit = QLineEdit(value)
        line_edit.setEchoMode(QLineEdit.EchoMode.Password)
        line_edit.setPlaceholderText(placeholder)
        row_layout.addWidget(line_edit, 1)

        line_edit.setObjectName("apiKeyInput")

        reveal_btn = EyeToggleButton(self)
        reveal_btn.setObjectName("revealButton")
        reveal_btn.setToolTip(tr("show_api_key_tooltip"))
        reveal_btn.toggled.connect(
            lambda checked, edit=line_edit: edit.setEchoMode(
                QLineEdit.EchoMode.Normal
                if checked
                else QLineEdit.EchoMode.Password
            )
        )
        reveal_btn.toggled.connect(
            lambda checked, btn=reveal_btn: btn.setToolTip(
                tr("hide_api_key_tooltip")
                if checked
                else tr("show_api_key_tooltip")
            )
        )
        row_layout.addWidget(reveal_btn)
        parent_layout.addWidget(row)
        return line_edit

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
            parsed_hotkeys = [
                HotkeyManager.parse_combination(hotkey)
                for hotkey in hotkeys_to_validate
                if hotkey
            ]
            if len(parsed_hotkeys) != len(set(parsed_hotkeys)):
                QMessageBox.warning(
                    self,
                    tr("error_title"),
                    tr("error_duplicate_hotkeys"),
                )
                return
            for index, hotkey in enumerate(hotkeys_to_validate):
                if hotkey and not HotkeyManager.can_register_combination(
                    hotkey,
                    0x6F20 + index,
                ):
                    QMessageBox.warning(
                        self,
                        tr("error_title"),
                        tr("error_unavailable_hotkey").format(hotkey=hotkey),
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

    def open_prompt_editor(self):
        dialog = PromptEditorDialog(
            self,
            self.system_prompt,
            self.translation_prompt,
        )
        dialog.setStyleSheet(self.styleSheet())
        if dialog.exec() == 1:
            (
                self.system_prompt,
                self.translation_prompt,
            ) = dialog.prompts()

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
        
        self.magic_worker = MagicContextWorker(openai_key=openai_key, groq_key=groq_key)
        self.magic_worker.finished.connect(self._on_magic_success)
        self.magic_worker.error.connect(self._on_magic_error)
        self.magic_worker.start()

    def _on_magic_success(self, context_str: str):
        self.magic_btn.setEnabled(True)
        self.context_input.setPlainText(context_str.strip())

    def _on_magic_error(self, err_msg: str):
        self.magic_btn.setEnabled(True)
        QMessageBox.warning(self, tr("error_title"), err_msg)


    def open_logs(self):
        if os.path.exists(LOG_PATH):
            os.startfile(LOG_PATH)
        else:
            QMessageBox.information(self, tr("app_name"), "Log file not found yet.")
