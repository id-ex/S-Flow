"""
Hotkey Controller for managing multiple hotkeys with batch operations.

This module provides a centralized controller for managing multiple hotkeys
with consistent start/stop behavior and simplified API.
"""

import logging
from typing import Callable
from PyQt6.QtCore import QObject, pyqtSignal

from .hotkey_manager import HotkeyManager

logger = logging.getLogger(__name__)


class HotkeyController(QObject):
    """
    Manages multiple hotkeys with batch operations.

    Attributes:
        triggered_activation: Signal emitted when activation hotkey is pressed
        triggered_translation: Signal emitted when translation hotkey is pressed
        triggered_cancel: Signal emitted when cancel hotkey is pressed
    """

    # Signals for each hotkey type
    triggered_activation = pyqtSignal()
    triggered_translation = pyqtSignal()
    triggered_cancel = pyqtSignal()

    def __init__(self, settings: dict):
        """
        Initialize HotkeyController with settings.

        Args:
            settings: Dictionary containing hotkey configurations with keys:
                      'hotkey', 'translation_hotkey', 'cancel_hotkey'
        """
        super().__init__()

        # Create individual hotkey managers
        self.managers = {
            "activation": HotkeyManager(settings.get("hotkey", "ctrl+alt+s")),
            "translation": HotkeyManager(
                settings.get("translation_hotkey", "ctrl+alt+t")
            ),
            "cancel": HotkeyManager(settings.get("cancel_hotkey", "ctrl+alt+x")),
        }

        # Connect signals
        self.managers["activation"].triggered.connect(self.triggered_activation.emit)
        self.managers["translation"].triggered.connect(self.triggered_translation.emit)
        self.managers["cancel"].triggered.connect(self.triggered_cancel.emit)

        logger.info(
            f"HotkeyController initialized with settings: {settings.get('hotkey')}, "
            f"{settings.get('translation_hotkey')}, {settings.get('cancel_hotkey')}"
        )

    def start_all(self) -> None:
        """Start all hotkey listeners."""
        for name, manager in self.managers.items():
            try:
                manager.start()
                logger.debug(f"Started hotkey manager: {name}")
            except Exception as e:
                logger.error(f"Failed to start hotkey manager {name}: {e}")

    def stop_all(self) -> None:
        """Stop all hotkey listeners."""
        for name, manager in self.managers.items():
            try:
                manager.stop()
                logger.debug(f"Stopped hotkey manager: {name}")
            except Exception as e:
                logger.error(f"Failed to stop hotkey manager {name}: {e}")

    def update_hotkey(self, hotkey_type: str, new_combination: str) -> bool:
        """
        Update a specific hotkey combination.

        Args:
            hotkey_type: Type of hotkey ('activation', 'translation', or 'cancel')
            new_combination: New key combination string (e.g., 'ctrl+alt+a')

        Returns:
            True if update succeeded, False otherwise
        """
        if hotkey_type not in self.managers:
            logger.error(f"Unknown hotkey type: {hotkey_type}")
            return False

        manager = self.managers[hotkey_type]
        if manager.combination == new_combination:
            return True  # No change needed

        try:
            manager.stop()
            manager.combination = new_combination
            manager.start()
            logger.info(f"Updated {hotkey_type} hotkey to: {new_combination}")
            return True
        except Exception as e:
            logger.error(f"Failed to update {hotkey_type} hotkey: {e}")
            return False

    def get_hotkey(self, hotkey_type: str) -> str:
        """
        Get current hotkey combination for a specific type.

        Args:
            hotkey_type: Type of hotkey ('activation', 'translation', or 'cancel')

        Returns:
            Current key combination string
        """
        if hotkey_type not in self.managers:
            logger.warning(f"Unknown hotkey type: {hotkey_type}")
            return ""

        return self.managers[hotkey_type].combination
