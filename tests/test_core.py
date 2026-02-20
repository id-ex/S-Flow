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
# Add src to path
# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from core.exceptions import (
    SFlowError,
    AuthenticationError,
    RateLimitError,
    APIConnectionError,
    TranscriptionError
)

from core.exceptions import (
    SFlowError,
    AuthenticationError,
    RateLimitError,
    APIConnectionError,
    TranscriptionError
)


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

    @patch('core.config.get_app_dir')
    def test_settings_creation_real(self, mock_get_app_dir, tmp_path):
        """Test real creation of settings.json in temporary directory"""
        from core.config import load_settings, DEFAULT_SETTINGS, SETTINGS_PATH
        import json
        
        # We need to ensure load_settings uses our temp path.
        # SETTINGS_PATH in core.config is a global constant computed at import time.
        # Patching get_app_dir works if we reload the module or if SETTINGS_PATH wasn't cached?
        # No, it's cached.
        # We must patch 'core.config.SETTINGS_PATH' directly.
        
        temp_settings_path = tmp_path / "settings.json"
        
        with patch('core.config.SETTINGS_PATH', str(temp_settings_path)):
            # Ensure file doesn't exist
            if os.path.exists(temp_settings_path):
                os.remove(temp_settings_path)
                
            settings = load_settings()
            
            assert os.path.exists(temp_settings_path)
            # Default settings might define keys not in DEFAULT_SETTINGS? No.
            # Compare keys or full dict
            assert settings == DEFAULT_SETTINGS
            
            # verify content
            with open(temp_settings_path, 'r', encoding='utf-8') as f:
                content = json.load(f)
                assert content == DEFAULT_SETTINGS

    @patch('core.config.get_app_dir')
    def test_settings_creation_real(self, mock_get_app_dir, tmp_path):
        """Test real creation of settings.json in temporary directory"""
        from core.config import load_settings, DEFAULT_SETTINGS, SETTINGS_PATH
        
        # Override SETTINGS_PATH logic by patching where it's used or ensuring we use a temp path
        # config.py uses os.path.join(get_app_dir(), "settings.json") for SETTINGS_PATH
        # But SETTINGS_PATH is a module-level constant computed at import time!
        # Patching get_app_dir AFTER import might not change SETTINGS_PATH.
        # However, we can patch core.config.SETTINGS_PATH directly.
        
        temp_settings_path = tmp_path / "settings.json"
        mock_get_app_dir.return_value = str(tmp_path)
        
        with patch('core.config.SETTINGS_PATH', str(temp_settings_path)):
            # Ensure file doesn't exist
            if os.path.exists(temp_settings_path):
                os.remove(temp_settings_path)
                
            settings = load_settings()
            
            assert os.path.exists(temp_settings_path)
            assert settings == DEFAULT_SETTINGS
            
            # verify content
            with open(temp_settings_path, 'r', encoding='utf-8') as f:
                content = json.load(f)
                assert content == DEFAULT_SETTINGS


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

    @patch('core.text_process.threading.Timer')
    @patch('core.text_process.pyperclip')
    @patch('core.text_process.keyboard')
    def test_paste_text(self, mock_keyboard, mock_pyperclip, mock_timer):
        """Test text paste functionality"""
        from core.text_process import TextProcessor

        test_text = "Test text to paste"
        TextProcessor.paste_text(test_text)

        mock_pyperclip.copy.assert_called_once_with(test_text)
        mock_timer.assert_called_once()
        mock_timer.return_value.start.assert_called_once()




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

    @patch('core.api_client.OpenAI')
    @patch('core.api_client.wave.open')
    def test_transcribe_no_client(self, mock_wave_open, mock_openai):
        """Test transcription when no clients are initialized raises TranscriptionError"""
        from core.api_client import ApiClient
        
        # Mock wave duration
        mock_file = MagicMock()
        mock_file.getnframes.return_value = 44100
        mock_file.getframerate.return_value = 44100
        mock_wave_open.return_value.__enter__.return_value = mock_file

        client = ApiClient()
        from io import BytesIO
        buf = BytesIO(b"fake wav")
        buf.name = "audio.wav"

        # Should raise TranscriptionError now
        with pytest.raises(TranscriptionError) as excinfo:
            client.transcribe(buf)
        
        assert "No valid API provider configured" in str(excinfo.value)

    @patch('core.api_client.OpenAI')
    @patch('core.api_client.wave.open')
    def test_transcribe_groq_success(self, mock_wave_open, mock_openai):
        """Test successful transcription with Groq (Primary)"""
        from core.api_client import ApiClient

        # Mock wave
        mock_file = MagicMock()
        mock_file.getnframes.return_value = 44100
        mock_file.getframerate.return_value = 44100
        mock_wave_open.return_value.__enter__.return_value = mock_file

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
    @patch('core.api_client.wave.open')
    def test_transcribe_failover_to_openai(self, mock_wave_open, mock_openai):
        """Test failover from Groq to OpenAI"""
        from core.api_client import ApiClient
        
        # Mock wave
        mock_file = MagicMock()
        mock_file.getnframes.return_value = 44100
        mock_file.getframerate.return_value = 44100
        mock_wave_open.return_value.__enter__.return_value = mock_file

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
    @patch('core.api_client.wave.open')
    def test_transcribe_openai_auth_error(self, mock_wave_open, mock_openai):
        """Test OpenAI AuthenticationError raises SFlowAuthError"""
        from core.api_client import ApiClient
        from openai import AuthenticationError as OpenAIAuthError

        # Mock wave
        mock_file = MagicMock()
        mock_file.getnframes.return_value = 44100
        mock_file.getframerate.return_value = 44100
        mock_wave_open.return_value.__enter__.return_value = mock_file

        mock_openai_inst = MagicMock()
        mock_openai.return_value = mock_openai_inst # Only OpenAI key provided
        
        mock_openai_inst.audio.transcriptions.create.side_effect = OpenAIAuthError("Invalid key", response=Mock(), body={})

        client = ApiClient(openai_key="test-openai")

        from io import BytesIO
        buf = BytesIO(b"fake wav")
        buf.name = "audio.wav"

        with pytest.raises(AuthenticationError):
            client.transcribe(buf)

    @patch('core.api_client.OpenAI')
    @patch('core.api_client.wave.open')
    def test_transcribe_openai_rate_limit(self, mock_wave_open, mock_openai):
        """Test OpenAI RateLimitError raises SFlowRateLimitError"""
        from core.api_client import ApiClient
        from openai import RateLimitError as OpenAIRateError

        # Mock wave
        mock_file = MagicMock()
        mock_file.getnframes.return_value = 44100
        mock_file.getframerate.return_value = 44100
        mock_wave_open.return_value.__enter__.return_value = mock_file

        mock_openai_inst = MagicMock()
        mock_openai.return_value = mock_openai_inst

        # First call fails immediately for simplicity (we Mock _execute_with_retry usually, but here checking wrapper)
        # But wait, _execute_with_retry retries. 
        # If we want to test exception wrapping, we need _execute_with_retry to raise the exception.
        # _execute_with_retry raises exception after MAX_RETRIES.
        
        # Let's mock _execute_with_retry internal logic or just force exception
        # ApiClient uses _execute_with_retry internally.
        # If we patch Audio.transcriptions.create to raise RateLimitError every time, 
        # _execute_with_retry will retry N times then raise it.
        # Then transcribe catches it and wraps it.
        
        # Speed up retry delay
        with patch('core.api_client.RETRY_DELAY', 0.001):
            mock_openai_inst.audio.transcriptions.create.side_effect = OpenAIRateError("Rate limit", response=Mock(), body={})
            
            client = ApiClient(openai_key="test-openai")
            from io import BytesIO
            buf = BytesIO(b"fake wav")
            buf.name = "audio.wav"

            with pytest.raises(RateLimitError):
                client.transcribe(buf)

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
        
        text, usage = client.correct_text("Original", provider="groq", system_prompt="Fix it")

        assert text == "Corrected by Groq"
        assert usage["provider"] == "groq"
        # Verify model used
        call_args = mock_groq_inst.chat.completions.create.call_args
        assert call_args.kwargs['model'] == "llama-3.3-70b-versatile"


class TestExceptions:
    """Test custom exceptions"""

    def test_sflow_error_basic(self):
        """Test SFlowError basic functionality"""
        from core.exceptions import SFlowError

        error = SFlowError("Technical message")
        assert str(error) == "Technical message"
        assert error.user_message == "Technical message"

    def test_sflow_error_with_user_message(self):
        """Test SFlowError with custom user message"""
        from core.exceptions import SFlowError

        error = SFlowError("Technical message", "User friendly message")
        assert str(error) == "Technical message"
        assert error.user_message == "User friendly message"

    def test_authentication_error(self):
        """Test AuthenticationError"""
        from core.exceptions import AuthenticationError

        error = AuthenticationError()
        assert "Invalid API Key" in error.user_message

    def test_transcription_error(self):
        """Test TranscriptionError"""
        from core.exceptions import TranscriptionError

        error = TranscriptionError("Transcription failed")
        assert "Transcription Failed" in error.user_message

    def test_api_connection_error(self):
        """Test APIConnectionError"""
        from core.exceptions import APIConnectionError

        error = APIConnectionError()
        assert "No Connection" in error.user_message

    def test_rate_limit_error(self):
        """Test RateLimitError"""
        from core.exceptions import RateLimitError

        error = RateLimitError()
        assert "Rate Limit" in error.user_message

    def test_audio_recording_error(self):
        """Test AudioRecordingError"""
        from core.exceptions import AudioRecordingError

        error = AudioRecordingError("Mic not found")
        assert "Audio recording failed" in error.user_message

    def test_configuration_error(self):
        """Test ConfigurationError"""
        from core.exceptions import ConfigurationError

        error = ConfigurationError("Invalid config")
        assert "Invalid config" in error.user_message

    def test_hotkey_error(self):
        """Test HotkeyError"""
        from core.exceptions import HotkeyError

        error = HotkeyError("Hotkey registration failed")
        assert "Hotkey operation failed" in error.user_message


class TestStatsManager:
    """Test stats manager"""

    def test_stats_manager_initialization(self):
        """Test StatsManager initialization"""
        from core.stats_manager import StatsManager

        with patch('core.stats_manager.get_app_dir', return_value='.'):
            with patch.object(StatsManager, 'load_stats', return_value={
                "total_seconds": 0.0,
                "total_prompt_tokens": 0,
                "total_completion_tokens": 0,
                "last_reset": "2024-01-01 00:00:00"
            }):
                manager = StatsManager()
                assert manager.stats["total_seconds"] == 0.0

    def test_add_usage(self):
        """Test adding usage data"""
        from core.stats_manager import StatsManager

        with patch('core.stats_manager.get_app_dir', return_value='.'):
            manager = StatsManager.__new__(StatsManager)
            manager.stats = {
                "total_seconds": 10.0,
                "total_prompt_tokens": 100,
                "total_completion_tokens": 50,
                "last_reset": "2024-01-01"
            }
            manager.stats_path = "stats.json"
            
            with patch.object(manager, 'save_stats'):
                manager.add_usage(whisper_seconds=5.0, prompt_tokens=50, completion_tokens=25)
                
                assert manager.stats["total_seconds"] == 15.0
                assert manager.stats["total_prompt_tokens"] == 150
                assert manager.stats["total_completion_tokens"] == 75

    def test_calculate_costs(self):
        """Test cost calculation"""
        from core.stats_manager import StatsManager

        with patch('core.stats_manager.get_app_dir', return_value='.'):
            manager = StatsManager.__new__(StatsManager)
            manager.stats = {
                "total_seconds": 60.0,  # 1 minute
                "total_prompt_tokens": 1000000,  # 1M tokens
                "total_completion_tokens": 500000,  # 0.5M tokens
                "last_reset": "2024-01-01"
            }
            
            with patch.object(manager, 'get_pricing', return_value={
                "whisper_price": 0.006,
                "gpt_input_price": 0.15,
                "gpt_output_price": 0.60
            }):
                costs = manager.calculate_costs()
                
                # Whisper: 1 min * $0.006 = $0.006
                assert costs["whisper_cost"] == 0.006
                # GPT input: 1M * $0.15/1M = $0.15
                assert costs["gpt_input_cost"] == 0.15
                # GPT output: 0.5M * $0.60/1M = $0.30
                assert costs["gpt_output_cost"] == 0.30
                # Total (use approx for floating point comparison)
                assert abs(costs["total_cost"] - 0.456) < 0.0001

    def test_reset_stats(self):
        """Test stats reset"""
        from core.stats_manager import StatsManager

        with patch('core.stats_manager.get_app_dir', return_value='.'):
            manager = StatsManager.__new__(StatsManager)
            manager.stats = {
                "total_seconds": 100.0,
                "total_prompt_tokens": 1000,
                "total_completion_tokens": 500,
                "last_reset": "2024-01-01"
            }
            manager.stats_path = "stats.json"
            
            with patch.object(manager, 'save_stats'):
                manager.reset_stats()
                
                assert manager.stats["total_seconds"] == 0.0
                assert manager.stats["total_prompt_tokens"] == 0
                assert manager.stats["total_completion_tokens"] == 0

    def test_get_pricing_defaults(self):
        """Test getting default pricing"""
        from core.stats_manager import StatsManager

        with patch('core.stats_manager.load_settings', return_value={}):
            manager = StatsManager.__new__(StatsManager)
            pricing = manager.get_pricing()
            
            assert pricing["whisper_price"] == 0.006
            assert pricing["gpt_input_price"] == 0.15
            assert pricing["gpt_output_price"] == 0.60


class TestConfigExtended:
    """Extended tests for config module"""

    def test_get_app_dir_frozen(self):
        """Test get_app_dir when frozen (PyInstaller)"""
        from core.config import get_app_dir

        with patch.object(sys, 'frozen', True, create=True):
            with patch('core.config.sys.executable', '/path/to/exe'):
                result = get_app_dir()
                assert result == os.path.dirname('/path/to/exe')

    def test_get_resource_path_frozen(self):
        """Test get_resource_path when frozen"""
        from core.config import get_resource_path

        # Create a mock sys module with _MEIPASS attribute
        mock_sys = MagicMock()
        mock_sys.frozen = True
        mock_sys._MEIPASS = '/temp/meipass'
        
        with patch('core.config.sys', mock_sys):
            result = get_resource_path('assets/icon.ico')
            assert 'assets/icon.ico' in result

    def test_save_settings_file_success(self):
        """Test save_settings_file success"""
        from core.config import save_settings_file

        with patch('builtins.open', mock_open()):
            with patch('core.config.SETTINGS_PATH', 'settings.json'):
                result = save_settings_file({"test": "value"})
                assert result is True

    def test_save_settings_file_error(self):
        """Test save_settings_file error handling"""
        from core.config import save_settings_file

        with patch('builtins.open', side_effect=PermissionError("No access")):
            with patch('core.config.SETTINGS_PATH', 'settings.json'):
                result = save_settings_file({"test": "value"})
                assert result is False

    def test_get_keys(self):
        """Test get_keys function"""
        from core.config import get_keys

        settings = {"openai_api_key": "key1", "groq_api_key": "key2"}
        with patch('core.config.load_settings', return_value=settings):
            keys = get_keys()
            assert keys["openai_api_key"] == "key1"
            assert keys["groq_api_key"] == "key2"

    def test_load_settings_migration(self):
        """Test settings migration from old api_key"""
        from core.config import load_settings, DEFAULT_SETTINGS

        old_settings = {"api_key": "old_key", "hotkey": "alt+a"}
        
        with patch('os.path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data=json.dumps(old_settings))):
                with patch('core.config.SETTINGS_PATH', 'settings.json'):
                    settings = load_settings()
                    # Old key should be migrated
                    assert settings.get("openai_api_key") == "old_key"
                    # Old key should be removed
                    assert "api_key" not in settings

    def test_load_settings_error(self):
        """Test load_settings error handling"""
        from core.config import load_settings, DEFAULT_SETTINGS

        with patch('os.path.exists', return_value=True):
            with patch('builtins.open', side_effect=json.JSONDecodeError("error", "", 0)):
                with patch('core.config.SETTINGS_PATH', 'settings.json'):
                    settings = load_settings()
                    assert settings == DEFAULT_SETTINGS


class TestApiClientExtended:
    """Extended tests for API client"""

    def test_process_text_normal(self):
        """Test _process_text with normal text"""
        from core.api_client import ApiClient

        client = ApiClient()
        text, duration, provider = client._process_text("Hello world", 5.0, "groq")
        
        assert text == "Hello world"
        assert duration == 5.0
        assert provider == "groq"

    def test_process_text_hallucination(self):
        """Test _process_text filters hallucinations"""
        from core.api_client import ApiClient

        client = ApiClient()
        # Short text with hallucination artifact
        text, duration, provider = client._process_text("редактор субтитров", 2.0, "groq")
        
        assert text == ""  # Should be filtered

    def test_process_text_too_short(self):
        """Test _process_text with too short text"""
        from core.api_client import ApiClient

        client = ApiClient()
        text, duration, provider = client._process_text("a", 1.0, "groq")
        
        assert text == ""

    def test_correct_text_no_client(self):
        """Test correct_text when no client available"""
        from core.api_client import ApiClient

        client = ApiClient()  # No keys
        text, usage = client.correct_text("Original text", provider="groq")
        
        assert text == "Original text"
        assert usage == {}

    @patch('core.api_client.OpenAI')
    def test_correct_text_with_context(self, mock_openai):
        """Test correct_text with previous messages context"""
        from core.api_client import ApiClient

        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "Corrected text"
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        mock_client.chat.completions.create.return_value = mock_response

        client = ApiClient(openai_key="test-key")
        
        previous_messages = [
            {"text": "Previous message 1"},
            {"text": "Previous message 2"}
        ]
        
        text, usage = client.correct_text(
            "Test text",
            provider="openai",
            previous_messages=previous_messages,
            user_context="Programming context"
        )
        
        assert text == "Corrected text"
        assert usage["prompt_tokens"] == 100
        
        # Verify context was injected
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs['messages']
        assert "Programming context" in messages[0]['content']

    @patch('core.api_client.OpenAI')
    def test_correct_text_translation_mode(self, mock_openai):
        """Test correct_text in translation mode"""
        from core.api_client import ApiClient

        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "Translated text"
        mock_response.usage.prompt_tokens = 50
        mock_response.usage.completion_tokens = 20
        mock_client.chat.completions.create.return_value = mock_response

        client = ApiClient(openai_key="test-key")
        
        text, usage = client.correct_text(
            "Текст для перевода",
            provider="openai",
            system_prompt="Ты — переводчик...",
            is_translation=True
        )
        
        assert text == "Translated text"
        
        # Verify translation prompt was used
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs['messages']
        assert "переводчик" in messages[0]['content'].lower()


class TestHotkeyManager:
    """Test hotkey manager"""

    @patch('core.hotkey_manager.keyboard')
    def test_hotkey_manager_start(self, mock_keyboard):
        """Test hotkey manager start"""
        from core.hotkey_manager import HotkeyManager

        manager = HotkeyManager("ctrl+alt+s")
        manager.start()
        
        mock_keyboard.add_hotkey.assert_called_once_with(
            "ctrl+alt+s", manager.on_trigger, suppress=True
        )

    @patch('core.hotkey_manager.keyboard')
    def test_hotkey_manager_stop(self, mock_keyboard):
        """Test hotkey manager stop"""
        from core.hotkey_manager import HotkeyManager

        manager = HotkeyManager("ctrl+alt+s")
        manager.stop()
        
        mock_keyboard.remove_hotkey.assert_called_once_with("ctrl+alt+s")

    @patch('core.hotkey_manager.keyboard')
    def test_update_hotkey_same(self, mock_keyboard):
        """Test update_hotkey with same combination"""
        from core.hotkey_manager import HotkeyManager

        manager = HotkeyManager("ctrl+alt+s")
        result = manager.update_hotkey("ctrl+alt+s")
        
        assert result is True
        mock_keyboard.remove_hotkey.assert_not_called()

    @patch('core.hotkey_manager.keyboard')
    def test_update_hotkey_different(self, mock_keyboard):
        """Test update_hotkey with different combination"""
        from core.hotkey_manager import HotkeyManager

        manager = HotkeyManager("ctrl+alt+s")
        result = manager.update_hotkey("ctrl+alt+d")
        
        assert result is True
        assert manager.combination == "ctrl+alt+d"
        mock_keyboard.remove_hotkey.assert_called()
        mock_keyboard.add_hotkey.assert_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
