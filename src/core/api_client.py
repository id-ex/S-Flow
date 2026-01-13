from openai import OpenAI, APIError, AuthenticationError, RateLimitError, APIConnectionError
import logging
from .config import get_model_config

logger = logging.getLogger(__name__)

class ApiClient:
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key)
        self.config = get_model_config()

    def transcribe(self, audio_path: str) -> str:
        model = self.config.get("transcription_model", "whisper-1")
        try:
            with open(audio_path, "rb") as audio_file:
                transcription = self.client.audio.transcriptions.create(
                    model=model, 
                    file=audio_file,
                    language="ru"
                )
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

    def correct_text(self, text: str, previous_messages: list = [], system_prompt: str = None, context_chars: int = 3000) -> str:
        model = self.config.get("correction_model", "gpt-4o-mini")
        try:
            # Default prompt
            if not system_prompt:
                system_prompt = "Ты — помощник, который исправляет распознанный текст."

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
            
            # Inject history
            if "{{history}}" in system_prompt:
                final_system_prompt = system_prompt.replace("{{history}}", history_text if history_text else "Нет контекста.")
            else:
                final_system_prompt = system_prompt
                if history_text:
                    final_system_prompt += f"\n\nContext:\n{history_text}"

            messages = [
                {"role": "system", "content": final_system_prompt},
                {"role": "user", "content": text}
            ]

            response = self.client.chat.completions.create(
                model=model,
                messages=messages
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.exception(f"Correction error: {e}")
            return text
