"""
Unit tests for S-Flow core components
Run with: python -m pytest tests/test_core.py -v
"""
import os
import sys
import json
import pytest
from unittest.mock import Mock, MagicMock, patch, mock_open

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


class TestConfig:
    """Test configuration module"""

    def test_load_settings(self):
        """Test settings loading"""
        from core.config import load_settings

        with patch('builtins.open', mock_open(read_data='{"test": "value"}')):
            with patch('os.path.exists', return_value=True):
                settings = load_settings()
                # load_settings merges with defaults, so we check if our key is present
                assert settings["test"] == "value"
                assert "app_language" in settings

    def test_load_settings_file_not_found(self):
        """Test settings loading when file doesn't exist"""
        from core.config import load_settings, DEFAULT_SETTINGS

        with patch('os.path.exists', return_value=False):
            with patch('core.config.save_settings_file', return_value=True):
                settings = load_settings()
                assert settings == DEFAULT_SETTINGS

    def test_get_model_config(self):
        """Test model config retrieval"""
        from core.config import get_model_config

        settings = {
            "transcription_model": "whisper-1",
            "correction_model": "gpt-4o-mini",
            "transcription_language": "en"
        }

        config = get_model_config(settings)
        assert config["transcription_model"] == "whisper-1"
        assert config["correction_model"] == "gpt-4o-mini"
        assert config["transcription_language"] == "en"

    def test_get_model_config_defaults(self):
        """Test model config with defaults"""
        from core.config import get_model_config

        config = get_model_config({})
        assert config["transcription_model"] == "whisper-1"
        assert config["correction_model"] == "gpt-4o-mini"
        assert config["transcription_language"] == "ru"


class TestLocaleManager:
    """Test locale manager"""

    def test_locale_manager_singleton(self):
        """Test that LocaleManager is a singleton"""
        from core.locale_manager import LocaleManager

        manager1 = LocaleManager()
        manager2 = LocaleManager()
        assert manager1 is manager2

    def test_tr_function(self):
        """Test translation function"""
        from core.locale_manager import tr

        # Test fallback when key not found
        result = tr("non_existent_key")
        assert result == "non_existent_key"

    def test_set_language(self):
        """Test language setting"""
        from core.locale_manager import set_language, get_current_language

        # This should not crash even if locale file doesn't exist
        set_language("en")
        lang = get_current_language()
        assert lang == "en"


class TestAudioRecorder:
    """Test audio recorder"""

    def test_recorder_initialization(self):
        """Test recorder initialization with default parameters"""
        from core.audio_recorder import AudioRecorder

        recorder = AudioRecorder()
        assert recorder.sample_rate == 16000
        assert recorder.channels == 1
        assert recorder.recording is False
        assert recorder.stream is None
        assert recorder.on_error is None

    def test_recorder_initialization_with_on_error(self):
        """Test recorder initialization with on_error callback"""
        from core.audio_recorder import AudioRecorder

        error_handler = Mock()
        recorder = AudioRecorder(on_error=error_handler)
        assert recorder.on_error is error_handler

    def test_recorder_custom_parameters(self):
        """Test recorder with custom parameters"""
        from core.audio_recorder import AudioRecorder

        recorder = AudioRecorder(sample_rate=48000, channels=2)
        assert recorder.sample_rate == 48000
        assert recorder.channels == 2

    @patch('core.audio_recorder.sd')
    def test_start_recording(self, mock_sd):
        """Test recording start"""
        from core.audio_recorder import AudioRecorder

        mock_stream = MagicMock()
        mock_sd.InputStream.return_value = mock_stream

        recorder = AudioRecorder()
        recorder.start_recording()

        assert recorder.recording is True
        mock_sd.InputStream.assert_called_once()
        mock_stream.start.assert_called_once()

    @patch('core.audio_recorder.sd')
    def test_stop_recording_returns_list(self, mock_sd):
        """Test recording stop returns list of chunks (not BytesIO)"""
        from core.audio_recorder import AudioRecorder
        import numpy as np

        mock_stream = MagicMock()
        mock_sd.InputStream.return_value = mock_stream

        recorder = AudioRecorder()
        recorder.start_recording()
        
        # Simulate audio data in queue
        recorder.audio_queue.put(np.zeros((1600, 1), dtype=np.int16))
        
        result = recorder.stop_recording()

        assert recorder.recording is False
        assert isinstance(result, list)
        assert len(result) == 1
        mock_stream.stop.assert_called_once()
        mock_stream.close.assert_called_once()

    @patch('core.audio_recorder.sd')
    def test_stop_recording_no_data(self, mock_sd):
        """Test stop recording with no audio data"""
        from core.audio_recorder import AudioRecorder

        mock_stream = MagicMock()
        mock_sd.InputStream.return_value = mock_stream

        recorder = AudioRecorder()
        recorder.start_recording()
        result = recorder.stop_recording()

        assert result is None

    def test_encode_wav_too_short(self):
        """Test encode_wav rejects too-short recordings"""
        from core.audio_recorder import AudioRecorder
        import numpy as np

        # 0.1s at 16000Hz = 1600 samples, below 0.4s threshold
        frames = [np.zeros((1600, 1), dtype=np.int16)]
        result = AudioRecorder.encode_wav(frames, sample_rate=16000)
        assert result is None

    def test_encode_wav_silence(self):
        """Test encode_wav rejects silent recordings"""
        from core.audio_recorder import AudioRecorder
        import numpy as np

        # 1s of silence at 16000Hz
        frames = [np.zeros((16000, 1), dtype=np.int16)]
        result = AudioRecorder.encode_wav(frames, sample_rate=16000)
        assert result is None

    def test_encode_wav_success(self):
        """Test encode_wav returns BytesIO for valid audio"""
        from core.audio_recorder import AudioRecorder
        import numpy as np
        import io

        # 1s of non-silent audio at 16000Hz
        audio = np.random.randint(-500, 500, (16000, 1), dtype=np.int16)
        frames = [audio]
        result = AudioRecorder.encode_wav(frames, sample_rate=16000)
        assert isinstance(result, io.BytesIO)

    @patch('core.audio_recorder.sd')
    def test_start_recording_error_with_callback(self, mock_sd):
        """Test on_error callback is called when microphone fails"""
        from core.audio_recorder import AudioRecorder

        mock_sd.InputStream.side_effect = Exception("No microphone")
        error_handler = Mock()

        recorder = AudioRecorder(on_error=error_handler)
        recorder.start_recording()

        assert recorder.recording is False
        error_handler.assert_called_once_with("No microphone")


class TestTextProcessor:
    """Test text processor"""

    @patch('core.text_process.QTimer')
    @patch('core.text_process.pyperclip')
    @patch('core.text_process.keyboard')
    def test_paste_text(self, mock_keyboard, mock_pyperclip, mock_qtimer):
        """Test text paste functionality"""
        from core.text_process import TextProcessor

        test_text = "Test text to paste"
        TextProcessor.paste_text(test_text)

        mock_pyperclip.copy.assert_called_once_with(test_text)
        mock_qtimer.singleShot.assert_called_once()




class TestApiClient:
    """Test API client"""

    @patch('core.api_client.OpenAI')
    def test_client_initialization_with_keys(self, mock_openai):
        """Test client initialization with API keys"""
        from core.api_client import ApiClient

        # Setup side_effect to return distinct mocks for each call
        mock_openai_instance = MagicMock()
        mock_groq_instance = MagicMock()
        mock_openai.side_effect = [mock_openai_instance, mock_groq_instance]

        client = ApiClient(openai_key="test-openai", groq_key="test-groq")
        
        assert client.openai_client == mock_openai_instance
        assert client.groq_client == mock_groq_instance
        
        # Verify calls - Groq init uses base_url
        assert mock_openai.call_count == 2
        # First call is openai (based on init order in code: openai then groq)
        # Check specific call arguments if needed
        # We can inspect call_args_list
        calls = mock_openai.call_args_list
        assert calls[0].kwargs['api_key'] == "test-openai"
        assert calls[1].kwargs['api_key'] == "test-groq"
        assert calls[1].kwargs['base_url'] == "https://api.groq.com/openai/v1"

    def test_client_initialization_without_keys(self):
        """Test client initialization without API keys"""
        from core.api_client import ApiClient

        client = ApiClient()
        assert client.openai_client is None
        assert client.groq_client is None

    @patch('core.api_client.wave.open')
    def test_transcribe_no_client(self, mock_wave_open):
        """Test transcription when no clients are initialized"""
        from core.api_client import ApiClient

        # Mock wave duration
        mock_file = MagicMock()
        mock_file.getnframes.return_value = 44100
        mock_file.getframerate.return_value = 44100
        mock_wave_open.return_value.__enter__.return_value = mock_file

        client = ApiClient()
        # Mocking byte buffer as it expects file-like object or str
        from io import BytesIO
        buf = BytesIO(b"fake wav")
        buf.name = "audio.wav"

        text, duration, provider = client.transcribe(buf)
        assert text == "Error: No valid API provider configured"
        assert duration == 0.0

    @patch('core.api_client.OpenAI')
    def test_transcribe_groq_success(self, mock_openai):
        """Test successful transcription with Groq (Primary)"""
        from core.api_client import ApiClient

        # We need mock_openai to return mocks when instantiated
        mock_openai_inst = MagicMock()
        mock_groq_inst = MagicMock()
        mock_openai.side_effect = [mock_openai_inst, mock_groq_inst]
        
        mock_groq_inst.audio.transcriptions.create.return_value = MagicMock(text="Groq Transcription")

        client = ApiClient(openai_key="test-openai", groq_key="test-groq")
        
        from io import BytesIO
        buf = BytesIO(b"fake wav")
        buf.name = "audio.wav"
        
        text, duration, provider = client.transcribe(buf)

        assert text == "Groq Transcription"
        assert provider == "groq"
        mock_groq_inst.audio.transcriptions.create.assert_called()

    @patch('core.api_client.OpenAI')
    def test_transcribe_failover_to_openai(self, mock_openai):
        """Test failover from Groq to OpenAI"""
        from core.api_client import ApiClient

        mock_openai_inst = MagicMock()
        mock_groq_inst = MagicMock()
        mock_openai.side_effect = [mock_openai_inst, mock_groq_inst]

        # Simulate Groq error
        mock_groq_inst.audio.transcriptions.create.side_effect = Exception("Groq Error")
        
        # OpenAI success
        mock_openai_inst.audio.transcriptions.create.return_value = MagicMock(text="OpenAI Transcription")

        client = ApiClient(openai_key="test-openai", groq_key="test-groq")

        from io import BytesIO
        buf = BytesIO(b"fake wav")
        buf.name = "audio.wav"

        text, duration, provider = client.transcribe(buf)

        assert text == "OpenAI Transcription"
        assert provider == "openai"
        mock_groq_inst.audio.transcriptions.create.assert_called()
        mock_openai_inst.audio.transcriptions.create.assert_called()

    @patch('core.api_client.OpenAI')
    def test_correct_text_groq(self, mock_openai):
        """Test correct_text functionality using Groq"""
        from core.api_client import ApiClient

        mock_groq_inst = MagicMock()
        mock_openai.return_value = mock_groq_inst

        mock_response = MagicMock()
        mock_response.choices[0].message.content = "Corrected by Groq"
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_groq_inst.chat.completions.create.return_value = mock_response

        # Only init groq key so only one client created
        client = ApiClient(groq_key="test-groq")
        
        text, usage = client.correct_text("Original", provider="groq")

        assert text == "Corrected by Groq"
        assert usage["provider"] == "groq"
        # Verify model used
        call_args = mock_groq_inst.chat.completions.create.call_args
        assert call_args.kwargs['model'] == "llama-3.3-70b-versatile"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
