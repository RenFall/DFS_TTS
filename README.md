# DFS TTS - Система автоматической транскрипции аудиофайлов

## Описание
DFS TTS - скрипт для автоматической транскрипции аудиофайлов с удаленного сервера. Система использует алгоритм поиска в глубину (DFS) для сканирования директорий, загружает аудиофайлы и обрабатывает их через сервис распознавания речи на базе Whisper.

## Возможности
- Автоматический поиск аудиофайлов (.wav, .mp3) в удаленных директориях
- Транскрипция аудио в текст с использованием модели Whisper large-v3
- Сохранение результатов в базу данных MySQL
- Предотвращение повторной обработки уже обработанных файлов
- Диаризация (разделение голосов разных говорящих)
- Обработка на GPU и CPU (CUDA)

## Требования

### Python пакеты
```
paramiko
sqlalchemy
pymysql
gradio-client
```

### Системные требования
- Python 3.7+
- MySQL сервер
- Доступ к серверу распознавания речи с Whisper
- SSH доступ к серверу с аудиофайлами

## Установка
```bash
pip install paramiko sqlalchemy pymysql gradio-client
```

## Конфигурация

Создайте файл `.env` или настройте переменные окружения:

```bash
# База данных
DB_HOST=your_mysql_host
DB_PORT=your_mysql_port
DB_USER=your_mysql_user
DB_PASSWORD=your_mysql_password
DB_NAME=your_database_name

# SSH сервер с аудиофайлами
SSH_HOST=your_ssh_host
SSH_USER=your_ssh_user
SSH_PASSWORD=your_ssh_password
SSH_REMOTE_PATH=/path/to/audio/files

# Сервер распознавания речи
WHISPER_API_URL=http://your_whisper_server:port/

# HuggingFace токен для диаризации
HF_TOKEN=your_huggingface_token

# Локальная временная директория
LOCAL_TEMP_DIR=./TEMP
```

## Использование

1. Убедитесь, что все сервисы доступны (MySQL, Whisper API, SSH сервер)

2. Запустите скрипт:
```bash
python DFS_TTS.py
```

Система автоматически:
- Подключится к удаленному серверу
- Найдет новые аудиофайлы
- Загрузит и обработает их
- Сохранит результаты в базу данных

## Структура базы данных

Таблица `transcriptions`:
- `id` - primary key
- `date_transcription` - дата и время обработки
- `file_name` - название аудиофайла
- `transcription_text` - результат транскрипции в JSON формате
- `flag` - флаг успешной обработки

## Параметры распознавания
- Модель: large-v3
- Язык: русский
- Beam size: 6
- Диаризация включена
- VAD фильтрация включена
- Температура: 0 


