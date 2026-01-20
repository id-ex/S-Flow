"""
Custom exceptions for S-Flow application.

This module provides a standardized exception hierarchy for better error handling
and logging throughout the application.
"""


class SFlowError(Exception):
    """Base exception for S-Flow application errors."""

    def __init__(self, message: str, user_message: str | None = None) -> None:
        """
        Initialize S-Flow error.

        Args:
            message: Technical error message for logging
            user_message: User-friendly message to display in UI (optional)
        """
        super().__init__(message)
        self.user_message = user_message or message


class AuthenticationError(SFlowError):
    """Raised when API authentication fails."""

    def __init__(self, message: str = "Invalid API Key") -> None:
        super().__init__(message, user_message="Error: Invalid API Key")


class TranscriptionError(SFlowError):
    """Raised when audio transcription fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message, user_message="Error: Transcription Failed")


class APIConnectionError(SFlowError):
    """Raised when API network connection fails."""

    def __init__(self, message: str = "Network connection error") -> None:
        super().__init__(message, user_message="Error: No Connection")


class RateLimitError(SFlowError):
    """Raised when API rate limit is exceeded."""

    def __init__(self, message: str = "Rate limit exceeded") -> None:
        super().__init__(message, user_message="Error: Rate Limit Exceeded")


class AudioRecordingError(SFlowError):
    """Raised when audio recording fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message, user_message="Error: Audio recording failed")


class ConfigurationError(SFlowError):
    """Raised when configuration is invalid."""

    def __init__(self, message: str) -> None:
        super().__init__(message, user_message=f"Error: {message}")


class HotkeyError(SFlowError):
    """Raised when hotkey operations fail."""

    def __init__(self, message: str) -> None:
        super().__init__(message, user_message="Error: Hotkey operation failed")
