from openai import OpenAI
import os

class ApiClient:
    def __init__(self, api_key):
        self.client = OpenAI(api_key=api_key)

    def transcribe(self, audio_path):
        try:
            with open(audio_path, "rb") as audio_file:
                transcription = self.client.audio.transcriptions.create(
                    model="whisper-1", 
                    file=audio_file,
                    language="ru"
                )
            return transcription.text
        except Exception as e:
            print(f"Transcription error: {e}")
            return None

    def correct_text(self, text, previous_messages=[], system_prompt=None, context_chars=3000):
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
                model="gpt-4o-mini",
                messages=messages
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Correction error: {e}")
            return text
