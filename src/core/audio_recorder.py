"""
Audio Recorder module for capturing microphone input.

This module provides functionality to record audio from the default microphone
and save it to temporary WAV files for transcription.
"""

import sounddevice as sd
import numpy as np
import scipy.io.wavfile as wav
import tempfile
import threading
import os
import logging
import queue

logger = logging.getLogger(__name__)


class AudioRecorder:
    """
    Records audio from the default microphone to temporary WAV files.

    Uses sounddevice for audio capture with callback-based streaming.
    Audio data is buffered in a queue and saved on stop_recording().
    """

    def __init__(self, sample_rate: int = 44100, channels: int = 1) -> None:
        """
        Initialize audio recorder.

        Args:
            sample_rate: Sample rate in Hz (default: 44100)
            channels: Number of audio channels (default: 1 for mono)
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.recording = False
        self.audio_queue = queue.Queue()
        self.stream = None
        self.filename = None
        self.temp_files = []  # Track created temp files for cleanup

    def cleanup(self) -> None:
        """Remove all temporary audio files created during recording sessions."""
        for path in self.temp_files:
            try:
                if os.path.exists(path):
                    os.unlink(path)
                    logger.debug(f"Cleaned up temp file: {path}")
            except Exception as e:
                logger.warning(f"Failed to delete temp file {path}: {e}")
        self.temp_files.clear()

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

    def stop_recording(self) -> str | None:
        """
        Stop recording and save audio to a temporary WAV file.

        Returns:
            Path to the temporary WAV file, or None if no data was recorded
        """
        if not self.recording or not self.stream:
            return None

        self.recording = False
        self.stream.stop()
        self.stream.close()
        logger.info("Recording stopped.")

        return self._save_from_queue()

    def _save_from_queue(self) -> str | None:
        """
        Save queued audio data to a temporary WAV file.

        Returns:
            Path to the temporary WAV file, or None if saving failed
        """
        frames = []
        while not self.audio_queue.empty():
            frames.append(self.audio_queue.get())

        if not frames:
            logger.warning("No audio data recorded.")
            return None

        recording = np.concatenate(frames, axis=0)

        # Create temp file
        try:
            fd, path = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            wav.write(path, self.sample_rate, recording)
            self.temp_files.append(path)  # Track for cleanup
            logger.info(f"Audio saved to {path}")
            return path
        except Exception as e:
            logger.error(f"Failed to save audio file: {e}")
            return None
