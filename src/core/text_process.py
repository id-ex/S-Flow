"""
Text Processor module for clipboard operations and text insertion.

This module provides functionality to paste text into active applications
using keyboard simulation.
"""

import pyperclip
import keyboard
import logging
import threading
import win32api
import win32con
import win32gui
import win32process

logger = logging.getLogger(__name__)


class TextProcessor:
    """
    Handles text insertion into active applications.
    """

    @staticmethod
    def get_foreground_window() -> int | None:
        """Return the current foreground window handle, if available."""
        try:
            hwnd = win32gui.GetForegroundWindow()
            return hwnd or None
        except Exception as e:
            logger.debug(f"Failed to get foreground window: {e}")
            return None

    @staticmethod
    def _restore_target_window(target_hwnd: int | None) -> None:
        """Best-effort restore of the original target window before paste."""
        if not target_hwnd:
            return

        try:
            if not win32gui.IsWindow(target_hwnd):
                return

            foreground_hwnd = win32gui.GetForegroundWindow()
            foreground_thread = win32process.GetWindowThreadProcessId(
                foreground_hwnd
            )[0] if foreground_hwnd else 0
            target_thread = win32process.GetWindowThreadProcessId(target_hwnd)[0]
            current_thread = win32api.GetCurrentThreadId()

            if win32gui.IsIconic(target_hwnd):
                win32gui.ShowWindow(target_hwnd, win32con.SW_RESTORE)

            attached_foreground = False
            attached_target = False
            try:
                if foreground_thread and foreground_thread != current_thread:
                    win32process.AttachThreadInput(
                        current_thread, foreground_thread, True
                    )
                    attached_foreground = True

                if target_thread and target_thread != current_thread:
                    win32process.AttachThreadInput(current_thread, target_thread, True)
                    attached_target = True

                win32gui.SetForegroundWindow(target_hwnd)
                win32gui.SetActiveWindow(target_hwnd)
            finally:
                if attached_target:
                    win32process.AttachThreadInput(current_thread, target_thread, False)
                if attached_foreground:
                    win32process.AttachThreadInput(
                        current_thread, foreground_thread, False
                    )
        except Exception as e:
            logger.debug(f"Failed to restore target window focus: {e}")

    @staticmethod
    def paste_text(text: str, target_hwnd: int | None = None) -> None:
        """
        Paste text into active application using clipboard and keyboard simulation.

        Args:
            text: Text to paste
            target_hwnd: Original destination window handle to refocus before paste

        Note:
            Uses pyperclip to copy text to clipboard and keyboard.send() to
            simulate Ctrl+V paste action. Uses QTimer for non-blocking delay.
        """
        if not text:
            return

        try:
            # Copy new text
            pyperclip.copy(text)

            def perform_paste() -> None:
                TextProcessor._restore_target_window(target_hwnd)
                keyboard.send("ctrl+v")

            # Non-blocking delay for clipboard update, then simulate Ctrl+V
            # Using threading.Timer instead of QTimer avoids Qt event loop delays
            # that can cause the paste to happen on app exit if the loop is blocked.
            threading.Timer(0.2, perform_paste).start()
            logger.info("Text pasted via keyboard simulation.")

        except Exception as e:
            logger.error(f"Failed to paste text: {e}")
