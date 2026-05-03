import sys
import os
import logging
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtCore import pyqtSignal, QObject, QThread, QTimer, Qt
from dotenv import load_dotenv, set_key

from ui.overlay import StatusOverlay
from ui.settings_dialog import SettingsDialog
from core.audio_recorder import AudioRecorder
from core.hotkey_manager import HotkeyManager, repair_hotkey_settings
from core.api_client import ApiClient
from core.text_process import TextProcessor
from core.stats_manager import StatsManager
from core.update_manager import UpdateManager
from core.config import (
    load_settings,
    save_settings_file,
    setup_logging,
    get_model_config,
    get_resource_path,
    get_app_dir,
    set_autostart,
    SYSTEM_PROMPT,
    TRANSLATION_PROMPT,
)
from core.exceptions import (
    SFlowError,
    AuthenticationError,
    RateLimitError,
    APIConnectionError,
    TranscriptionError
)
from core.locale_manager import tr, set_language, get_current_language

logger = logging.getLogger(__name__)


class ProcessingWorker(QThread):
    finished = pyqtSignal(str, str, dict)  # raw_text, corrected_text, usage_stats

    def __init__(
        self,
        api_client: ApiClient,
        audio_frames: list,
        sample_rate: int,
        channels: int,
        history: list,
        system_prompt: str,
        context_chars: int,
        user_context: str = "",
        is_translation: bool = False,
        use_llm_correction: bool = True,
        correction_model: str = "gpt-4o-mini",
    ):
        super().__init__()
        self.api_client = api_client
        self.audio_frames = audio_frames
        self.sample_rate = sample_rate
        self.channels = channels
        self.history = history
        self.system_prompt = system_prompt
        self.context_chars = context_chars
        self.user_context = user_context
        self.is_translation = is_translation
        self.use_llm_correction = use_llm_correction
        self.correction_model = correction_model

    def run(self):
        audio_buffer = None
        try:
            # Encode WAV from raw chunks (heavy operation, done in worker thread)
            logger.info("Encoding WAV from raw audio chunks...")
            audio_buffer = AudioRecorder.encode_wav(
                self.audio_frames,
                sample_rate=self.sample_rate,
                channels=self.channels,
            )
            if audio_buffer is None:
                self.finished.emit("", "NoSpeech", {})
                return

            logger.info("Transcribing audio...")
            raw_text, duration, provider = self.api_client.transcribe(audio_buffer)
            usage_stats = {"whisper_seconds": duration, "prompt_tokens": 0, "completion_tokens": 0, "provider": provider}

            if not raw_text:
                logger.info("No speech detected or filtered artifact.")
                self.finished.emit("", "NoSpeech", usage_stats)
                return

            logger.info(f"Transcription result ({provider}): {raw_text}")
            
            if self.use_llm_correction or self.is_translation:
                corrected_text, gpt_usage = self.api_client.correct_text(
                    raw_text,
                    provider,
                    self.history,
                    self.system_prompt,
                    self.context_chars,
                    self.user_context,
                    is_translation=self.is_translation,
                    correction_model=self.correction_model,
                )
                usage_stats.update(gpt_usage)
                if gpt_usage.get("llm_failed"):
                    logger.warning("LLM post-processing failed.")
                    if self.is_translation:
                        self.finished.emit("", tr("error_translation_failed"), usage_stats)
                        return

                    corrected_text = raw_text
                    usage_stats["used_raw_fallback"] = True
                logger.info(f"Corrected Result: {corrected_text}")
            else:
                logger.info("LLM correction disabled, using raw text.")
                corrected_text = raw_text

            self.finished.emit(raw_text, corrected_text, usage_stats)

        except AuthenticationError:
            self.finished.emit("", tr("error_auth"), {})
        except RateLimitError:
             self.finished.emit("", tr("error_rate_limit"), {})
        except APIConnectionError:
             self.finished.emit("", tr("error_connection"), {})
        except TranscriptionError:
             self.finished.emit("", tr("error_transcription"), {})
        except SFlowError as e:
             # Generic SFlow handler
             logger.error(f"SFlow Error: {e}")
             self.finished.emit("", tr("error_unknown"), {})
        except Exception as e:
            logger.exception("Worker thread error")
            self.finished.emit("", tr("error_unknown"), {})
        finally:
            if audio_buffer:
                try:
                    audio_buffer.close()
                except:
                    pass


class AppController(QObject):
    audio_level_changed = pyqtSignal(float)

    def __init__(self, app, settings=None):
        super().__init__()
        self.app = app
        self.settings = settings if settings is not None else load_settings()
        
        # Keys from Environment or Settings (Migration fallback)
        self.openai_key = os.getenv("OPENAI_API_KEY")
        if not self.openai_key:
             self.openai_key = self.settings.get("openai_api_key", "")
        
        self.groq_key = os.getenv("GROQ_API_KEY")
        if not self.groq_key:
             self.groq_key = self.settings.get("groq_api_key", "")
        
        self.is_processing = False
        self.is_shutting_down = False
        self.hotkeys_suspended = False
        self.paste_target_hwnd = None

        # Initialize Locale
        lang = self.settings.get("app_language", "ru")
        set_language(lang)

        # UI Components
        self.overlay = StatusOverlay()
        self.audio_level_changed.connect(self.overlay.set_audio_level)

        # API & Logic
        self.api_client = self._create_api_client()
        # We no longer need an in-memory message_history list
        # self.message_history = []  <- Removed! Using stats_manager instead.
        self.audio_recorder = AudioRecorder(
            on_error=lambda msg: self.overlay.show_message(
                f"{tr('error_title')}: {msg}", duration=4000
            ),
            on_level=self.audio_level_changed.emit,
        )
        self.stats_manager = StatsManager()
        self.update_manager = UpdateManager()

        # Activation Hotkey
        self.hotkey_manager = HotkeyManager(self.settings.get("hotkey", "ctrl+alt+s"))
        self.hotkey_manager.triggered.connect(
            self.toggle_standard_recording, Qt.ConnectionType.QueuedConnection
        )

        # Translation Hotkey
        self.translation_hotkey_manager = HotkeyManager(
            self.settings.get("translation_hotkey", "ctrl+alt+t")
        )
        self.translation_hotkey_manager.triggered.connect(
            self.toggle_translation_recording, Qt.ConnectionType.QueuedConnection
        )

        self.available_update_url = None
        self.available_update_version = None

        # Update Manager Signals
        self.update_manager.update_available.connect(self.on_update_available)
        self.update_manager.download_progress.connect(self.on_download_progress)
        self.update_manager.download_finished.connect(self.on_download_finished)
        self.update_manager.error.connect(lambda msg: logger.error(f"Update error: {msg}"))
        self.update_manager.not_found.connect(self.on_update_not_found)

        # Cancellation Hotkey
        self.cancel_hotkey_manager = HotkeyManager(
            self.settings.get("cancel_hotkey", "ctrl+alt+x")
        )
        self.cancel_hotkey_manager.triggered.connect(
            self.cancel_operation, Qt.ConnectionType.QueuedConnection
        )
        self.hotkey_managers = [
            self.hotkey_manager,
            self.translation_hotkey_manager,
            self.cancel_hotkey_manager,
        ]
        self._start_hotkeys()

        self.hotkey_health_timer = QTimer(self)
        self.hotkey_health_timer.setInterval(30000)
        self.hotkey_health_timer.timeout.connect(self._check_hotkey_health)
        self.hotkey_health_timer.start()

        self.current_mode = "correction"  # or "translation"

        # System Tray
        self.tray_icon = QSystemTrayIcon(
            QIcon(get_resource_path("assets/icon.ico")), self.app
        )
        self.update_tray_menu()
        self.tray_icon.show()

        self.overlay.show_message(tr("ready"), duration=2000, mode="ready")
        logger.info(f"Application started (Language: {lang})")

        if not self.openai_key and not self.groq_key:
            QTimer.singleShot(1000, self.open_settings)

        # Auto-check for updates after the app has settled.
        QTimer.singleShot(120000, lambda: self.update_manager.check_for_updates(manual=False))

    def _create_api_client(self):
        def on_api_notify(msg):
            # Thread-safe UI update
            QTimer.singleShot(0, lambda: self.overlay.show_message(msg, duration=4000))
            
        return ApiClient(
            openai_key=self.openai_key, 
            groq_key=self.groq_key,
            on_notify=on_api_notify
        )

    def _start_hotkeys(self) -> None:
        for manager in self.hotkey_managers:
            if not manager.ensure_registered():
                logger.error("Hotkey failed to register: %s", manager.combination)

    def _stop_hotkeys(self) -> None:
        for manager in self.hotkey_managers:
            manager.stop()

    def _check_hotkey_health(self) -> None:
        if self.hotkeys_suspended or self.is_shutting_down:
            return

        if self.audio_recorder.recording or self.is_processing:
            return

        logger.debug("Checking hotkey registrations")
        for manager in self.hotkey_managers:
            manager.ensure_registered()

    def update_tray_menu(self):
        from core.config import APP_VERSION

        self.tray_icon.setToolTip(f"{tr('app_name')} v{APP_VERSION}")
        menu = QMenu()

        settings_action = QAction(tr("menu_settings"), self.app)
        settings_action.triggered.connect(self.open_settings)

        stats_action = QAction(tr("menu_stats"), self.app)
        stats_action.triggered.connect(self.open_statistics)

        quit_action = QAction(tr("menu_quit"), self.app)
        quit_action.triggered.connect(self.quit_app)

        menu.addAction(settings_action)
        menu.addAction(stats_action)

        if self.available_update_url:
            install_update_action = QAction(
                tr("menu_install_update").format(version=self.available_update_version),
                self.app,
            )
            install_update_action.triggered.connect(self.start_update_download)
            menu.addAction(install_update_action)

        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray_icon.setContextMenu(menu)

    def open_settings(self):
        # Stop all hotkeys to prevent triggering while typing in settings
        self.hotkeys_suspended = True
        self._stop_hotkeys()
        logger.info("Hotkeys stopped for settings dialog")

        current_lang = get_current_language()

        try:
            dialog = SettingsDialog(
                None,
                current_hotkey=self.settings.get("hotkey", "ctrl+alt+s"),
                openai_key=self.openai_key,
                groq_key=self.groq_key,
                current_lang=current_lang,
                cancel_hotkey=self.settings.get("cancel_hotkey", "ctrl+alt+x"),
                translation_hotkey=self.settings.get("translation_hotkey", "ctrl+alt+t"),
                current_startup=self.settings.get("startup", False),
                use_llm_correction=self.settings.get("use_llm_correction", True),
                correction_model=self.settings.get("correction_model", "gpt-4o-mini"),
                system_prompt=self.settings.get("system_prompt", SYSTEM_PROMPT),
                translation_prompt=self.settings.get("translation_prompt", TRANSLATION_PROMPT),
            )
            # Manually set context because we passed None as parent
            dialog.context_input.setPlainText(self.settings.get("user_context", ""))

            result = dialog.exec()
            if result == 1:  # Accepted
                changes = False

                # Update Hotkey
                if dialog.new_hotkey != self.settings.get("hotkey"):
                    self.settings["hotkey"] = dialog.new_hotkey
                    self.hotkey_manager.combination = (
                        dialog.new_hotkey
                    )  # Update combination
                    logger.info(f"Hotkey updated to {dialog.new_hotkey}")
                    changes = True

                # Update Cancel Hotkey
                if dialog.new_cancel_hotkey != self.settings.get("cancel_hotkey", ""):
                    self.settings["cancel_hotkey"] = dialog.new_cancel_hotkey
                    self.cancel_hotkey_manager.combination = (
                        dialog.new_cancel_hotkey
                    )  # Update combination
                    logger.info(f"Cancel Hotkey updated to {dialog.new_cancel_hotkey}")
                    changes = True

                # Update API Keys (to .env)
                env_path = os.path.join(get_app_dir(), ".env")
                if not os.path.exists(env_path):
                    with open(env_path, "w") as f:
                        f.write("")

                keys_changed = False
                if dialog.new_openai_key != self.openai_key:
                    set_key(env_path, "OPENAI_API_KEY", dialog.new_openai_key)
                    self.openai_key = dialog.new_openai_key
                    logger.info("OpenAI API Key updated in .env")
                    keys_changed = True

                if dialog.new_groq_key != self.groq_key:
                    set_key(env_path, "GROQ_API_KEY", dialog.new_groq_key)
                    self.groq_key = dialog.new_groq_key
                    logger.info("Groq API Key updated in .env")
                    keys_changed = True

                if keys_changed:
                    self.api_client = self._create_api_client()

                # Update Translation Hotkey
                if dialog.new_translation_hotkey != self.settings.get("translation_hotkey"):
                    self.settings["translation_hotkey"] = dialog.new_translation_hotkey
                    self.translation_hotkey_manager.combination = (
                        dialog.new_translation_hotkey
                    )  # Update combination
                    logger.info(
                        f"Translation Hotkey updated to {dialog.new_translation_hotkey}"
                    )
                    changes = True

                # Update Language
                if dialog.new_lang != current_lang:
                    self.settings["app_language"] = dialog.new_lang
                    set_language(dialog.new_lang)
                    self.update_tray_menu()  # Refresh tray menu
                    logger.info(f"Language updated to {dialog.new_lang}")
                    changes = True

                # Update User Context
                if dialog.new_user_context != self.settings.get("user_context", ""):
                    self.settings["user_context"] = dialog.new_user_context
                    logger.info("User context updated")
                    changes = True

                # Update Prompt Settings
                prompt_updates = {
                    "system_prompt": dialog.system_prompt,
                    "translation_prompt": dialog.translation_prompt,
                }
                for key, value in prompt_updates.items():
                    if value != self.settings.get(key, ""):
                        self.settings[key] = value
                        logger.info("%s updated", key)
                        changes = True

                # Update Startup
                if dialog.new_startup != self.settings.get("startup", False):
                    self.settings["startup"] = dialog.new_startup
                    set_autostart(dialog.new_startup)
                    logger.info(f"Startup setting updated to {dialog.new_startup}")
                    changes = True

                # Update LLM Correction
                if dialog.use_llm_correction != self.settings.get("use_llm_correction", True):
                    self.settings["use_llm_correction"] = dialog.use_llm_correction
                    logger.info(f"LLM Correction enabled: {dialog.use_llm_correction}")
                    changes = True

                # Update Correction Model
                if hasattr(dialog, "correction_model") and dialog.correction_model != self.settings.get("correction_model"):
                    self.settings["correction_model"] = dialog.correction_model
                    logger.info(f"LLM Correction model updated to: {dialog.correction_model}")
                    changes = True

                if changes:
                    save_settings_file(self.settings)
                    self.api_client.config = get_model_config(self.settings)
                    self.overlay.show_message(
                        tr("settings_saved"), duration=2000, mode="done"
                    )
        finally:
            # Restart hotkeys after dialog closes or if settings flow raises.
            self.hotkeys_suspended = False
            self._start_hotkeys()
            logger.info("Hotkeys restarted after settings dialog")


    def open_statistics(self):
        from ui.stats_dialog import StatsDialog
        dialog = StatsDialog(self.stats_manager)
        dialog.exec()

    def manual_update_check(self):
        self.overlay.show_message(tr("checking_updates"), animate=True)
        self.update_manager.check_for_updates(manual=True)

    def on_update_available(self, version, description, download_url):
        self.overlay.hide_overlay()
        self.available_update_url = download_url
        self.available_update_version = version
        self.update_tray_menu()

        self.overlay.show_message(tr("update_available_overlay").format(version=version), duration=5000)

    def start_update_download(self):
        if self.available_update_url:
            self.overlay.show_message(tr("downloading_update"), animate=True)
            self.update_manager.start_download(self.available_update_url)

    def on_download_progress(self, percent):
        self.overlay.show_message(f"{tr('downloading_update')} {percent}%")

    def on_download_finished(self, success, message):
        self.overlay.hide_overlay()
        if success:
            self.update_manager.apply_update()
        else:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(None, tr("error_title"), f"{tr('update_error')}: {message}")

    def on_update_not_found(self):
        self.overlay.hide_overlay()
        self.overlay.show_message(tr("update_not_found"), duration=2000)

    def cancel_operation(self):
        logger.info("Cancellation requested.")

        if self.audio_recorder.recording:
            # Stop recording without processing
            audio_chunks = self.audio_recorder.stop_recording()
            chunk_count = len(audio_chunks) if audio_chunks else 0
            logger.info(f"Recording cancelled. {chunk_count} audio chunks discarded.")
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
        else:
            self.overlay.show_message(tr("canceled"), duration=700)
            logger.info("Cancellation hotkey received while idle.")

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
            # Stop — returns raw chunks (list of numpy arrays)
            audio_chunks = self.audio_recorder.stop_recording()
            if audio_chunks:
                msg_key = (
                    "translating"
                    if self.current_mode == "translation"
                    else "recognizing"
                )
                self.overlay.show_message(tr(msg_key), animate=True, mode=msg_key)
                self.process_audio_chunks(audio_chunks)
            else:
                self.overlay.show_message(tr("error_no_speech"), duration=2000)
                logger.warning("Recording stopped but no audio chunks returned")
        else:
            # Start
            self.paste_target_hwnd = TextProcessor.get_foreground_window()
            self.audio_recorder.start_recording()
            self.overlay.show_message(tr("recording_started"), mode="recording")

    def process_audio_chunks(self, audio_chunks):
        """Process raw audio chunks in a background worker thread."""
        self.is_processing = True
        is_translation = self.current_mode == "translation"
        prompt_key = "translation_prompt" if is_translation else "system_prompt"
        fallback_prompt = TRANSLATION_PROMPT if is_translation else SYSTEM_PROMPT
        system_prompt = self.settings.get(prompt_key, fallback_prompt) or fallback_prompt

        context_chars = self.settings.get("context_window_chars", 3000)
        user_context = self.settings.get("user_context", "")
        use_llm = self.settings.get("use_llm_correction", True)
        correction_model = self.settings.get("correction_model", "gpt-4o-mini")

        # Always fetch fresh history from StatsManager
        current_history = self.stats_manager.get_history()

        # Clean up previous worker if exists
        if hasattr(self, 'worker') and self.worker is not None:
            self.worker.deleteLater()

        self.worker = ProcessingWorker(
            self.api_client,
            audio_frames=audio_chunks,
            sample_rate=self.audio_recorder.sample_rate,
            channels=self.audio_recorder.channels,
            history=current_history,
            system_prompt=system_prompt,
            context_chars=context_chars,
            user_context=user_context,
            is_translation=is_translation,
            use_llm_correction=use_llm,
            correction_model=correction_model,
        )
        self.worker.finished.connect(self.on_processing_finished)
        self.worker.start()

    def on_processing_finished(self, raw_text, corrected_text, usage_stats):
        if self.is_shutting_down:
            return

        self.is_processing = False
        self.overlay.hide_overlay()

        # Clean up worker
        if hasattr(self, 'worker') and self.worker is not None:
            self.worker.deleteLater()
            self.worker = None

        if usage_stats:
            # Stats for cost calculation:
            # We only add to stats if provider is NOT Groq (since Groq is free in this context)
            if usage_stats.get("provider") != "groq":
                self.stats_manager.add_usage(
                    whisper_seconds=usage_stats.get("whisper_seconds", 0.0),
                    prompt_tokens=usage_stats.get("prompt_tokens", 0),
                    completion_tokens=usage_stats.get("completion_tokens", 0)
                )

        if raw_text and not corrected_text.startswith("Error"):
            overlay_key = "warning_raw_text_used" if usage_stats.get("used_raw_fallback") else "done"
            mode = "done" if overlay_key == "done" else None
            self.overlay.show_message(tr(overlay_key), duration=1500, mode=mode)

            # History is now parsed from app.log directly in StatsManager

            TextProcessor.paste_text(
                corrected_text, target_hwnd=self.paste_target_hwnd
            )
            self.paste_target_hwnd = None
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
                "Error: Unknown": "error_unknown",
                "NoSpeech": "error_no_speech",
            }

            if error_text in map_errors:
                error_text = tr(map_errors[error_text])

            self.overlay.show_message(error_text, duration=3000)
            logger.error(f"Processing failed: {error_text}")
            self.paste_target_hwnd = None

    def quit_app(self):
        logger.info("Quitting application")
        self.is_shutting_down = True

        # Stop recording and cancel processing if active
        if self.audio_recorder.recording or self.is_processing:
            logger.info("Stopping active operations before quitting...")
            self.cancel_operation()

        self.hotkey_health_timer.stop()
        self._stop_hotkeys()
        self.app.quit()


def main():
    setup_logging()

    # Single instance check
    import ctypes

    mutex_name = "Global\\S-Flow-Single-Instance-Mutex"
    mutex = None
    try:
        mutex = ctypes.windll.kernel32.CreateMutexW(None, False, mutex_name)
        if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            logger.warning("Another instance is already running. Exiting.")
            return

        load_dotenv(os.path.join(get_app_dir(), ".env"))
        settings = load_settings()
        if repair_hotkey_settings(settings):
            save_settings_file(settings)
            logger.warning("Hotkey settings were repaired before application startup")

        # Set AppUserModelID for Windows Taskbar Icon
        myappid = "sflow.recognition.app.1.0"  # arbitrary string
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)
        app.setWindowIcon(QIcon(get_resource_path("assets/icon.ico")))

        controller = AppController(app, settings=settings)

        sys.exit(app.exec())
    finally:
        if mutex:
            ctypes.windll.kernel32.CloseHandle(mutex)


if __name__ == "__main__":
    main()
