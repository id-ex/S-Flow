# AGENTS.md

Guide for agentic coding agents working on S-Flow repository.

## Commands

### Development
```bash
python src/main.py
```

### Build Executable
```bash
pyinstaller S-Flow.spec
```

### Install Dependencies
```bash
pip install -r requirements.txt
pip install -r requirements-test.txt
```

### Testing
```bash
# Run all tests
python -m pytest tests/test_core.py -v

# Run single test (replace test_name with actual function name)
python -m pytest tests/test_core.py -v -k test_name

# Run with coverage
python -m pytest tests/test_core.py --cov=src --cov-report=html
```

### Linting/Type Checking
No automated linting or type checking commands are currently configured. When adding code, follow the style guidelines below.

## Code Style Guidelines

### Imports
- Order: standard library → third-party → local imports
- Use absolute imports for local modules: `from core.config import load_settings`
- No blank lines between import groups

### Formatting
- 4-space indentation
- Max line length: ~100 characters (soft limit)
- Blank lines between methods and logical sections
- No trailing whitespace

### Types
- Use type hints for function parameters and return values
- Python 3.10+ union syntax: `str | None` (not `Optional[str]`)
- Class methods should include return types

### Naming Conventions
- **Classes**: PascalCase (`AudioRecorder`, `AppController`)
- **Functions/Methods**: snake_case (`start_recording`, `get_resource_path`)
- **Constants**: UPPER_SNAKE_CASE (`MAX_RETRIES`, `APP_VERSION`)
- **Private methods**: underscore prefix (`_save_from_queue`, `_call_api`)
- **Instance variables**: snake_case (`self.sample_rate`, `self.recording`)

### Error Handling
- Always use logger: `logger.error()`, `logger.warning()`, `logger.exception()`
- Catch specific exceptions when possible; use generic `Exception` as fallback
- Return user-friendly error strings from API methods (e.g., `"Error: Invalid API Key"`)
- Graceful degradation: return empty dict/list for config failures

### Logging
- Module-level logger at top of file: `logger = logging.getLogger(__name__)`
- Configure via `setup_logging()` from `core.config`
- Log to both file (`app.log`) and console

### PyQt6 Patterns
- Use signals/slots for communication: `self.hotkey_manager.triggered.connect(self.toggle_recording)`
- Worker threads extend `QThread` and emit results via signals
- Always use `tr("key")` for user-facing strings (i18n)
- Dialogs should call `super().__init__(parent)`

### Internationalization
- All user-facing text must use `tr("key")` from `core.locale_manager`
- Add translations to `assets/locales/ru.json` and `en.json`
- Fallback: returns key itself if translation not found

### File Organization
- `src/core/`: Core business logic (audio, API, config, hotkeys, i18n)
- `src/ui/`: PyQt6 UI components
- `tests/`: Unit tests (pytest)
- `assets/`: Resources (icon, locales, stylesheets)

### Configuration
- Settings stored in `settings.json` (application directory)
- Environment variables loaded from `.env` file (OPENAI_API_KEY)
- Use `get_resource_path()` for asset files (works in dev and PyInstaller)
- Use `get_app_dir()` for application root directory

### Testing
- Use pytest for testing
- Mock external dependencies: `@patch('core.audio_recorder.sd')`
- Test both happy path and error cases
- Test structure: Group related tests in classes (`class TestAudioRecorder:`)
- Test file paths: `tests/` directory, imports via `sys.path.insert(0, ...)`

### Threading
- Long-running operations use `QThread` (e.g., `ProcessingWorker`)
- Emit results via PyQt signals: `self.finished.emit(data)`
- Disconnect signals before reconnecting: `self.worker.finished.disconnect()`

### Windows-Specific
- Check `sys.frozen` for PyInstaller detection
- Use `sys._MEIPASS` for temp resource path in builds
- Windows registry operations for autostart (winreg)
- Mutex for single-instance protection

### Common Patterns
- **Singleton**: LocaleManager uses `__new__` pattern
- **Resource paths**: Always use `get_resource_path()` for files in assets/
- **API retry**: Use `_execute_with_retry()` for network operations
- **Signal disconnection**: Wrap in try/except for `TypeError` and `RuntimeError`
