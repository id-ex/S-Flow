"""
Text Processor module for clipboard operations and text insertion.

This module provides functionality to paste text into active applications
using keyboard simulation.
"""

import pyperclip
import keyboard
import time
import logging

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
            simulate Ctrl+V paste action. Waits 0.2s for clipboard update.
        """
        if not text:
            return

        try:
            # Copy new text
            pyperclip.copy(text)

            # Simulating Ctrl+V
            # Wait a bit for clipboard update.
            # 0.1 is usually enough, but 0.2 is safer for slower apps.
            time.sleep(0.2)
            keyboard.send("ctrl+v")
            logger.info("Text pasted via keyboard simulation.")

        except Exception as e:
            logger.error(f"Failed to paste text: {e}")
