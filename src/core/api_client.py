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
    APITimeoutError
)
import logging
import time
import wave
import io
from typing import Callable, Any, Tuple
from .config import get_model_config, MAX_RETRIES, RETRY_DELAY

logger = logging.getLogger(__name__)


class ApiClient:
    """
    Client for OpenAI API operations (transcription and text correction).

    Provides methods for audio transcription using Whisper and
    text correction/chat completion using GPT models.
    """

    def __init__(
        self,
        openai_key: str | None = None,
        groq_key: str | None = None,
        on_notify: Callable[[str], None] | None = None,
    ) -> None:
        """
        Initialize API client.

        Args:
            openai_key: OpenAI API key.
            groq_key: Groq API key.
            on_notify: Callback function to send notifications (msg) -> None.
        """
        self.openai_client: OpenAI | None = None
        self.groq_client: OpenAI | None = None
        self.on_notify = on_notify

        if openai_key:
            self.openai_client = OpenAI(api_key=openai_key)
        
        if groq_key:
            self.groq_client = OpenAI(
                api_key=groq_key,
                base_url="https://api.groq.com/openai/v1"
            )

        self.config = get_model_config()

    def _execute_with_retry(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """
        Execute a function with exponential backoff retry logic.
        """
        retries = 0
        while retries <= MAX_RETRIES:
            try:
                return func(*args, **kwargs)
            except (RateLimitError, APIConnectionError, APITimeoutError) as e:
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

    def transcribe(self, audio_file: io.BytesIO | str) -> Tuple[str, float, str]:
        """
        Transcribe audio file using Groq (primary) or OpenAI (fallback).

        Args:
            audio_file: Buffer (BytesIO) or path to WAV audio file

        Returns:
            Tuple of (Transcribed text, duration in seconds, provider_used)
            provider_used: "groq" or "openai"
            If transcription fails, returns (Error string, 0.0, "")
        """
        # Calculate duration
        duration = 0.0
        try:
            # Handle both path and file-like object
            if isinstance(audio_file, str):
                f = open(audio_file, "rb")
                should_close = True
            else:
                f = audio_file
                should_close = False
                f.seek(0)
            
            try:
                with wave.open(f, "rb") as wav_file:
                    frames = wav_file.getnframes()
                    rate = wav_file.getframerate()
                    duration = frames / float(rate)
            finally:
                if should_close:
                    f.close()
                else:
                    f.seek(0) # Reset buffer position
        except Exception as e:
            logger.error(f"Error calculating audio duration: {e}")

        # Helper to prepare file for API
        def get_file_obj():
            if isinstance(audio_file, str):
                return open(audio_file, "rb")
            else:
                audio_file.seek(0)
                # Important: API client needs a 'name' attribute to determine content type
                if not hasattr(audio_file, "name"):
                    audio_file.name = "audio.wav" 
                return audio_file # BytesIO is already file-like

        # --- Attempt 1: Groq ---
        if self.groq_client:
            try:
                logger.info("Attempting transcription with Groq...")
                
                def _call_groq():
                    f_obj = get_file_obj()
                    try:
                        model_name = "whisper-large-v3-turbo"
                        logger.info(f"STT Model: {model_name}")
                        return self.groq_client.audio.transcriptions.create(
                            model=model_name,
                            file=f_obj,
                            language="ru" # Groq whisper supports language param
                        )
                    finally:
                        if isinstance(audio_file, str):
                            f_obj.close()

                transcription = self._execute_with_retry(_call_groq)
                text = transcription.text.strip()
                return self._process_text(text, duration, "groq")

            except (RateLimitError, APIConnectionError, APITimeoutError, APIError) as e:
                msg = f"Groq Issue: {e}. Switching to OpenAI."
                logger.warning(msg)
                if self.on_notify:
                    self.on_notify("Лимит Groq исчерпан. Переключаюсь на OpenAI")
            except Exception as e:
                logger.error(f"Unexpected Groq error: {e}. Switching to OpenAI.")
                if self.on_notify:
                    self.on_notify("Ошибка Groq. Переключаюсь на OpenAI")

        # --- Attempt 2: OpenAI (Fallback) ---
        if self.openai_client:
            try:
                logger.info("Attempting transcription with OpenAI...")
                 
                def _call_openai():
                    f_obj = get_file_obj()
                    try:
                        model_name = "whisper-1"
                        logger.info(f"STT Model: {model_name}")
                        return self.openai_client.audio.transcriptions.create(
                            model=model_name,
                            file=f_obj,
                            language="ru"
                        )
                    finally:
                        if isinstance(audio_file, str):
                            f_obj.close()

                transcription = self._execute_with_retry(_call_openai)
                text = transcription.text.strip()
                return self._process_text(text, duration, "openai")

            except (AuthenticationError, ValueError):
                logger.error("OpenAI Authentication failed.")
                return "Error: Invalid API Key", 0.0, ""
            except Exception as e:
                logger.exception(f"OpenAI transcription failed: {e}")
                return "Error: Transcription Failed", 0.0, ""
        
        return "Error: No valid API provider configured", 0.0, ""

    def _process_text(self, text: str, duration: float, provider: str) -> Tuple[str, float, str]:
        """Filter hallucinations and return result."""
        # Filter out known Whisper hallucinations
        artifacts = [
            "редактор субтитров", "а. синецкая", "корректор а. егорова",
            "субтитры а. синецкая", "текст предоставлен правообладателем",
            "dimatorzok", "dima torzok", "субтитры сделал", "озвучка:",
            "перевод:", "приятного аппетита", "с вами был игорь негода",
            "подписывайтесь на мой канал", "игорь негода",
        ]
        
        text_lower = text.lower().replace(".", "").replace(",", "").strip()
        
        if any(art in text_lower for art in artifacts):
            if len(text) < 100:
                logger.warning(f"Whisper hallucination detected: {text}")
                return "", duration, provider
                
        if len(text_lower.strip()) < 2:
            return "", duration, provider

        return text, duration, provider

    def correct_text(
        self,
        text: str,
        provider: str,
        previous_messages: list | None = None,
        system_prompt: str | None = None,
        context_chars: int = 3000,
        user_context: str = "",
        is_translation: bool = False,
    ) -> Tuple[str, dict]:
        """
        Correct text using the specified provider.
        """
        if previous_messages is None:
            previous_messages = []

        # Logic for pairing:
        # Groq -> llama-3.3-70b-versatile
        # OpenAI -> gpt-4o-mini
        
        if provider == "groq" and self.groq_client:
            client = self.groq_client
            model = "llama-3.3-70b-versatile"
        elif provider == "openai" and self.openai_client:
            client = self.openai_client
            model = "gpt-4o-mini"
        elif self.openai_client: # Fallback to OpenAI if provider invalid/missing but openai avail
            client = self.openai_client
            model = "gpt-4o-mini"
        else:
            return text, {}

        logger.info(f"LLM Correction Model: {model}")

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

            # Construct context
            history_text = ""
            current_length = 0
            context_messages = []
            for msg in reversed(previous_messages):
                msg_text = msg["text"]
                if current_length + len(msg_text) < context_chars:
                    context_messages.insert(0, f"- {msg_text}")
                    current_length += len(msg_text)
                else:
                    break
            history_text = "\n".join(context_messages)

            # Inject History
            final_system_prompt = system_prompt
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
                return client.chat.completions.create(
                    model=model, messages=messages
                )

            response = self._execute_with_retry(_call_chat)
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "provider": provider
            }
            return response.choices[0].message.content.strip(), usage
            
        except Exception as e:
            logger.exception(f"Correction error ({provider}): {e}")
            return text, {}

