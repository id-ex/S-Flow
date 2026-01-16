# Тесты S-Flow

Эта директория содержит модульные тесты для основных компонентов приложения.

## Запуск тестов

### Установка зависимостей

```bash
pip install -r requirements-test.txt
```

### Запуск всех тестов

```bash
python -m pytest tests/test_core.py -v
```

### Запуск с покрытием кода

```bash
python -m pytest tests/test_core.py --cov=src --cov-report=html
```

После этого откройте `htmlcov/index.html` в браузере для просмотра подробного отчета.

## Покрытие тестами

В текущем наборе тестов покрываются:

- **Config** (4 теста): загрузка настроек, конфигурация моделей
- **LocaleManager** (3 теста): singleton паттерн, функция перевода
- **AudioRecorder** (5 тестов): инициализация, запуск/остановка записи
- **TextProcessor** (1 тест): вставка текста
- **ApiClient** (4 теста): инициализация, retry логика, обработка ошибок

## Добавление новых тестов

При добавлении новой функциональности не забывайте писать тесты!

Пример теста:

```python
def test_my_new_feature(self):
    """Test description"""
    from core.module import Class

    obj = Class()
    result = obj.method()
    assert result == "expected"
```

## CI/CD

Эти тесты могут быть интегрированы в CI/CD пайплайн для автоматического запуска при каждой коммите.
