# Voice Bot — Голосовой интерфейс

## Обзор

Voice Bot предоставляет голосовой интерфейс для CRM Sales Bot. Клиент говорит голосом, бот отвечает голосом.

**Архитектура:**
```
┌───────────────────┐     ┌───────────────────┐     ┌───────────────────┐
│   faster-whisper  │ ──► │    SalesBot       │ ──► │   F5-TTS Russian  │
│   (STT)           │     │   (text mode)     │     │   + RUAccent      │
└───────────────────┘     └───────────────────┘     └───────────────────┘
      Голос клиента              Обработка               Голос бота
```

## Структура

```
voice_bot/
├── voice_pipeline.py       # Полный pipeline: STT → LLM → TTS
├── test_stt.py             # Тесты Speech-to-Text
├── test_tts.py             # Тесты Text-to-Speech
├── test_llm.py             # Тесты LLM интеграции
├── seed_search.py          # Поиск семян для обучения
├── run.sh                  # Скрипт запуска
│
├── CosyVoice/              # Синтез речи (submodule)
├── fish-speech/            # Speech synthesis (submodule)
├── checkpoints/            # Модели F5-TTS, OpenAudio
├── models/                 # XTTS-RU-IPA модели
├── audio/                  # Примеры аудио
└── ruslan_corpus/          # Корпус для обучения TTS
```

## Компоненты

### STT (Speech-to-Text)

**Модель:** faster-whisper (GPU)

```python
from faster_whisper import WhisperModel

# Инициализация
model = WhisperModel("large-v3", device="cuda", compute_type="float16")

# Распознавание
segments, info = model.transcribe("audio.wav", language="ru")
text = "".join([segment.text for segment in segments])
```

**Особенности:**
- GPU ускорение через CUDA
- Поддержка русского языка
- Автоматическое определение языка
- Модели: tiny, base, small, medium, large-v3

### LLM (Language Model)

**Модель:** vLLM + Qwen3-4B-AWQ

Используется тот же SalesBot что и в текстовом режиме:

```python
from bot import SalesBot
from llm import VLLMClient

llm = VLLMClient()
bot = SalesBot(llm)

# Обработка текста
result = bot.process(recognized_text)
response_text = result["response"]
```

### TTS (Text-to-Speech)

**Модель:** F5-TTS Russian + RUAccent

```python
from f5_tts import F5TTS
from ruaccent import RUAccent

# Расстановка ударений
accentizer = RUAccent()
text_with_accents = accentizer.process_all("Привет, как дела?")
# → "Приве+т, как дела+?"

# Синтез речи
tts = F5TTS(model_path="checkpoints/f5-tts-ru")
audio = tts.synthesize(text_with_accents, speaker="ruslan")

# Сохранение
import soundfile as sf
sf.write("response.wav", audio, samplerate=24000)
```

**Особенности:**
- Натуральное звучание на русском
- Автоматическая расстановка ударений (RUAccent)
- Поддержка разных голосов
- Преобразование чисел в слова (num2words)

## Полный Pipeline

### voice_pipeline.py

```python
class VoicePipeline:
    def __init__(self):
        # STT
        self.whisper = WhisperModel("large-v3", device="cuda")

        # LLM (vLLM + Qwen3-4B-AWQ)
        self.llm = VLLMClient()
        self.bot = SalesBot(self.llm)

        # TTS
        self.tts = F5TTS()
        self.accentizer = RUAccent()

    def process_audio(self, audio_path: str) -> str:
        """Обработка аудио файла, возврат пути к ответу"""

        # 1. STT: Аудио → Текст
        segments, _ = self.whisper.transcribe(audio_path, language="ru")
        user_text = "".join([s.text for s in segments])

        # 2. LLM: Обработка текста
        result = self.bot.process(user_text)
        response_text = result["response"]

        # 3. TTS: Текст → Аудио
        text_with_accents = self.accentizer.process_all(response_text)
        audio = self.tts.synthesize(text_with_accents)

        # Сохранение
        output_path = "response.wav"
        sf.write(output_path, audio, 24000)

        return output_path

    def process_stream(self, audio_stream):
        """Обработка аудио потока в реальном времени"""
        # ... реализация streaming
```

### Использование

```python
from voice_pipeline import VoicePipeline

pipeline = VoicePipeline()

# Обработка файла
response_audio = pipeline.process_audio("client_message.wav")

# Воспроизведение
import sounddevice as sd
import soundfile as sf

data, samplerate = sf.read(response_audio)
sd.play(data, samplerate)
sd.wait()
```

## Установка

### Зависимости

```bash
# Основные
pip install faster-whisper
pip install f5-tts
pip install ruaccent
pip install sounddevice soundfile
pip install num2words
pip install torch  # с CUDA

# Дополнительные
pip install numpy
pip install scipy
```

### requirements.txt

```
# voice_bot/requirements.txt
faster-whisper>=0.10.0
f5-tts>=0.1.0
ruaccent>=0.3.0
sounddevice>=0.4.6
soundfile>=0.12.1
num2words>=0.5.12
torch>=2.0.0
numpy>=1.24.0
scipy>=1.10.0
```

### Модели

```bash
# Whisper (автоматически при первом запуске)
# Модели: tiny, base, small, medium, large-v3

# F5-TTS (скачать вручную)
cd voice_bot/checkpoints
wget https://example.com/f5-tts-ru.zip
unzip f5-tts-ru.zip
```

## Конфигурация

### Параметры STT

```python
# voice_pipeline.py
STT_CONFIG = {
    "model_size": "large-v3",  # tiny, base, small, medium, large-v3
    "device": "cuda",          # cuda, cpu
    "compute_type": "float16", # float16, float32, int8
    "language": "ru",          # ru, en, auto
    "beam_size": 5,
    "vad_filter": True,        # Voice Activity Detection
}
```

### Параметры TTS

```python
# voice_pipeline.py
TTS_CONFIG = {
    "model_path": "checkpoints/f5-tts-ru",
    "speaker": "ruslan",       # голос
    "sample_rate": 24000,
    "speed": 1.0,              # скорость (0.5-2.0)
}
```

### Параметры аудио

```python
AUDIO_CONFIG = {
    "sample_rate": 16000,      # для STT
    "channels": 1,             # моно
    "format": "wav",
}
```

## Запуск

### Интерактивный режим

```bash
cd voice_bot
./run.sh
```

```python
# Или напрямую
python voice_pipeline.py

# Interactive voice bot
# Press ENTER to start recording, ENTER again to stop
# Say 'quit' to exit
```

### Batch обработка

```python
from voice_pipeline import VoicePipeline

pipeline = VoicePipeline()

# Обработка нескольких файлов
audio_files = ["msg1.wav", "msg2.wav", "msg3.wav"]
for audio in audio_files:
    response = pipeline.process_audio(audio)
    print(f"{audio} → {response}")
```

## Тестирование

```bash
# Тест STT
python test_stt.py audio/test_sample.wav

# Тест TTS
python test_tts.py "Привет, это тестовое сообщение"

# Тест LLM интеграции
python test_llm.py

# Полный тест pipeline
python voice_pipeline.py --test
```

## Производительность

| Компонент | Время | GPU |
|-----------|-------|-----|
| STT (10s audio) | ~1s | RTX 3080 |
| LLM (response) | ~0.1-0.2s | vLLM |
| TTS (100 chars) | ~0.5s | RTX 3080 |
| **Итого** | **~1.5-2s** | |

### Оптимизация

```python
# Кэширование моделей
pipeline = VoicePipeline(preload=True)  # Загрузка моделей при старте

# Streaming TTS
pipeline.enable_streaming()  # Начинает говорить до окончания генерации

# Batch processing
pipeline.process_batch(audio_files, parallel=True)
```

## Голоса

### Доступные голоса

| Голос | Описание |
|-------|----------|
| `ruslan` | Мужской, нейтральный |
| `natasha` | Женский, нейтральный |
| `custom` | Обучение на своих данных |

### Добавление голоса

```python
# Подготовка корпуса
# ruslan_corpus/
# ├── audio/
# │   ├── 001.wav
# │   ├── 002.wav
# │   └── ...
# └── transcripts.txt

# Обучение
python seed_search.py --corpus ruslan_corpus --output checkpoints/custom
```

## Интеграция с ботом

### Расширение SalesBot

```python
class VoiceSalesBot(SalesBot):
    def __init__(self, llm):
        super().__init__(llm)
        self.pipeline = VoicePipeline()

    def process_voice(self, audio_path: str) -> str:
        """Обработка голосового сообщения"""
        return self.pipeline.process_audio(audio_path)

    def speak(self, text: str) -> str:
        """Озвучивание текста"""
        return self.pipeline.synthesize(text)
```

### WebSocket интеграция

```python
import websockets

async def voice_handler(websocket):
    bot = VoiceSalesBot()

    async for audio_chunk in websocket:
        # Получение аудио
        audio_path = save_audio(audio_chunk)

        # Обработка
        response_audio = bot.process_voice(audio_path)

        # Отправка ответа
        await websocket.send(load_audio(response_audio))
```

## Ограничения

- **GPU необходим** для приемлемой производительности
- **Русский язык** — основной, английский хуже
- **Качество микрофона** влияет на STT
- **Шум** может ухудшить распознавание
- **Интонация** бота пока не адаптивна

## Troubleshooting

### STT не распознаёт

```python
# Проверить качество аудио
import soundfile as sf
data, sr = sf.read("audio.wav")
print(f"Sample rate: {sr}, Duration: {len(data)/sr}s")

# Использовать VAD
segments, _ = model.transcribe("audio.wav", vad_filter=True)
```

### TTS звучит неестественно

```python
# Проверить ударения
text = "Привет"
accented = accentizer.process_all(text)
print(accented)  # Должно быть "Приве+т"

# Настроить скорость
audio = tts.synthesize(text, speed=0.9)
```

### Медленная обработка

```python
# Использовать меньшую модель
model = WhisperModel("small", device="cuda")

# Включить int8
model = WhisperModel("large-v3", compute_type="int8")
```
