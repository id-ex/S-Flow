"""
Test script for S-Flow application
Tests core components without starting the GUI
"""
import sys
import os

# Setup path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

print("=" * 60)
print("S-Flow Component Test")
print("=" * 60)

# Test 1: Configuration
print("\n[1/6] Testing configuration...")
try:
    from core.config import load_settings, get_openai_key, APP_VERSION
    settings = load_settings()
    api_key = get_openai_key()

    print(f"  ✓ Version: {APP_VERSION}")
    print(f"  ✓ Settings loaded: {len(settings)} items")
    print(f"  ✓ API Key: {'✓ Present' if api_key else '✗ Missing'}")

    # Check required settings
    required_keys = ['hotkey', 'correction_model', 'transcription_model']
    for key in required_keys:
        if key in settings:
            print(f"  ✓ {key}: {settings[key]}")
        else:
            print(f"  ✗ Missing: {key}")
except Exception as e:
    print(f"  ✗ Error: {e}")
    sys.exit(1)

# Test 2: Locale Manager
print("\n[2/6] Testing locale manager...")
try:
    from core.locale_manager import tr, set_language, get_current_language
    set_language('ru')
    lang = get_current_language()
    test_text = tr("ready")
    print(f"  ✓ Current language: {lang}")
    print(f"  ✓ Translation test: 'ready' -> '{test_text}'")
except Exception as e:
    print(f"  ✗ Error: {e}")

# Test 3: API Client
print("\n[3/6] Testing API client...")
try:
    from core.api_client import ApiClient
    client = ApiClient(api_key)
    print(f"  ✓ ApiClient initialized")
    print(f"  ✓ Models: {settings.get('correction_model')}, {settings.get('transcription_model')}")
except Exception as e:
    print(f"  ✗ Error: {e}")

# Test 4: Audio Recorder
print("\n[4/6] Testing audio recorder...")
try:
    from core.audio_recorder import AudioRecorder
    recorder = AudioRecorder()
    print(f"  ✓ AudioRecorder initialized")
    print(f"  ✓ Sample rate: {recorder.sample_rate} Hz")
    print(f"  ✓ Channels: {recorder.channels}")
except Exception as e:
    print(f"  ✗ Error: {e}")

# Test 5: Text Processor
print("\n[5/6] Testing text processor...")
try:
    from core.text_process import TextProcessor
    processor = TextProcessor()
    print(f"  ✓ TextProcessor initialized")
except Exception as e:
    print(f"  ✗ Error: {e}")

# Test 6: Hotkey Manager (without actually registering)
print("\n[6/6] Testing hotkey manager...")
try:
    from core.hotkey_manager import HotkeyManager
    print(f"  ✓ HotkeyManager can be imported")
    print(f"  ✓ Standard hotkey: {settings.get('hotkey')}")
    print(f"  ✓ Translation hotkey: {settings.get('translation_hotkey')}")
    print(f"  ✓ Cancel hotkey: {settings.get('cancel_hotkey')}")
except Exception as e:
    print(f"  ✗ Error: {e}")

print("\n" + "=" * 60)
print("Component test completed!")
print("=" * 60)
