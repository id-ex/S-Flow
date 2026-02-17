"""
Text Processor module for clipboard operations and text insertion.

This module provides functionality to paste text into active applications
using keyboard simulation.
"""

import pyperclip
import keyboard
import logging
from PyQt6.QtCore import QTimer

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
            QTimer.singleShot(200, lambda: keyboard.send("ctrl+v"))
            logger.info("Text pasted via keyboard simulation.")

        except Exception as e:
            logger.error(f"Failed to paste text: {e}")

