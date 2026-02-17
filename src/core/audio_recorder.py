import sounddevice as sd
import numpy as np
import io
import wave
import threading
import logging
import queue
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class AudioRecorder:
    """
    Records audio from the default microphone to in-memory buffers.

    Uses sounddevice for audio capture with callback-based streaming.
    Audio data is buffered in a queue and returned as raw chunks on stop_recording().
    WAV encoding is done separately via the static encode_wav() method.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        on_error: Optional[Callable[[str], None]] = None,
    ) -> None:
        """
        Initialize audio recorder.

        Args:
            sample_rate: Sample rate in Hz (default: 16000 for efficiency)
            channels: Number of audio channels (default: 1 for mono)
            on_error: Optional callback for error notifications (e.g., no microphone)
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.recording = False
        self._lock = threading.Lock()
        self.audio_queue = queue.Queue()
        self.stream = None
        self.on_error = on_error

    def cleanup(self) -> None:
        """
        No-op for compatibility, as we no longer use temp files.
        """
        pass

    def start_recording(self) -> None:
        """Start recording audio from the default microphone."""
        with self._lock:
            if self.recording:
                return
            self.recording = True

        # Clear existing queue instead of creating new one
        while not self.audio_queue.empty():
            self.audio_queue.get()

        def callback(indata, frames, time, status):
            """Audio callback for sounddevice streaming."""
            if status:
                logger.warning(f"Audio recording status: {status}")
            self.audio_queue.put(indata.copy())

        try:
            self.stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="int16",
                callback=callback,
            )
            self.stream.start()
            logger.info("Recording started...")
        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            with self._lock:
                self.recording = False
            if self.on_error:
                self.on_error(str(e))

    def stop_recording(self) -> list | None:
        """
        Stop recording and return raw audio chunks.

        Returns:
            List of numpy arrays (raw audio chunks), or None if no data was recorded.
            Use AudioRecorder.encode_wav() to convert chunks to WAV BytesIO.
        """
        with self._lock:
            if not self.recording or not self.stream:
                return None
            self.recording = False

        self.stream.stop()
        self.stream.close()
        logger.info("Recording stopped.")

        frames = []
        while not self.audio_queue.empty():
            frames.append(self.audio_queue.get())

        if not frames:
            logger.warning("No audio data recorded.")
            return None

        return frames

    @staticmethod
    def encode_wav(
        frames: list,
        sample_rate: int = 16000,
        channels: int = 1,
        min_duration: float = 0.4,
        silence_threshold: int = 150,
    ) -> io.BytesIO | None:
        """
        Encode raw audio chunks into a WAV BytesIO buffer.

        This method is designed to be called from a background thread
        (e.g., ProcessingWorker) to avoid blocking the GUI.

        Args:
            frames: List of numpy arrays from stop_recording()
            sample_rate: Sample rate used during recording
            channels: Number of channels used during recording
            min_duration: Minimum duration in seconds to accept
            silence_threshold: Max amplitude below which audio is considered silence

        Returns:
            io.BytesIO with WAV data, or None if audio is too short/quiet
        """
        recording = np.concatenate(frames, axis=0)

        # Check for minimum duration
        duration = len(recording) / sample_rate
        if duration < min_duration:
            logger.info(f"Recording too short ({duration:.2f}s), skipping.")
            return None

        # Check for silence (max amplitude threshold)
        max_amplitude = np.max(np.abs(recording))
        if max_amplitude < silence_threshold:
            logger.info(f"Audio is too quiet (max amplitude {max_amplitude}), skipping.")
            return None

        # Create in-memory buffer
        try:
            audio_buffer = io.BytesIO()
            with wave.open(audio_buffer, "wb") as wav_file:
                wav_file.setnchannels(channels)
                wav_file.setsampwidth(2)  # 2 bytes for int16
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(recording.tobytes())

            audio_buffer.seek(0)
            logger.info("Audio saved to memory buffer")
            return audio_buffer
        except Exception as e:
            logger.error(f"Failed to save audio to memory: {e}")
            return None
