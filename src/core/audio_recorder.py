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
    def __init__(self, sample_rate: int = 44100, channels: int = 1):
        self.sample_rate = sample_rate
        self.channels = channels
        self.recording = False
        self.audio_queue = queue.Queue()
        self.stream = None
        self.filename = None

    def start_recording(self):
        if self.recording:
            return
        
        self.recording = True
        self.audio_queue = queue.Queue() # Reset queue
        
        def callback(indata, frames, time, status):
            if status:
                logger.warning(f"Audio recording status: {status}")
            self.audio_queue.put(indata.copy())

        try:
            self.stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype='int16',
                callback=callback
            )
            self.stream.start()
            logger.info("Recording started...")
        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            self.recording = False

    def stop_recording(self) -> str | None:
        if not self.recording or not self.stream:
            return None
            
        self.recording = False
        self.stream.stop()
        self.stream.close()
        logger.info("Recording stopped.")
        
        return self._save_from_queue()

    def _save_from_queue(self) -> str | None:
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
            logger.info(f"Audio saved to {path}")
            return path
        except Exception as e:
            logger.error(f"Failed to save audio file: {e}")
            return None
