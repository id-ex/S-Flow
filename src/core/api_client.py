from openai import OpenAI, APIError, AuthenticationError, RateLimitError, APIConnectionError
import logging
import time
from .config import get_model_config, MAX_RETRIES, RETRY_DELAY

logger = logging.getLogger(__name__)

class ApiClient:
    def __init__(self, api_key: str = None):
        self.client = None
        if api_key:
            self.client = OpenAI(api_key=api_key)
        self.config = get_model_config()

    def _execute_with_retry(self, func, *args, **kwargs):
        """
        Executes a function with exponential backoff retry logic.
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
                logger.warning(f"Network/Rate error in {func.__name__} (Attempt {retries}/{MAX_RETRIES}). Retrying in {wait_time}s...")
                time.sleep(wait_time)
            except Exception as e:
                # Other errors: do not retry
                raise e

    def transcribe(self, audio_path: str) -> str:
        model = self.config.get("transcription_model", "whisper-1")
        
        def _call_api():
            if not self.client:
                raise AuthenticationError("API Key not set", None, None)
            with open(audio_path, "rb") as audio_file:
                return self.client.audio.transcriptions.create(
                    model=model, 
                    file=audio_file,
                    language="ru"
                )

        try:
            transcription = self._execute_with_retry(_call_api)
            return transcription.text
        except AuthenticationError:
            logger.error("Authentication failed. Check API Key.")
            return "Error: Invalid API Key"
        except RateLimitError:
            logger.error("Rate limit exceeded.")
            return "Error: Rate Limit Exceeded"
        except APIConnectionError:
            logger.error("Network connection error.")
            return "Error: No Connection"
        except APIError as e:
            logger.error(f"OpenAI API Error: {e}")
            return f"Error: API Error"
        except Exception as e:
            logger.exception(f"Unexpected error during transcription: {e}")
            return f"Error: Transcription Failed"

    def correct_text(self, text: str, previous_messages: list = [], system_prompt: str = None, context_chars: int = 3000, user_context: str = "", is_translation: bool = False) -> str:
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
                msg_text = msg['text']
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
                final_system_prompt = final_system_prompt.replace("{{history}}", history_text if history_text else "Нет контекста.")
            else:
                if history_text:
                    final_system_prompt += f"\n\nContext History:\n{history_text}"

            # Inject User Context
            if user_context:
                final_system_prompt += f"\n\n[USER CONTEXT: {user_context}]"

            messages = [
                {"role": "system", "content": final_system_prompt},
                {"role": "user", "content": text}
            ]

            def _call_chat():
                if not self.client:
                    raise Exception("Error: Invalid API Key")
                return self.client.chat.completions.create(
                    model=model,
                    messages=messages
                )

            response = self._execute_with_retry(_call_chat)
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.exception(f"Correction error: {e}")
            return text
