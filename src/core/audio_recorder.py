import sounddevice as sd
import numpy as np
import io
import wave
import threading
import logging
import queue

logger = logging.getLogger(__name__)


class AudioRecorder:
    """
    Records audio from the default microphone to in-memory buffers.

    Uses sounddevice for audio capture with callback-based streaming.
    Audio data is buffered in a queue and saved to a BytesIO object on stop_recording().
    """

    def __init__(self, sample_rate: int = 16000, channels: int = 1) -> None:
        """
        Initialize audio recorder.

        Args:
            sample_rate: Sample rate in Hz (default: 16000 for efficiency)
            channels: Number of audio channels (default: 1 for mono)
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.recording = False
        self.audio_queue = queue.Queue()
        self.stream = None

    def cleanup(self) -> None:
        """
        No-op for compatibility, as we no longer use temp files.
        """
        pass

    def start_recording(self) -> None:
        """Start recording audio from the default microphone."""
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
            self.recording = False

    def stop_recording(self) -> io.BytesIO | None:
        """
        Stop recording and save audio to an in-memory buffer.

        Returns:
            io.BytesIO object containing WAV data, or None if no data was recorded
        """
        if not self.recording or not self.stream:
            return None

        self.recording = False
        self.stream.stop()
        self.stream.close()
        logger.info("Recording stopped.")

        return self._save_from_queue()

    def _save_from_queue(self) -> io.BytesIO | None:
        """
        Save queued audio data to an in-memory buffer.

        Returns:
            io.BytesIO object containing WAV data, or None if saving failed
        """
        frames = []
        while not self.audio_queue.empty():
            frames.append(self.audio_queue.get())

        if not frames:
            logger.warning("No audio data recorded.")
            return None

        recording = np.concatenate(frames, axis=0)

        # Check for minimum duration (e.g., 0.4 seconds)
        duration = len(recording) / self.sample_rate
        if duration < 0.4:
            logger.info(f"Recording too short ({duration:.2f}s), skipping.")
            return None

        # Check for silence (max amplitude threshold)
        max_amplitude = np.max(np.abs(recording))
        if max_amplitude < 150:
            logger.info(f"Audio is too quiet (max amplitude {max_amplitude}), skipping.")
            return None

        # Create in-memory buffer
        try:
            audio_buffer = io.BytesIO()
            with wave.open(audio_buffer, "wb") as wav_file:
                wav_file.setnchannels(self.channels)
                wav_file.setsampwidth(2)  # 2 bytes for int16
                wav_file.setframerate(self.sample_rate)
                wav_file.writeframes(recording.tobytes())
            
            audio_buffer.seek(0)
            logger.info("Audio saved to memory buffer")
            return audio_buffer
        except Exception as e:
            logger.error(f"Failed to save audio to memory: {e}")
            return None
