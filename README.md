# S-Flow

## English

**S-Flow** is a Windows desktop application built with Python and PyQt6 that provides seamless speech-to-text processing with AI-powered text correction and translation. The application runs as a system tray service and uses global hotkeys to record, transcribe, and process speech input using OpenAI's Whisper and GPT models.

### Key Features
*   **Smart Dictation**: Records speech, transcribes it, and automatically corrects grammar and style using AI.
*   **Translation Mode**: Records speech and translates it between English and Russian (or other configured languages).
*   **Global Hotkeys**: Control recording from anywhere in the system:
    *   `Ctrl+Alt+S`: Record and Process (Standard Mode)
    *   `Ctrl+Alt+T`: Record and Translate
    *   `Ctrl+Alt+X`: Cancel Recording
*   **Context Awareness**: Maintains conversation history for better context understanding and correction.
*   **Auto-Paste**: Automatically types the processed text into the active text field.
*   **System Tray Integration**: Runs unobtrusively in the background.

### Installation & Usage
You can download the latest version from the **[Releases](../../releases)** page.
*   **No installation required**: Simply extract the downloaded folder to a desired location.
*   Run `S-Flow.exe` to start the application.

---

## Русский

**S-Flow** — это настольное приложение для Windows, созданное на Python и PyQt6, которое обеспечивает качественное преобразование речи в текст с коррекцией и переводом на базе искусственного интеллекта. Приложение работает в системном трее и использует глобальные горячие клавиши для записи, транскрипции и обработки речи с использованием моделей OpenAI Whisper и GPT.

### Основные возможности
*   **Умная диктовка**: Записывает речь, транскрибирует её и автоматически исправляет грамматику и стиль с помощью ИИ.
*   **Режим перевода**: Записывает речь и переводит её (например, с русского на английский и наоборот).
*   **Глобальные горячие клавиши**: Управление записью из любой точки системы:
    *   `Ctrl+Alt+S`: Записать и обработать (Стандартный режим)
    *   `Ctrl+Alt+T`: Записать и перевести
    *   `Ctrl+Alt+X`: Отменить запись
*   **Учет контекста**: Сохраняет историю разговора для лучшего понимания контекста и коррекции.
*   **Авто-вставка**: Автоматически вставляет обработанный текст в активное текстовое поле.
*   **Работа в фоне**: Сворачивается в системный трей и не мешает работе.

### Установка и использование
Последнюю версию можно скачать на странице **[Releases](../../releases)**.
*   **Установка не требуется**: Просто распакуйте скачанный архив в любое удобное место.
*   Запустите `S-Flow.exe` для начала работы.
