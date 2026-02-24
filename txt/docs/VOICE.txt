# Voice

## 1. Статус

Голосовой контур находится в отдельной директории `voice_bot/` и не интегрирован в основной runtime `src/bot.py`.

## 2. Основной файл

- `voice_bot/voice_pipeline.py`

Pipeline:
1. STT (`faster-whisper`)
2. LLM (`ollama.chat`)
3. post-process текста (транслитерация/числительные/ударения)
4. TTS (`F5-TTS`)

## 3. Зависимости voice-контура

Требуются внешние пакеты и модели:
- `faster-whisper`
- `f5_tts`
- `ruaccent`
- `num2words`
- локальные чекпоинты F5-TTS

## 4. Тестовые скрипты

- `voice_bot/test_stt.py`
- `voice_bot/test_llm.py`
- `voice_bot/test_tts.py`

## 5. Запуск

```bash
python3 voice_bot/voice_pipeline.py
```

Перед запуском нужно подготовить окружение из `voice_bot/requirements.txt` и модели, указанные в `voice_bot/voice_pipeline.py`.
