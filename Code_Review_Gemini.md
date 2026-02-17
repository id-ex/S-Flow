# Code Review Report

**Role:** Senior Python Desktop Developer (Expert in Qt/PySide)
**Date:** 2026-02-17

## 1. Thread Safety (Потокобезопасность)

*   **GUI Thread Blocking:** В целом архитектура корректна. Тяжелые сетевые запросы (`transcribe`, `correct_text`) вынесены в `ProcessingWorker` (QThread), что предотвращает зависание интерфейса.
*   **Скрытая проблема:** В методе `AudioRecorder.stop_recording()` происходит вызов `_save_from_queue()`, который выполняет `np.concatenate` и запись WAV в память.
    *   *Риск:* Операции с `numpy` в основном потоке (Main Thread) блокируют GUI. При коротких записях это незаметно, но при длительной диктовке (5+ минут) конкатенация большого массива данных вызовет "фриз" интерфейса на 0.5–2 секунды.
*   **Race Conditions:** В `main.py` при отмене (`cancel_operation`) используется `self.worker.finished.disconnect()`.
    *   *Риск:* Поток продолжает работать в фоне, потребляя трафик и платные токены API, даже если результат пользователю уже не нужен. Python API для OpenAI синхронный, поэтому "мягко" прервать его выполнение невозможно, но стоит учитывать этот расход ресурсов.

## 2. Code Style (Стиль кода)

*   **Соответствие стандартам:** Код написан чисто, соблюдается PEP 8. Имена переменных понятные (`snake_case`), классы — `PascalCase`.
*   **Qt Best Practices:**
    *   Использование `QTimer.singleShot` для отложенных действий — отлично.
    *   Сигналы определены как атрибуты класса (`finished = pyqtSignal(...)`) — корректно.
*   **Структура:** Логика хорошо разделена по модулям (`core` vs `ui`).
*   **Замечание:** `AppController` в `main.py` перегружен ответственностью (God Object). Он управляет и треем, и настройками, и записью, и обновлениями. Рекомендуется вынести логику трея в отдельный класс `TrayController`.

## 3. Robustness (Устойчивость)

*   **API Client:** Реализована отличная логика повторных попыток (`_execute_with_retry`) с экспоненциальной задержкой. Это критически важно для нестабильных соединений.
*   **Ресурсы:** Использование `get_resource_path` с учетом `sys._MEIPASS` гарантирует корректную работу после сборки через PyInstaller.
*   **Single Instance:** Использование `CreateMutexW` — надежное решение для Windows, предотвращающее запуск копий приложения.
*   **Обработка ошибок:** В `ProcessingWorker` есть широкий `try-except`, который спасает приложение от падения ("крэша"), но возвращаемые ошибки (`tr("error_unknown")`) могли бы быть информативнее для отладки.

## 4. Refactored Fragment

Для решения проблемы блокировки UI при сохранении аудио (пункт 1), предлагаю перенести "тяжелую" сборку WAV-файла из `AudioRecorder` (Main Thread) в `ProcessingWorker` (Background Thread).

**Изменения:**
1.  `AudioRecorder` должен отдавать "сырые" данные (список chunks), не тратя время на склейку.
2.  `ProcessingWorker` принимает сырые данные и сам собирает их в WAV перед отправкой.

```python
# 1. Изменяем core/audio_recorder.py
class AudioRecorder:
    # ... (init и start без изменений)

    def stop_recording(self) -> list | None:
        """
        Stops stream and returns raw list of numpy arrays immediately.
        Non-blocking for UI.
        """
        if not self.recording or not self.stream:
            return None

        self.recording = False
        self.stream.stop()
        self.stream.close()
        
        # Возвращаем список чанков моментально, без конкатенации
        raw_frames = []
        while not self.audio_queue.empty():
            raw_frames.append(self.audio_queue.get())
            
        logger.info("Recording stopped. Raw frames returned.")
        return raw_frames

    @staticmethod
    def encode_audio(frames: list, sample_rate: int, channels: int) -> io.BytesIO | None:
        """
        Static method to encode audio. Heavy lifting designed for a worker thread.
        """
        if not frames:
            return None
            
        try:
            # Heavy operation: allocation and copy
            recording = np.concatenate(frames, axis=0) 
            
            # Validation logic moved here
            duration = len(recording) / sample_rate
            if duration < 0.4:
                return None
                
            audio_buffer = io.BytesIO()
            with wave.open(audio_buffer, "wb") as wav_file:
                wav_file.setnchannels(channels)
                wav_file.setsampwidth(2)
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(recording.tobytes())
            
            audio_buffer.seek(0)
            return audio_buffer
        except Exception as e:
            logger.error(f"Encoding error: {e}")
            return None

# 2. Обновляем Worker в src/main.py
class ProcessingWorker(QThread):
    def __init__(self, api_client, raw_frames, sample_rate, ...):
        super().__init__()
        self.raw_frames = raw_frames # Принимаем сырые данные
        self.sample_rate = sample_rate
        # ... остальные аргументы

    def run(self):
        try:
            logger.info("Encoding audio in worker thread...")
            # Тяжелая операция теперь здесь, UI не фризится
            audio_buffer = AudioRecorder.encode_audio(
                self.raw_frames, 
                self.sample_rate, 
                channels=1
            )
            
            if not audio_buffer:
                self.finished.emit("", "NoSpeech", {})
                return

            # Дальше логика транскрибации как обычно...
            raw_text, duration, provider = self.api_client.transcribe(audio_buffer)
            # ...
```
