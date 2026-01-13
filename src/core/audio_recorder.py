import sounddevice as sd
import numpy as np
import scipy.io.wavfile as wav
import tempfile
import threading
import os

class AudioRecorder:
    def __init__(self, sample_rate=44100):
        self.sample_rate = sample_rate
        self.recording = False
        self.frames = []
        self.thread = None
        self.stop_event = threading.Event()

    def start_recording(self):
        if self.recording:
            return
        
        self.recording = True
        self.frames = []
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._record_loop)
        self.thread.start()
        print("Recording started...")

    def stop_recording(self):
        if not self.recording:
            return None
            
        self.recording = False
        self.stop_event.set()
        self.thread.join()
        print("Recording stopped.")
        
        return self._save_to_temp_file()

    def _record_loop(self):
        with sd.InputStream(samplerate=self.sample_rate, channels=1, dtype='int16') as stream:
            while not self.stop_event.is_set():
                data, overflowed = stream.read(1024)
                if overflowed:
                    print("Audio overflowed!")
                self.frames.append(data)

    def _save_to_temp_file(self):
        if not self.frames:
            return None
            
        recording = np.concatenate(self.frames, axis=0)
        
        # Create temp file
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        
        wav.write(path, self.sample_rate, recording)
        return path
