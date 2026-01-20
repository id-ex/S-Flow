"""
OpenAI API Client for audio transcription and text correction.

This module provides a wrapper around the OpenAI API for Whisper transcription
and GPT text correction with retry logic and error handling.
"""

from openai import (
    OpenAI,
    APIError,
    AuthenticationError,
    RateLimitError,
    APIConnectionError,
)
import logging
import time
import wave
from typing import Callable, Any, Tuple
from .config import get_model_config, MAX_RETRIES, RETRY_DELAY

logger = logging.getLogger(__name__)


class ApiClient:
    """
    Client for OpenAI API operations (transcription and text correction).

    Provides methods for audio transcription using Whisper and
    text correction/chat completion using GPT models.
    """

    def __init__(self, api_key: str | None = None) -> None:
        """
        Initialize API client.

        Args:
            api_key: OpenAI API key. If None, client will be initialized later.
        """
        self.client: OpenAI | None = None
        if api_key:
            self.client = OpenAI(api_key=api_key)
        self.config = get_model_config()

    def _execute_with_retry(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """
        Execute a function with exponential backoff retry logic.

        Retries on RateLimitError and APIConnectionError with exponential backoff.
        Other exceptions are raised immediately.

        Args:
            func: Function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Result of func call

        Raises:
            RateLimitError: If max retries exceeded
            APIConnectionError: If max retries exceeded
            Exception: Other exceptions are propagated
        """
        retries = 0
        while retries <= MAX_RETRIES:
            try:
                return func(*args, **kwargs)
            except (RateLimitError, APIConnectionError) as e:
                retries += 1
                if retries > MAX_RETRIES:
                    logger.error(f"Max retries exceeded for {func.__name__}: {e}")
                    raise e

                wait_time = RETRY_DELAY * (2 ** (retries - 1))
                logger.warning(
                    f"Network/Rate error in {func.__name__} (Attempt {retries}/{MAX_RETRIES}). Retrying in {wait_time}s..."
                )
                time.sleep(wait_time)
            except Exception as e:
                # Other errors: do not retry
                raise e

    def transcribe(self, audio_path: str) -> Tuple[str, float]:
        """
        Transcribe audio file using OpenAI Whisper API.

        Args:
            audio_path: Path to WAV audio file

        Returns:
            Tuple of (Transcribed text, duration in seconds)
            If transcription fails, returns (Error string, 0.0)

        Note:
            Returns error strings instead of raising exceptions for UI compatibility.
            Error format: "Error: <message>"
        """
        model = self.config.get("transcription_model", "whisper-1")
        language = self.config.get("transcription_language", "ru")

        duration = 0.0
        try:
            with wave.open(audio_path, "rb") as wav_file:
                frames = wav_file.getnframes()
                rate = wav_file.getframerate()
                duration = frames / float(rate)
        except Exception as e:
            logger.error(f"Error calculating audio duration: {e}")

        def _call_api():
            if not self.client:
                raise ValueError("API Key not set")
            with open(audio_path, "rb") as audio_file:
                return self.client.audio.transcriptions.create(
                    model=model, file=audio_file, language=language
                )

        try:
            transcription = self._execute_with_retry(_call_api)
            return transcription.text, duration
        except (AuthenticationError, ValueError):
            logger.error("Authentication failed. Check API Key.")
            return "Error: Invalid API Key", 0.0
        except RateLimitError:
            logger.error("Rate limit exceeded.")
            return "Error: Rate Limit Exceeded", 0.0
        except APIConnectionError:
            logger.error("Network connection error.")
            return "Error: No Connection", 0.0
        except APIError as e:
            logger.error(f"OpenAI API Error: {e}")
            return f"Error: API Error", 0.0
        except Exception as e:
            logger.exception(f"Unexpected error during transcription: {e}")
            return f"Error: Transcription Failed", 0.0

    def correct_text(
        self,
        text: str,
        previous_messages: list | None = None,
        system_prompt: str | None = None,
        context_chars: int = 3000,
        user_context: str = "",
        is_translation: bool = False,
    ) -> Tuple[str, dict]:
        """
        Correct or translate text using OpenAI Chat API.

        Supports both text correction and translation modes. Builds context
        from previous messages and user-provided context.

        Args:
            text: Text to process
            previous_messages: List of previous conversation messages for context
            system_prompt: Custom system prompt (uses default if None)
            context_chars: Maximum context characters from history
            user_context: Additional user-provided context (e.g., topics, terms)
            is_translation: If True, use translation mode instead of correction

        Returns:
            Tuple of (Corrected/translated text, usage dictionary)
            If processing fails, returns (original text, empty dict)
        """
        if previous_messages is None:
            previous_messages = []

        model = self.config.get("correction_model", "gpt-4o-mini")

        try:
            # Default prompt if none provided
            if not system_prompt:
                if is_translation:
                    system_prompt = (
                        "Ты — профессиональный переводчик. Твоя задача — перевести предоставленный текст, сохраняя смысл и учитывая контекст.\n"
                        "### КОНТЕКСТ ДИАЛОГА:\n{{history}}\n"
                        "### ПРАВИЛА:\n"
                        "- Если текст на русском, переведи его на английский.\n"
                        "- Если текст на английском, переведи его на русский.\n"
                        "- Верни ТОЛЬКО переведенный текст."
                    )
                else:
                    system_prompt = "Ты — помощник, который исправляет распознанный текст. Контекст:\n{{history}}"

            # Construct context by chars
            history_text = ""
            current_length = 0

            # Iterate backwards
            context_messages = []
            for msg in reversed(previous_messages):
                msg_text = msg["text"]
                if current_length + len(msg_text) < context_chars:
                    context_messages.insert(0, f"- {msg_text}")
                    current_length += len(msg_text)
                else:
                    break

            history_text = "\n".join(context_messages)

            # Use Base Prompt
            final_system_prompt = system_prompt

            # Inject History
            if "{{history}}" in final_system_prompt:
                final_system_prompt = final_system_prompt.replace(
                    "{{history}}", history_text if history_text else "Нет контекста."
                )
            else:
                if history_text:
                    final_system_prompt += f"\n\nContext History:\n{history_text}"

            # Inject User Context
            if user_context:
                final_system_prompt += f"\n\n[USER CONTEXT: {user_context}]"

            messages = [
                {"role": "system", "content": final_system_prompt},
                {"role": "user", "content": text},
            ]

            def _call_chat():
                if not self.client:
                    raise ValueError("API Key not set")
                return self.client.chat.completions.create(
                    model=model, messages=messages
                )

            response = self._execute_with_retry(_call_chat)
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
            }
            return response.choices[0].message.content.strip(), usage
        except Exception as e:
            logger.exception(f"Correction error: {e}")
            return text, {}
