# Media

## 1. Статус

В чат-боте есть единый media pipeline для вложений во входящем сообщении. Он поддерживает:
- изображения
- аудио / голосовые сообщения
- документы
- видео

По документам текущий статус такой:
- поддержка включена в основном runtime чата
- документы разбираются до вызова `SalesBot.process(...)`
- на вход в основной диалоговый pipeline уходит не бинарный файл, а текстовая выжимка
- свежий real E2E по документам уже прогоняли: `7/7 status=ok`, `6/7 media_used=true`
- главное runtime-ограничение на сегодня: `pdf` зависит от доступного extraction backend; в последнем real E2E один PDF был скипнут с причиной `pdf extraction backend is unavailable`

Важно: документный preprocessor работает отдельно от логики самого sales-бота. Это значит, что извлечение текста и summary может отработать нормально, но финальный ответ всё равно может уехать в общий sales-flow и KB Wipon.

## 2. Где это работает

Основные точки интеграции:
- `src/api.py`
- `src/media_preprocessor.py`
- `src/llm.py`

Фактический путь обработки документов:
1. API получает `message.attachments`.
2. В `src/api.py` вызывается `prepare_incoming_message(...)`.
3. `MediaPreprocessor` загружает attachment из `data_base64`, `url` или `text_content`.
4. Для документа выбирается extractor по `mime_type` и/или расширению файла.
5. Извлечённый текст режется по `MEDIA_MAX_DOCUMENT_CHARS`.
6. LLM делает краткую выжимку документа на русском языке.
7. В `prepared_message.text` добавляется блок вида `Дополнительный контекст из вложений клиента:`.
8. Уже этот текст уходит в `SalesBot.process(...)`.

То есть документы работают не как отдельный endpoint и не как отдельный режим бота. Они работают как предобработка входящего сообщения внутри обычного chat runtime.

## 3. Какой формат запроса ожидается

Во входящем API-сообщении для attachment можно передавать:
- `type`
- `mime_type`
- `file_name`
- `url`
- `data_base64`
- `text_content`
- `caption`

Минимальный пример:

```json
{
  "session_id": "sess-1",
  "user_id": "user-1",
  "message": {
    "text": "посмотрите документ",
    "attachments": [
      {
        "type": "document",
        "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "file_name": "request.docx",
        "data_base64": "..."
      }
    ]
  }
}
```

Attachment-only сценарий тоже допустим: пустой `message.text` разрешён, если вложение есть и оно поддерживается.

## 4. Какие форматы документов поддерживаются

Поддерживаемые форматы и текущий способ разбора:

| Формат | Распознаётся по | Как извлекается | Внешние зависимости |
| --- | --- | --- | --- |
| `txt`, `md`, `csv`, `json`, `xml`, `tsv`, `yaml`, `yml` | extension / `text/*` | прямое декодирование текста | нет |
| `html`, `htm` | extension / HTML MIME | удаление тегов, `script`, `style`, перевод в plain text | нет |
| `docx` | extension / OOXML Word MIME | чтение `word/document.xml` из zip-архива | нет |
| `xlsx`, `xlsm`, `xltx`, `xltm` | extension / OOXML Spreadsheet MIME | разбор workbook, shared strings и строк листов | нет |
| `xls` | extension / legacy Excel MIME | чтение через `xlrd` | `xlrd` |
| `pptx`, `pptm`, `ppsx`, `potx`, `potm` | extension / OOXML Presentation MIME | разбор slide XML и текста со слайдов | нет |
| `odt`, `ods`, `odp` | extension / ODF MIME | чтение `content.xml` | нет |
| `pdf` | extension / `application/pdf` | сначала `pypdf`, потом `PyPDF2`, потом `pdftotext` | `pypdf` или `PyPDF2`, либо системный `pdftotext` |
| `rtf` | extension / RTF MIME | встроенная очистка RTF control words | нет |
| `doc` | extension / `application/msword` | системный backend `antiword` или `catdoc` | `antiword` или `catdoc` |

Что реально делает preprocessor после извлечения текста:
- определяет, что вложение является `document`
- извлекает текст формата
- ограничивает объём текста
- просит LLM кратко ответить по шаблону: что это за документ, какие там ключевые данные, какой запрос/проблема клиента из него следует
- добавляет summary в prepared message

## 5. Что именно умеет document pipeline

На текущий момент pipeline умеет:
- принимать документ как `base64`, `url` или `text_content`
- определять тип документа по `type`, `mime_type` и/или расширению
- безопасно скачивать файл по `url`
- извлекать текст из офисных и текстовых форматов
- структурно разбирать таблицы и презентации
- суммаризировать документ на русском перед передачей в диалоговый pipeline
- работать с attachment-only сообщениями
- возвращать в API-метаданных, были ли вложения реально использованы или скипнуты

Что возвращает API по факту обработки:
- `media_used`
- `attachments_used`
- `attachments_skipped`

Это приходит в `response.meta` из `src/api.py`.

## 6. Ограничения и runtime-настройки

Ключевые env-переменные для документов:
- `MEDIA_MAX_ATTACHMENTS`, по умолчанию `6`
- `MEDIA_MAX_INLINE_BYTES`, по умолчанию `15728640` байт (`15 MiB`)
- `MEDIA_DOWNLOAD_TIMEOUT_SECONDS`, по умолчанию `20`
- `MEDIA_MAX_DOCUMENT_CHARS`, по умолчанию `12000`
- `MEDIA_MAX_SUMMARY_CHARS`, по умолчанию `2200`
- `MEDIA_MAX_TABLE_SHEETS`, по умолчанию `5`
- `MEDIA_MAX_TABLE_ROWS`, по умолчанию `200`
- `MEDIA_MAX_TABLE_COLS`, по умолчанию `20`
- `MEDIA_MAX_PRESENTATION_SLIDES`, по умолчанию `30`
- `MEDIA_MAX_DOWNLOAD_REDIRECTS`, по умолчанию `3`

Практический смысл:
- большие файлы режутся или отклоняются по размеру
- в таблицах обрабатывается ограниченное число листов, строк и колонок
- в презентациях обрабатывается ограниченное число слайдов
- в bot pipeline идёт summary, а не полный документ

Текущие runtime-зависимости по документам:
- для `pdf` нужен хотя бы один доступный backend: `pypdf`, `PyPDF2` или `pdftotext`
- для `doc` нужен `antiword` или `catdoc`
- для `xls` нужен `xlrd`

## 7. Безопасность загрузки по URL

Если документ приходит как `url`, загрузка идёт через защищённый downloader:
- разрешены только `http/https`
- URL с credentials запрещены
- hostname должен резолвиться
- non-public IP блокируются
- редиректы валидируются вручную
- размер ограничен `MEDIA_MAX_INLINE_BYTES`
- скачивание идёт потоково

Это сделано, чтобы не открывать SSRF и не тянуть большие или внутренние файлы.

## 8. Как это тестировали

### 8.1. Unit и regression

Покрытие по документам есть в `tests/test_media_preprocessor.py`. Там отдельно проверено:
- `docx`: текст действительно извлекается до summary
- `xlsx`: текст листов и строк попадает в LLM prompt
- `doc`: legacy extraction через `antiword` backend
- `pptx`: текст со слайдов извлекается до summary
- `html`: теги и `script`/`style` вычищаются
- URL на non-public адрес блокируется
- attachment-only запросы через API принимаются и корректно проставляют `media_used`

Это значит, что document path не только описан в коде, но и закрыт unit/regression тестами на ключевых форматах и edge cases.

### 8.2. Real E2E по документам

Свежий отчёт:
- `results/docs_real_e2e_20260311_120728.json`
- `results/docs_real_e2e_20260311_120728.md`

Что было в этом прогоне:
- `MEDIA_MAX_INLINE_BYTES=20971520`
- 7 сценариев на реальных документах
- health-check'и `ollama`, `tei_embed`, `tei_rerank` были зелёные

Какие форматы реально гоняли:
- `docx`
- `pdf`
- `txt`
- `csv`
- `doc`
- `pptx`

Результат по сценариям:
- `D01` `docx`: document summary сработал, attachment использован
- `D02` `pdf`: attachment был скипнут, причина `pdf extraction backend is unavailable`
- `D03` `pdf`: OCR/PDF summary сработал, attachment использован
- `D04` `txt`: summary сработал
- `D05` `csv`: summary сработал
- `D06` `doc`: summary сработал
- `D07` `pptx`: summary сработал

Сводка по real E2E:
- `7/7 status=ok`
- `6/7 media_used=true`
- средний `preprocess`: `35.6s`
- средний `pipeline`: `102.96s`

Что важно понимать по качеству:
- preprocessor по документам в этом прогоне в целом отработал хорошо
- проблемы были не только в extraction, но и downstream: основной sales-flow иногда игнорировал смысл summary и отвечал как обычный Wipon sales-бот
- особенно это видно на `D04`, `D05`, `D06`, `D07`, где summary был собран, но финальный ответ частично или полностью ушёл в общую KB

Итог по документам после реального прогона: извлечение и summary уже работают в runtime, но grounded final response для document-heavy кейсов ещё не гарантирован.

## 9. Что сейчас подтверждено, а что нет

Подтверждено:
- document attachments реально проходят через основной chat runtime
- `docx`, `txt`, `csv`, `doc`, `pptx` и как минимум часть `pdf` сценариев реально работают
- API корректно отдаёт метаданные использования вложений
- unit/regression покрывают ключевые форматы и защитные ограничения

Не гарантировано в любом окружении:
- `pdf`, если не установлен ни один extraction backend
- `doc`, если в окружении нет `antiword`/`catdoc`
- идеальная привязка финального ответа к смыслу документа, потому что после summary управление снова переходит в общий sales dialogue pipeline

## 10. Короткий итог

Документы в чате уже работают как полноценная часть media pipeline:
- файл принимается API
- превращается в текст
- суммаризируется
- встраивается в `prepared_message`
- и только потом идёт в обычный `SalesBot`

На сегодня по документам можно честно утверждать:
- кодовый путь есть
- unit/regression есть
- real E2E есть
- office и text форматы реально проверялись
- слабое место сейчас не столько само извлечение, сколько качество финального ответа после передачи document summary в основной sales-flow
