"""
Hotkey Manager module for global keyboard shortcuts.

This module provides functionality to register and manage global hotkeys
using the keyboard library.
"""

import keyboard
import logging
from PyQt6.QtCore import QObject, pyqtSignal, QMetaObject, Qt

logger = logging.getLogger(__name__)


class HotkeyManager(QObject):
    """
    Manages a single global hotkey combination.

    Emits a PyQt signal when the hotkey combination is pressed.
    """

    triggered = pyqtSignal()

    def __init__(self, combination: str = "ctrl+alt+s") -> None:
        """
        Initialize hotkey manager.

        Args:
            combination: Key combination string (e.g., "ctrl+alt+s")
        """
        super().__init__()
        self.combination = combination
        self.hook = None

    def start(self) -> None:
        """Start listening for hotkey combination."""
        # We use a non-blocking hook with suppress=True to prevent
        # the hotkey from being passed to other applications
        keyboard.add_hotkey(self.combination, self.on_trigger, suppress=True)

    def stop(self) -> None:
        """Stop listening for hotkey combination."""
        try:
            keyboard.remove_hotkey(self.combination)
        except KeyError:
            logger.debug(f"Hotkey {self.combination} was not registered or already removed.")
        except Exception as e:
            logger.warning(f"Error removing hotkey {self.combination}: {e}")

    def on_trigger(self) -> None:
        """Handle hotkey trigger event."""
        logger.info(f"Hotkey {self.combination} triggered")
        # Thread-safe emit: keyboard callbacks run in non-GUI thread
        QMetaObject.invokeMethod(self, "triggered", Qt.ConnectionType.QueuedConnection)

    def update_hotkey(self, new_combination: str) -> bool:
        """
        Update the hotkey combination.

        Args:
            new_combination: New key combination string

        Returns:
            True if update succeeded, False otherwise
        """
        if self.combination == new_combination:
            return True

        try:
            self.stop()
            self.combination = new_combination
            self.start()
            return True
        except Exception as e:
            logger.error(f"Failed to update hotkey: {e}")
            return False
