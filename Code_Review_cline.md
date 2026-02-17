# Аудит кода десктопного приложения S-Flow

**Дата:** 17.02.2026  
**Аудитор:** Cline (Senior Python Desktop Developer)  
**Версия приложения:** 1.9.8

---

## 🔴 Thread Safety: Анализ блокировок UI

### Критические проблемы:

#### 1. **Сигналы из не-Qt потока** (`hotkey_manager.py:31-33`)
```python
def on_trigger(self) -> None:
    self.triggered.emit()  # Вызов из потока keyboard library!
```
Библиотека `keyboard` вызывает callback в своём внутреннем потоке. Сигнал `emit()` из не-Qt потока может привести к race condition. 

**Решение:** Использовать `Qt.QueuedConnection` при подключении:
```python
self.hotkey_manager.triggered.connect(
    self.toggle_standard_recording, 
    Qt.ConnectionType.QueuedConnection
)
```

#### 2. **Сигналы из daemon thread** (`update_manager.py:47-51`)
```python
def check_for_updates(self, manual: bool = False):
    def _check():
        # ... 
        self.update_available.emit(...)  # Из threading.Thread!
```
Сигналы из `threading.Thread` (не QThread) требуют явной очередизации.

#### 3. **Race condition в AudioRecorder** (`audio_recorder.py:38-42`)
```python
if self.recording:
    return
self.recording = True  # Не атомарно!
```
Между проверкой и установкой флага другой поток может вмешаться.

**Решение:** Использовать `threading.Lock`:
```python
def __init__(self):
    self._lock = threading.Lock()
    
def start_recording(self):
    with self._lock:
        if self.recording:
            return
        self.recording = True
```

#### 4. **Блокирующий sleep в UI контексте** (`text_process.py:31`)
```python
time.sleep(0.2)  # В основном потоке!
keyboard.send("ctrl+v")
```
Вызывается из `on_processing_finished` (слот в GUI потоке). Блокирует UI на 200ms.

**Решение:** Вынести в отдельный поток или использовать QTimer.

---

## 🟡 Code Style: Соответствие PEP 8 и Qt конвенциям

### Нарушения:

| Файл | Строка | Проблема |
|------|--------|----------|
| `main.py` | 35 | `audio_buffer: any` → должно быть `io.BytesIO` |
| `main.py` | 285-295 | Дублирование кода после `finally` блока (недостижимый код) |
| `api_client.py` | 19 | `Callable[[str], None]` — лишние пробелы внутри скобок |
| `config.py` | 21 | `sys._MEIPASS` без проверки атрибута |

### Положительные аспекты:
- ✅ Сигналы названы в past tense (`triggered`, `finished`)
- ✅ Классы наследуют `QObject` корректно
- ✅ Логирование используется консистентно

---

## 🟠 Robustness: Устойчивость к падениям

### Проблемы:

#### 1. **Нет обработки недоступности микрофона** (`audio_recorder.py:48-55`)
```python
try:
    self.stream = sd.InputStream(...)
    self.stream.start()
except Exception as e:
    logger.error(...)
    self.recording = False  # Пользователь не уведомляется!
```

#### 2. **Незащищённый disconnect** (`main.py:223-228`)
```python
try:
    self.worker.finished.disconnect(self.on_processing_finished)
except (TypeError, RuntimeError) as e:
    logger.debug(...)  # Игнорируется, но лучше проверить isSignalConnected()
```

#### 3. **Потеря данных при ошибке** (`api_client.py:95-98`)
При ошибке Groq переключается на OpenAI, но уведомление приходит через callback, который может быть не готов к частичным данным.

#### 4. **Windows-only код без fallback** 
- `os.startfile()` в `settings_dialog.py:147`
- `winreg` в `config.py:143`
- `ctypes.windll` в `main.py:272`

---

## 🔵 Архитектура интерфейса

### Проблемы разделения ответственности:

#### 1. **God Object: AppController** (`main.py:68-268`)
Класс отвечает за:
- UI (overlay, tray menu)
- Hotkeys (3 менеджера)
- API client
- Audio recording
- Updates
- Statistics
- Settings persistence

**Рекомендация:** Разделить на:
- `TrayController` — управление треем
- `RecordingController` — логика записи
- `UpdateController` — обновления

#### 2. **Неиспользуемый HotkeyController**
Существует `hotkey_controller.py` с готовой архитектурой, но в `main.py` используется прямое управление тремя `HotkeyManager`.

#### 3. **Смешивание UI и логики**
```python
# В AppController (main.py:191-192)
dialog = SettingsDialog(None, ...)
result = dialog.exec()
```
Контроллер напрямую создаёт и управляет диалогами.

---

## 🟢 Управление ресурсами

### Положительные аспекты:
- ✅ `get_resource_path()` корректно работает с `sys._MEIPASS`
- ✅ QSS стили вынесены в отдельный файл
- ✅ Локализация через JSON файлы

### Проблемы:

#### 1. **Утечка QTimer** (`overlay.py:30-33`)
```python
self.anim_timer = QTimer(self)  # Создаётся новый при каждом show_message!
```
При многократном вызове старый таймер не удаляется корректно.

**Решение:**
```python
def show_message(self, text, duration=None, animate=False):
    if not hasattr(self, 'anim_timer'):
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self.update_animation)
    self.anim_timer.stop()  # Остановить предыдущий
```

#### 2. **Memory leak в worker** (`main.py:223`)
```python
self.worker.finished.disconnect(self.on_processing_finished)
```
Worker объект остаётся в памяти. Нужно:
```python
self.worker.finished.connect(self.on_processing_finished)
self.worker.finished.connect(self.worker.deleteLater)  # Добавить!
```

---

## 🟣 Готовность к пакетной сборке (PyInstaller/Nuitka)

### ✅ Корректно реализовано:
```python
# config.py
def get_resource_path(relative_path):
    if getattr(sys, "frozen", False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(...)
    return os.path.join(base_path, relative_path)
```

### ⚠️ Требует внимания:

#### 1. **Динамические импорты** (`locale_manager.py:47`)
```python
from .config import get_resource_path  # Внутри метода!
```
PyInstaller может не обнаружить этот импорт при статическом анализе.

#### 2. **Отсутствие spec-файла или хуков**
Нет явной конфигурации для PyInstaller с `--add-data "assets;assets"`.

---

## 📝 Refactored Fragment: Оптимизация работы с потоками

### До (main.py):
```python
class ProcessingWorker(QThread):
    finished = pyqtSignal(str, str, dict)
    
    def run(self):
        try:
            # ... heavy processing
            self.finished.emit(raw_text, corrected_text, usage_stats)
        except Exception as e:
            self.finished.emit("", tr("error_unknown"), {})
```

### После:
```python
from PyQt6.QtCore import QThread, pyqtSignal, pyqtSlot

class ProcessingWorker(QThread):
    """Thread-safe worker for audio processing with proper cleanup."""
    
    finished = pyqtSignal(str, str, dict)
    error = pyqtSignal(str)
    
    def __init__(self, api_client, audio_buffer, **kwargs):
        super().__init__()
        self.api_client = api_client
        self.audio_buffer = audio_buffer
        self._is_cancelled = False
        
    @pyqtSlot()
    def run(self):
        try:
            if self._is_cancelled:
                return
                
            raw_text, duration, provider = self.api_client.transcribe(self.audio_buffer)
            
            if self._is_cancelled:
                return
                
            # ... processing
            self.finished.emit(raw_text, corrected_text, usage_stats)
            
        except Exception as e:
            logger.exception("Worker error")
            self.error.emit(str(e))
        finally:
            self.audio_buffer.close()
            
    def cancel(self):
        """Thread-safe cancellation flag."""
        self._is_cancelled = True


# В AppController:
def process_audio(self, audio_path):
    self.worker = ProcessingWorker(self.api_client, audio_path, ...)
    self.worker.finished.connect(self.on_processing_finished)
    self.worker.finished.connect(self.worker.deleteLater)  # Важно!
    self.worker.error.connect(self.on_processing_error)
    self.worker.start()
```

---

## 📊 Итоговая оценка

| Критерий | Оценка | Комментарий |
|----------|--------|-------------|
| Thread Safety | ⚠️ 6/10 | Сигналы из не-Qt потоков, race conditions |
| Code Style | ✅ 8/10 | Мелкие нарушения PEP 8 |
| Robustness | ⚠️ 6/10 | Нет обработки ошибок устройств |
| Архитектура | ⚠️ 5/10 | God Object, неиспользуемый код |
| Ресурсы | ✅ 7/10 | QTimer утечки, в целом корректно |
| PyInstaller | ✅ 8/10 | Готов, нужны минорные правки |

---

## 🎯 Приоритетные исправления

### Критические (исправить немедленно):
1. 🔴 Добавить `Qt.QueuedConnection` для сигналов hotkey
2. 🔴 Добавить `threading.Lock` в `AudioRecorder`

### Важные (исправить в ближайшем спринте):
3. 🟠 Разбить `AppController` на контроллеры
4. 🟠 Добавить обработку недоступности микрофона
5. 🟠 Исправить утечку памяти в worker

### Рекомендации (улучшения):
6. 🟡 Удалить дублирующийся код в `main()`
7. 🟡 Добавить `deleteLater()` для worker объектов
8. 🟡 Создать PyInstaller spec-файл

---

## 📁 Файлы, требующие изменений

| Файл | Приоритет | Изменения |
|------|-----------|-----------|
| `src/main.py` | 🔴 Высокий | QueuedConnection, deleteLater, удаление дублей |
| `src/core/hotkey_manager.py` | 🔴 Высокий | Документирование thread-safety |
| `src/core/audio_recorder.py` | 🔴 Высокий | Добавить Lock |
| `src/ui/overlay.py` | 🟠 Средний | Исправить QTimer утечку |
| `src/core/text_process.py` | 🟠 Средний | Убрать blocking sleep |
| `src/core/update_manager.py` | 🟡 Низкий | Использовать QThread вместо threading |

---

*Отчёт сгенерирован автоматически.*