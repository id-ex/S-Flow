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
from .exceptions import (
    AuthenticationError as SFlowAuthError,
    RateLimitError as SFlowRateLimitError,
    APIConnectionError as SFlowConnectionError,
    TranscriptionError
)

logger = logging.getLogger(__name__)


class NamedBytesIO(io.BytesIO):
    """BytesIO wrapper with a stable file name for multipart uploads."""

    def __init__(self, initial_bytes: bytes = b"", name: str = "audio.wav") -> None:
        super().__init__(initial_bytes)
        self.name = name


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
        language = self.config.get("transcription_language", "ru")
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
                if hasattr(audio_file, "name"):
                    return audio_file

                named_buffer = NamedBytesIO(audio_file.getvalue())
                named_buffer.seek(0)
                return named_buffer

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
                            language=language,
                        )
                    finally:
                        if isinstance(audio_file, str) or isinstance(f_obj, NamedBytesIO):
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
                            language=language,
                        )
                    finally:
                        if isinstance(audio_file, str) or isinstance(f_obj, NamedBytesIO):
                            f_obj.close()

                transcription = self._execute_with_retry(_call_openai)
                text = transcription.text.strip()
                return self._process_text(text, duration, "openai")

            except (AuthenticationError, ValueError) as e:
                logger.error(f"OpenAI Authentication failed: {e}")
                raise SFlowAuthError("OpenAI Authentication failed") from e
            except (RateLimitError, APIConnectionError, APITimeoutError) as e:
                 logger.error(f"OpenAI Connection/Rate Limit error: {e}")
                 # Raise specific S-Flow errors
                 if isinstance(e, RateLimitError):
                     raise SFlowRateLimitError(str(e)) from e
                 raise SFlowConnectionError(str(e)) from e
            except Exception as e:
                logger.exception(f"OpenAI transcription failed: {e}")
                raise TranscriptionError(f"Transcription failed: {e}") from e
        
        # If we reach here, no provider worked
        raise TranscriptionError("No valid API provider configured or all attempts failed")

    def _process_text(self, text: str, duration: float, provider: str) -> Tuple[str, float, str]:
        """Filter hallucinations and return result."""
        # Filter out known Whisper hallucinations
        # Strict artifacts (almost always hallucinations)
        strict_artifacts = [
            "редактор субтитров", "а. синецкая", "корректор а. егорова",
            "субтитры а. синецкая", "текст предоставлен правообладателем",
            "dimatorzok", "dima torzok", "субтитры сделал", "с вами был игорь негода",
            "игорь негода",
        ]

        # Conditional artifacts with minimum valid duration (seconds)
        # If audio is shorter than this, it's likely a glitch/click.
        conditional_artifacts = {
            "продолжение следует": 1.2,
            "подписывайтесь на мой канал": 1.5,
            "приятного аппетита": 1.0,
            "озвучка:": 0.5,
            "перевод:": 0.5,
        }
        
        text_lower = text.lower().replace(".", "").replace(",", "").strip()
        
        # Check strict artifacts
        if any(art in text_lower for art in strict_artifacts):
             if len(text) < 100:
                logger.warning(f"Whisper strict hallucination detected: {text}")
                return "", duration, provider

        # Check conditional artifacts
        for art, min_duration in conditional_artifacts.items():
            if art in text_lower:
                # Condition 1: Audio too short (physically impossible to say the phrase)
                if duration < min_duration:
                    logger.warning(f"Whisper hallucination (Too Fast {duration:.2f}s < {min_duration}s): {text}")
                    return "", duration, provider
                
                # Condition 2: Audio too long (silence hallucination)
                if duration > 5.0 and len(text) < 50:
                    logger.warning(f"Whisper hallucination (Silence {duration:.2f}s > 5.0s): {text}")
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
        correction_model: str = "gpt-4o-mini",
    ) -> Tuple[str, dict]:
        """
        Correct text using the specified provider.
        """
        if previous_messages is None:
            previous_messages = []

        # Logic for pairing based on requested model prefix
        if correction_model.startswith("llama") and self.groq_client:
            client = self.groq_client
            model = correction_model
            used_provider = "groq"
        elif correction_model.startswith("gpt") and self.openai_client:
            client = self.openai_client
            model = correction_model
            used_provider = "openai"
        elif provider == "groq" and self.groq_client:
            client = self.groq_client
            model = "llama-3.3-70b-versatile"
            used_provider = "groq"
        elif provider == "openai" and self.openai_client:
            client = self.openai_client
            model = "gpt-4o-mini"
            used_provider = "openai"
        elif self.openai_client: # Fallback to OpenAI if provider invalid/missing but openai avail
            client = self.openai_client
            model = "gpt-4o-mini"
            used_provider = "openai"
        else:
            return text, {"llm_failed": True}

        logger.info(f"LLM Correction Model: {model}")

        try:
            # Default prompt if none provided
            if not system_prompt:
                # Fallback to a very basic prompt or raise error. 
                # Since we want to enforce config usage, let's log warning and use a minimal fallback.
                logger.warning("No system_prompt provided to correct_text, using minimal fallback.")
                system_prompt = "Correct the text."

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

            target_label = (
                "### TEXT TO TRANSLATE:"
                if is_translation
                else "### TARGET TEXT TO CORRECT:"
            )

            messages = [
                {"role": "system", "content": final_system_prompt},
                {"role": "user", "content": f"{target_label}\n{text}"},
            ]

            def _call_chat():
                kwargs = {
                    "model": model,
                    "messages": messages
                }
                if model.startswith("gpt-5"):
                    kwargs["reasoning_effort"] = "low"
                    
                return client.chat.completions.create(**kwargs)

            response = self._execute_with_retry(_call_chat)
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "provider": used_provider
            }
            return response.choices[0].message.content.strip(), usage
            
        except Exception as e:
            logger.exception(f"Correction error ({provider}): {e}")
            return text, {"provider": used_provider, "llm_failed": True}

    def generate_magic_context(self, history: list, openai_key: str, groq_key: str) -> str:
        """
        Generates a comma-separated list of context keywords from recent execution history.
        Prioritizes Groq over OpenAI for free generation.
        """
        if not history:
            return ""

        # Determine best available client
        client = None
        model = None
        
        if groq_key and self.groq_client:
            client = self.groq_client
            model = "llama-3.3-70b-versatile"
        elif openai_key and self.openai_client:
            client = self.openai_client
            model = "gpt-4o-mini"
            
        if not client or not model:
            logger.warning("Cannot generate magic context: no API keys configured.")
            return ""
            
        logger.info(f"Generating Magic Context using {model}")
        
        history_text = "\n".join([f"- {msg.get('text', '')}" for msg in history if isinstance(msg, dict) and msg.get('text')])
        if not history_text:
            return ""
            
        system_prompt = (
            "You are an AI assistant that analyzes a user's recent dictated text blocks. "
            "Extract the main technical terms, topics, names, and subjects to form a contextual glossary. "
            "Return ONLY a comma-separated list of these terms. Maximum 15 terms. Do not add conversational text or formatting. "
            "Keep the terms in the original language if possible. If the history is too short or generic, return an empty string."
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Recent dictated history:\n{history_text}"},
        ]

        def _call_magic():
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": 0.3
            }
            return client.chat.completions.create(**kwargs)

        try:
            response = self._execute_with_retry(_call_magic)
            generated_context = response.choices[0].message.content.strip()
            return generated_context
        except Exception as e:
            logger.error(f"Failed to generate magic context: {e}")
            return ""


