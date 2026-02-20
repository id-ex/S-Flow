"""
Text Processor module for clipboard operations and text insertion.

This module provides functionality to paste text into active applications
using keyboard simulation.
"""

import pyperclip
import keyboard
import logging
import threading

logger = logging.getLogger(__name__)


class TextProcessor:
    """
    Handles text insertion into active applications.
    """

    @staticmethod
    def paste_text(text: str) -> None:
        """
        Paste text into active application using clipboard and keyboard simulation.

        Args:
            text: Text to paste

        Note:
            Uses pyperclip to copy text to clipboard and keyboard.send() to
            simulate Ctrl+V paste action. Uses QTimer for non-blocking delay.
        """
        if not text:
            return

        try:
            # Copy new text
            pyperclip.copy(text)

            # Non-blocking delay for clipboard update, then simulate Ctrl+V
            # Using threading.Timer instead of QTimer avoids Qt event loop delays
            # that can cause the paste to happen on app exit if the loop is blocked.
            threading.Timer(0.2, lambda: keyboard.send("ctrl+v")).start()
            logger.info("Text pasted via keyboard simulation.")

        except Exception as e:
            logger.error(f"Failed to paste text: {e}")

