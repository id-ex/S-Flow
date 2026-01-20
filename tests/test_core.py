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
                assert settings == {"test": "value"}

    def test_load_settings_file_not_found(self):
        """Test settings loading when file doesn't exist"""
        from core.config import load_settings

        with patch('os.path.exists', return_value=False):
            settings = load_settings()
            assert settings == {}

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
        assert recorder.sample_rate == 44100
        assert recorder.channels == 1
        assert recorder.recording is False
        assert recorder.stream is None

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
    def test_stop_recording(self, mock_sd):
        """Test recording stop"""
        from core.audio_recorder import AudioRecorder

        mock_stream = MagicMock()
        mock_sd.InputStream.return_value = mock_stream

        recorder = AudioRecorder()
        recorder.start_recording()
        recorder.stop_recording()

        assert recorder.recording is False
        mock_stream.stop.assert_called_once()
        mock_stream.close.assert_called_once()


class TestTextProcessor:
    """Test text processor"""

    @patch('core.text_process.time')
    @patch('core.text_process.pyperclip')
    @patch('core.text_process.keyboard')
    def test_paste_text(self, mock_keyboard, mock_pyperclip, mock_time):
        """Test text paste functionality"""
        from core.text_process import TextProcessor

        test_text = "Test text to paste"
        TextProcessor.paste_text(test_text)

        mock_pyperclip.copy.assert_called_once_with(test_text)
        mock_keyboard.send.assert_called_once_with('ctrl+v')
        mock_time.sleep.assert_called_once_with(0.2)


class TestApiClient:
    """Test API client"""

    @patch('core.api_client.OpenAI')
    def test_client_initialization_with_key(self, mock_openai):
        """Test client initialization with API key"""
        from core.api_client import ApiClient

        client = ApiClient("test-api-key")
        assert client.client is not None
        assert client.config["transcription_model"] == "whisper-1"
        assert client.config["correction_model"] == "gpt-4o-mini"

    def test_client_initialization_without_key(self):
        """Test client initialization without API key"""
        from core.api_client import ApiClient

        client = ApiClient()
        assert client.client is None

    @patch('core.api_client.wave.open')
    def test_transcribe_no_client(self, mock_wave_open):
        """Test transcription when client is not initialized"""
        from core.api_client import ApiClient

        # Mock wave duration
        mock_file = MagicMock()
        mock_file.getnframes.return_value = 44100
        mock_file.getframerate.return_value = 44100
        mock_wave_open.return_value.__enter__.return_value = mock_file

        client = ApiClient()
        text, duration = client.transcribe("test_audio.wav")
        assert text == "Error: Invalid API Key"
        assert duration == 0.0

    @patch('core.api_client.wave.open')
    @patch('core.api_client.OpenAI')
    def test_transcribe_success(self, mock_openai, mock_wave_open):
        """Test successful transcription"""
        from core.api_client import ApiClient

        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_client.audio.transcriptions.create.return_value = MagicMock(text="Hello world")

        # Mock wave duration
        mock_file = MagicMock()
        mock_file.getnframes.return_value = 88200
        mock_file.getframerate.return_value = 44100
        mock_wave_open.return_value.__enter__.return_value = mock_file

        client = ApiClient("test-key")
        with patch('builtins.open', mock_open(read_data=b"audio data")):
            text, duration = client.transcribe("test_audio.wav")

        assert text == "Hello world"
        assert duration == 2.0

    @patch('core.api_client.OpenAI')
    def test_correct_text_success(self, mock_openai):
        """Test successful text correction"""
        from core.api_client import ApiClient

        mock_client = MagicMock()
        mock_openai.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices[0].message.content = "Corrected text"
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_client.chat.completions.create.return_value = mock_response

        client = ApiClient("test-key")
        text, usage = client.correct_text("Original text")

        assert text == "Corrected text"
        assert usage["prompt_tokens"] == 10
        assert usage["completion_tokens"] == 5

    @patch('core.api_client.OpenAI')
    def test_execute_with_retry_success(self, mock_openai):
        """Test successful API call with retry logic"""
        from core.api_client import ApiClient

        mock_client = MagicMock()
        mock_openai.return_value = mock_client

        client = ApiClient("test-key")

        # Mock function that succeeds
        def mock_func():
            return "success"

        result = client._execute_with_retry(mock_func)
        assert result == "success"

    @patch('core.api_client.OpenAI')
    @patch('core.api_client.time.sleep')
    def test_execute_with_retry_rate_limit(self, mock_sleep, mock_openai):
        """Test retry logic on rate limit error"""
        from core.api_client import ApiClient
        from openai import RateLimitError

        mock_client = MagicMock()
        mock_openai.return_value = mock_client

        client = ApiClient("test-key")

        call_count = 0

        def mock_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                # Create a proper RateLimitError with required arguments
                response = MagicMock()
                response.status_code = 429
                raise RateLimitError("Rate limit exceeded", response=response, body="")
            return "success"

        result = client._execute_with_retry(mock_func)
        assert result == "success"
        assert call_count == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
