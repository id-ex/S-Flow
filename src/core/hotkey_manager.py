"""
Hotkey Manager module for global keyboard shortcuts.

This module uses the native Windows RegisterHotKey API instead of the
third-party keyboard listener for hotkey capture. The WinAPI approach is
significantly more stable for a long-running tray app and avoids background
listener thread failures.
"""

from __future__ import annotations

import ctypes
import itertools
import logging
from ctypes import wintypes

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication, QWidget

logger = logging.getLogger(__name__)

user32 = ctypes.windll.user32

WM_HOTKEY = 0x0312

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

HOTKEY_SETTING_KEYS = ("hotkey", "translation_hotkey", "cancel_hotkey")
_HOTKEY_PRECHECK_BASE_ID = 0x5F10

_HOTKEY_FALLBACKS = {
    "hotkey": ("ctrl+alt+s", "ctrl+shift+s", "ctrl+alt+shift+s"),
    "translation_hotkey": (
        "ctrl+alt+t",
        "ctrl+shift+t",
        "ctrl+alt+shift+t",
    ),
    "cancel_hotkey": ("ctrl+alt+x", "ctrl+shift+x", "ctrl+alt+shift+x"),
}

_LEGACY_HOTKEY_MIGRATIONS = {
    "hotkey": {"alt+a": "ctrl+alt+s"},
    "translation_hotkey": {"alt+t": "ctrl+alt+t"},
    "cancel_hotkey": {"alt+c": "ctrl+alt+x"},
}

_MODIFIER_MAP = {
    "alt": MOD_ALT,
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
    "meta": MOD_WIN,
}

_SPECIAL_KEYS = {
    "backspace": 0x08,
    "tab": 0x09,
    "enter": 0x0D,
    "return": 0x0D,
    "pause": 0x13,
    "capslock": 0x14,
    "esc": 0x1B,
    "escape": 0x1B,
    "space": 0x20,
    "pageup": 0x21,
    "pagedown": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "insert": 0x2D,
    "delete": 0x2E,
}

_CYRILLIC_KEY_MAP = {
    "й": "q",
    "ц": "w",
    "у": "e",
    "к": "r",
    "е": "t",
    "н": "y",
    "г": "u",
    "ш": "i",
    "щ": "o",
    "з": "p",
    "х": "[",
    "ъ": "]",
    "ф": "a",
    "ы": "s",
    "в": "d",
    "а": "f",
    "п": "g",
    "р": "h",
    "о": "j",
    "л": "k",
    "д": "l",
    "ж": ";",
    "э": "'",
    "я": "z",
    "ч": "x",
    "с": "c",
    "м": "v",
    "и": "b",
    "т": "n",
    "ь": "m",
    "б": ",",
    "ю": ".",
}


def _is_windows_message_event(event_type) -> bool:
    try:
        event_name = bytes(event_type).decode("ascii", errors="ignore")
    except (TypeError, ValueError):
        event_name = str(event_type)

    return event_name in {"windows_generic_MSG", "windows_dispatcher_MSG"}


class _HotkeyMessageWindow(QWidget):
    """Hidden native window that receives WM_HOTKEY messages."""

    def nativeEvent(self, event_type, message):
        if not _is_windows_message_event(event_type):
            return False, 0

        msg = wintypes.MSG.from_address(int(message))
        if msg.message != WM_HOTKEY:
            return False, 0

        manager = HotkeyManager._instances_by_id.get(int(msg.wParam))
        if manager is None:
            return False, 0

        manager.on_trigger()
        return True, 0


class HotkeyManager(QObject):
    """
    Manages a single global hotkey combination.

    Emits a PyQt signal when the hotkey combination is pressed.
    """

    triggered = pyqtSignal()

    _message_window: _HotkeyMessageWindow | None = None
    _message_hwnd: int | None = None
    _instances_by_id: dict[int, "HotkeyManager"] = {}
    _id_counter = itertools.count(1000)

    def __init__(self, combination: str = "ctrl+alt+s") -> None:
        super().__init__()
        self.combination = combination
        self.hotkey_id: int | None = None
        self.is_registered = False
        self._vk_code: int | None = None
        self._modifiers: int | None = None
        self._hwnd: int | None = None

    @classmethod
    def _ensure_message_window(cls) -> int:
        app = QApplication.instance()
        if app is None:
            raise RuntimeError("QApplication must exist before registering hotkeys")

        if cls._message_window is None:
            cls._message_window = _HotkeyMessageWindow()
            cls._message_window.setWindowTitle("S-Flow Hotkey Sink")
            cls._message_hwnd = int(cls._message_window.winId())

        if cls._message_hwnd is None:
            raise RuntimeError("Failed to create hotkey message window")

        return cls._message_hwnd

    @staticmethod
    def _parse_key_token(token: str) -> tuple[int, int]:
        if token in _SPECIAL_KEYS:
            return _SPECIAL_KEYS[token], 0

        if token.startswith("f") and token[1:].isdigit():
            number = int(token[1:])
            if 1 <= number <= 24:
                return 0x70 + number - 1, 0

        if len(token) == 1:
            if token.isascii():
                return ord(token.upper()), 0

            if token in _CYRILLIC_KEY_MAP:
                mapped_key = _CYRILLIC_KEY_MAP[token]
                return ord(mapped_key.upper()), 0

            layout = user32.GetKeyboardLayout(0)
            vk_result = user32.VkKeyScanExW(token, layout)
            if ctypes.c_short(vk_result).value == -1:
                raise ValueError(f"Unsupported hotkey key: {token}")

            vk_code = vk_result & 0xFF
            shift_state = (vk_result >> 8) & 0xFF
            derived_modifiers = 0
            if shift_state & 1:
                derived_modifiers |= MOD_SHIFT
            if shift_state & 2:
                derived_modifiers |= MOD_CONTROL
            if shift_state & 4:
                derived_modifiers |= MOD_ALT
            return vk_code, derived_modifiers

        raise ValueError(f"Unsupported hotkey key: {token}")

    @classmethod
    def parse_combination(cls, combination: str) -> tuple[int, int]:
        tokens = [part.strip().lower() for part in combination.split("+") if part.strip()]
        if not tokens:
            raise ValueError("Empty hotkey combination")

        modifiers = 0
        main_tokens: list[str] = []

        for token in tokens:
            if token in _MODIFIER_MAP:
                modifiers |= _MODIFIER_MAP[token]
            else:
                main_tokens.append(token)

        if len(main_tokens) != 1:
            raise ValueError(f"Invalid hotkey combination: {combination}")

        vk_code, derived_modifiers = cls._parse_key_token(main_tokens[0])
        return modifiers | derived_modifiers, vk_code

    @classmethod
    def is_focus_safe_combination(cls, combination: str) -> bool:
        """Return False for pure Alt hotkeys that steal focus in many apps."""
        modifiers, _ = cls.parse_combination(combination)
        return modifiers != MOD_ALT

    @staticmethod
    def _registration_modifiers(modifiers: int) -> int:
        return modifiers | MOD_NOREPEAT

    @classmethod
    def can_register_combination(cls, combination: str, hotkey_id: int) -> bool:
        """Return True if Windows accepts this global hotkey right now."""
        try:
            modifiers, vk_code = cls.parse_combination(combination)
        except ValueError:
            return False

        registration_modifiers = cls._registration_modifiers(modifiers)
        if not user32.RegisterHotKey(None, hotkey_id, registration_modifiers, vk_code):
            return False

        try:
            return True
        finally:
            user32.UnregisterHotKey(None, hotkey_id)

    def _register_hotkey(self, hotkey_id: int, modifiers: int, vk_code: int) -> None:
        if self._hwnd is None:
            raise RuntimeError("Hotkey message window must exist before registration")

        registration_modifiers = self._registration_modifiers(modifiers)
        if not user32.RegisterHotKey(
            self._hwnd,
            hotkey_id,
            registration_modifiers,
            vk_code,
        ):
            error_code = ctypes.GetLastError()
            raise OSError(error_code, f"RegisterHotKey failed for {self.combination}")

    def _unregister_hotkey(self, hotkey_id: int) -> None:
        if not user32.UnregisterHotKey(self._hwnd, hotkey_id):
            error_code = ctypes.GetLastError()
            logger.debug(
                "UnregisterHotKey returned failure for %s (id=%s, error=%s)",
                self.combination,
                hotkey_id,
                error_code,
            )

    def start(self) -> None:
        """Start listening for hotkey combination."""
        if self.is_registered:
            self.stop()

        self._hwnd = self._ensure_message_window()
        modifiers, vk_code = self.parse_combination(self.combination)
        hotkey_id = next(self._id_counter)
        self._register_hotkey(hotkey_id, modifiers, vk_code)

        self.hotkey_id = hotkey_id
        self._modifiers = modifiers
        self._vk_code = vk_code
        self.is_registered = True
        self._instances_by_id[hotkey_id] = self
        logger.info(f"Hotkey registered: {self.combination}")

    def stop(self) -> None:
        """Stop listening for hotkey combination."""
        hotkey_id = self.hotkey_id
        try:
            if hotkey_id is not None:
                self._unregister_hotkey(hotkey_id)
        finally:
            if hotkey_id is not None:
                self._instances_by_id.pop(hotkey_id, None)
            self.hotkey_id = None
            self._vk_code = None
            self._modifiers = None
            self._hwnd = None
            self.is_registered = False

    def on_trigger(self) -> None:
        """Handle hotkey trigger event."""
        logger.info(f"Hotkey {self.combination} triggered")
        try:
            self.triggered.emit()
        except Exception as e:
            logger.exception(f"Failed to emit hotkey signal for {self.combination}: {e}")
            self.is_registered = False

    def ensure_registered(self) -> bool:
        """Ensure the hotkey is registered and recover if registration was lost."""
        try:
            if (
                self.is_registered
                and self.hotkey_id in self._instances_by_id
                and self._vk_code is not None
                and self._modifiers is not None
            ):
                return True

            self.start()
            return True
        except Exception as e:
            logger.error(f"Failed to recover hotkey {self.combination}: {e}")
            self.hotkey_id = None
            self.is_registered = False
            return False

    def refresh_registration(self) -> bool:
        """Force a complete unregister/register cycle."""
        try:
            self.stop()
            self.start()
            return True
        except Exception as e:
            logger.error(f"Failed to refresh hotkey {self.combination}: {e}")
            self.hotkey_id = None
            self.is_registered = False
            return False

    def update_hotkey(self, new_combination: str) -> bool:
        """Update the hotkey combination."""
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


def _unique_candidates(*groups: str | tuple[str, ...]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for group in groups:
        candidates = (group,) if isinstance(group, str) else group
        for candidate in candidates:
            normalized = candidate.strip().lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(candidate.strip())
    return result


def normalize_hotkey_combination(setting_key: str, combination: str) -> str:
    """Normalize unsafe legacy hotkeys to focus-safe combinations."""
    normalized = combination.strip().lower()
    if not normalized:
        return normalized

    legacy_map = _LEGACY_HOTKEY_MIGRATIONS.get(setting_key, {})
    if normalized in legacy_map:
        return legacy_map[normalized]

    try:
        if HotkeyManager.is_focus_safe_combination(normalized):
            return normalized
    except ValueError:
        return normalized

    if normalized.startswith("alt+"):
        return f"ctrl+{normalized}"

    return normalized


def repair_hotkey_settings(settings: dict) -> bool:
    """Preflight hotkey settings before the app starts registering them.

    The function mutates settings in place and returns True when it had to
    replace an invalid, duplicate, or currently unavailable global hotkey.
    """
    used_combinations: set[tuple[int, int]] = set()
    changed = False

    for index, key in enumerate(HOTKEY_SETTING_KEYS):
        original_value = str(settings.get(key, "")).strip()
        current_value = normalize_hotkey_combination(key, original_value)
        candidates = _unique_candidates(current_value, _HOTKEY_FALLBACKS[key])
        selected: str | None = None

        for candidate in candidates:
            try:
                parsed = HotkeyManager.parse_combination(candidate)
            except ValueError:
                logger.warning("Skipping invalid %s candidate: %s", key, candidate)
                continue

            if parsed in used_combinations:
                logger.warning("Skipping duplicate %s candidate: %s", key, candidate)
                continue

            temp_id = _HOTKEY_PRECHECK_BASE_ID + index
            if not HotkeyManager.can_register_combination(candidate, temp_id):
                logger.warning(
                    "Hotkey candidate is unavailable for %s: %s", key, candidate
                )
                continue

            selected = candidate
            used_combinations.add(parsed)
            break

        if selected is None:
            logger.error("No available startup hotkey candidate found for %s", key)
            continue

        if selected != original_value:
            logger.warning(
                "Repairing %s from %r to %r before startup",
                key,
                original_value,
                selected,
            )
            settings[key] = selected
            changed = True

    return changed
