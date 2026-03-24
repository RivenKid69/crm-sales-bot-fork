import base64
import io
import json
import sys
import types
import zipfile

import pytest

from src.media_preprocessor import PreparedMessage, prepare_incoming_message
from src.media_turn_context import MediaTurnContext


class _FakeLLM:
    def __init__(self, generate_response=None, multimodal_response=None):
        self.last_generate_prompt = None
        self.last_multimodal_prompt = None
        self.generate_response = generate_response
        self.multimodal_response = multimodal_response

    def generate(self, prompt, **kwargs):
        self.last_generate_prompt = prompt
        purpose = kwargs.get("purpose")
        source_text = self.generate_response or self.multimodal_response or ""
        if purpose == "media_sparse_extraction":
            extracted = {}
            lower_text = f"{source_text}\n{prompt}".lower()
            if "альфа логистик" in lower_text:
                extracted["company_name"] = "Альфа Логистик"
            if "алексей петрович" in lower_text:
                extracted["contact_name"] = "Алексей Петрович"
                extracted["client_name"] = "Алексей Петрович"
            if "алматы" in lower_text:
                extracted["city"] = "Алматы"
            if "логистик" in lower_text or "доставк" in lower_text:
                extracted["business_type"] = "логистика"
            return json.dumps(extracted, ensure_ascii=False)
        return self.generate_response or "В документе реквизиты клиента и просьба выставить счет."

    def generate_multimodal(self, prompt, **kwargs):
        self.last_multimodal_prompt = prompt
        return self.multimodal_response or "На изображении чек, видны реквизиты и сумма оплаты."


def _tiny_png_base64() -> str:
    return (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
        "/w8AAgMBgL9nXc8AAAAASUVORK5CYII="
    )


def _docx_base64(text: str) -> str:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "word/document.xml",
            (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body><w:p><w:r><w:t>"
                f"{text}"
                "</w:t></w:r></w:p></w:body></w:document>"
            ),
        )
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _xlsx_base64(rows: list[list[str]], *, sheet_name: str = "Продажи") -> str:
    shared_strings: list[str] = []
    shared_index: dict[str, int] = {}
    row_xml: list[str] = []

    for row_number, row in enumerate(rows, start=1):
        cell_xml: list[str] = []
        for col_number, value in enumerate(row, start=1):
            if value not in shared_index:
                shared_index[value] = len(shared_strings)
                shared_strings.append(value)
            column_letter = chr(ord("A") + col_number - 1)
            cell_xml.append(
                f'<c r="{column_letter}{row_number}" t="s"><v>{shared_index[value]}</v></c>'
            )
        row_xml.append(f'<row r="{row_number}">{"".join(cell_xml)}</row>')

    shared_strings_xml = "".join(f"<si><t>{value}</t></si>" for value in shared_strings)
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<sheets>"
        f'<sheet name="{sheet_name}" sheetId="1" r:id="rId1"/>'
        "</sheets>"
        "</workbook>"
    )
    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(row_xml)}</sheetData>"
        "</worksheet>"
    )
    shared_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        f'count="{len(shared_strings)}" uniqueCount="{len(shared_strings)}">'
        f"{shared_strings_xml}"
        "</sst>"
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        archive.writestr("xl/sharedStrings.xml", shared_xml)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _pptx_base64(slides: list[str]) -> str:
    slide_rels = []
    slide_ids = []
    slide_xml_files = {}

    for idx, slide_text in enumerate(slides, start=1):
        rel_id = f"rId{idx}"
        slide_ids.append(
            f'<p:sldId id="{255 + idx}" r:id="{rel_id}"/>'
        )
        slide_rels.append(
            f'<Relationship Id="{rel_id}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" '
            f'Target="slides/slide{idx}.xml"/>'
        )
        slide_xml_files[f"ppt/slides/slide{idx}.xml"] = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
            "<p:cSld><p:spTree><p:sp><p:txBody>"
            f"<a:p><a:r><a:t>{slide_text}</a:t></a:r></a:p>"
            "</p:txBody></p:sp></p:spTree></p:cSld>"
            "</p:sld>"
        )

    presentation_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        f"<p:sldIdLst>{''.join(slide_ids)}</p:sldIdLst>"
        "</p:presentation>"
    )
    presentation_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{''.join(slide_rels)}"
        "</Relationships>"
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("ppt/presentation.xml", presentation_xml)
        archive.writestr("ppt/_rels/presentation.xml.rels", presentation_rels_xml)
        for path, payload in slide_xml_files.items():
            archive.writestr(path, payload)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _audio_base64() -> str:
    return base64.b64encode(b"fake-audio-payload").decode("ascii")


def _import_api_module_with_fastapi_stub(monkeypatch):
    fastapi_mod = types.ModuleType("fastapi")
    fastapi_concurrency = types.ModuleType("fastapi.concurrency")
    fastapi_exceptions = types.ModuleType("fastapi.exceptions")
    fastapi_responses = types.ModuleType("fastapi.responses")

    class _FakeFastAPI:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def exception_handler(self, *_args, **_kwargs):
            def decorator(fn):
                return fn

            return decorator

        def get(self, *_args, **_kwargs):
            def decorator(fn):
                return fn

            return decorator

        def post(self, *_args, **_kwargs):
            def decorator(fn):
                return fn

            return decorator

    class _FakeJSONResponse:
        def __init__(self, status_code=200, content=None):
            self.status_code = status_code
            self.content = content

    class _FakeRequestValidationError(Exception):
        def errors(self):
            return []

    fastapi_mod.Depends = lambda value=None: value
    fastapi_mod.FastAPI = _FakeFastAPI
    fastapi_mod.Header = lambda default=None: default
    fastapi_mod.Request = object
    fastapi_concurrency.run_in_threadpool = lambda func, *args, **kwargs: func(*args, **kwargs)
    fastapi_exceptions.RequestValidationError = _FakeRequestValidationError
    fastapi_responses.JSONResponse = _FakeJSONResponse

    monkeypatch.setitem(sys.modules, "fastapi", fastapi_mod)
    monkeypatch.setitem(sys.modules, "fastapi.concurrency", fastapi_concurrency)
    monkeypatch.setitem(sys.modules, "fastapi.exceptions", fastapi_exceptions)
    monkeypatch.setitem(sys.modules, "fastapi.responses", fastapi_responses)
    sys.modules.pop("src.api", None)

    import src.api as api_mod

    return api_mod


def test_prepare_incoming_message_summarizes_text_document():
    llm = _FakeLLM()

    prepared = prepare_incoming_message(
        user_text="Проверьте, пожалуйста",
        attachments=[
            {
                "type": "document",
                "file_name": "invoice.txt",
                "text_content": "Счет на оплату №77\nСумма: 190 000 тг",
            }
        ],
        llm=llm,
    )

    assert prepared.media_used is True
    assert "Проверьте, пожалуйста" in prepared.text
    assert "Тип: документ" in prepared.text
    assert "invoice.txt" in prepared.text
    assert prepared.used_attachments[0]["type"] == "document"
    assert "Счет на оплату" in llm.last_generate_prompt


def test_prepare_incoming_message_uses_multimodal_llm_for_image():
    llm = _FakeLLM()

    prepared = prepare_incoming_message(
        user_text="Что на фото?",
        attachments=[
            {
                "type": "image",
                "file_name": "check.png",
                "mime_type": "image/png",
                "data_base64": _tiny_png_base64(),
                "caption": "Это чек после оплаты",
            }
        ],
        llm=llm,
    )

    assert prepared.media_used is True
    assert "Тип: изображение" in prepared.text
    assert "Это чек после оплаты" in prepared.text
    assert "видны реквизиты" in prepared.text
    assert llm.last_multimodal_prompt is not None


def test_prepare_incoming_message_transcribes_voice_attachment(monkeypatch):
    llm = _FakeLLM()

    monkeypatch.setattr(
        "src.media_preprocessor.MediaPreprocessor._transcribe_audio",
        lambda _self, _data, **_kwargs: "Добрый день, у нас две точки и нужен учет остатков.",
    )

    prepared = prepare_incoming_message(
        user_text="",
        attachments=[
            {
                "mime_type": "audio/ogg",
                "file_name": "voice.ogg",
                "data_base64": _audio_base64(),
            }
        ],
        llm=llm,
    )

    assert prepared.media_used is True
    assert "Тип: голосовое сообщение" in prepared.text
    assert "нужен учет остатков" in prepared.text
    assert prepared.used_attachments[0]["type"] == "audio"
    assert prepared.used_attachments[0]["file_name"] == "voice.ogg"


def test_prepare_incoming_message_extracts_docx_text_before_summary():
    llm = _FakeLLM()

    prepared = prepare_incoming_message(
        user_text="",
        attachments=[
            {
                "type": "document",
                "file_name": "request.docx",
                "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "data_base64": _docx_base64("Клиент просит подключить вторую точку."),
            }
        ],
        llm=llm,
    )

    assert prepared.media_used is True
    assert prepared.used_attachments[0]["file_name"] == "request.docx"
    assert "Клиент просит подключить вторую точку." in llm.last_generate_prompt


def test_prepare_incoming_message_extracts_xlsx_text_before_summary():
    llm = _FakeLLM()

    prepared = prepare_incoming_message(
        user_text="",
        attachments=[
            {
                "type": "document",
                "file_name": "sales.xlsx",
                "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "data_base64": _xlsx_base64(
                    [
                        ["Клиент", "Сумма", "Статус"],
                        ["ИП Айна", "120000", "Ожидает оплату"],
                    ]
                ),
            }
        ],
        llm=llm,
    )

    assert prepared.media_used is True
    assert prepared.used_attachments[0]["file_name"] == "sales.xlsx"
    assert "Лист: Продажи" in llm.last_generate_prompt
    assert "ИП Айна" in llm.last_generate_prompt
    assert "Ожидает оплату" in llm.last_generate_prompt


def test_prepare_incoming_message_extracts_doc_text_via_antiword_backend(monkeypatch):
    llm = _FakeLLM()

    class _CompletedProcess:
        def __init__(self):
            self.returncode = 0
            self.stdout = "Коммерческое предложение для клиента".encode("cp1251")

    monkeypatch.setattr("src.media_preprocessor.shutil.which", lambda tool: "/usr/bin/antiword" if tool == "antiword" else None)
    monkeypatch.setattr("src.media_preprocessor.subprocess.run", lambda *args, **kwargs: _CompletedProcess())

    prepared = prepare_incoming_message(
        user_text="",
        attachments=[
            {
                "type": "document",
                "file_name": "offer.doc",
                "mime_type": "application/msword",
                "data_base64": base64.b64encode(b"fake-doc-binary").decode("ascii"),
            }
        ],
        llm=llm,
    )

    assert prepared.media_used is True
    assert prepared.used_attachments[0]["file_name"] == "offer.doc"
    assert "Коммерческое предложение для клиента" in llm.last_generate_prompt


def test_prepare_incoming_message_extracts_pptx_text_before_summary():
    llm = _FakeLLM()

    prepared = prepare_incoming_message(
        user_text="",
        attachments=[
            {
                "type": "document",
                "file_name": "pitch.pptx",
                "mime_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                "data_base64": _pptx_base64(
                    [
                        "Автоматизация магазина и складской учет",
                        "Проблема клиента: нет контроля остатков по точкам",
                    ]
                ),
            }
        ],
        llm=llm,
    )

    assert prepared.media_used is True
    assert prepared.used_attachments[0]["file_name"] == "pitch.pptx"
    assert "Слайд 1: Автоматизация магазина" in llm.last_generate_prompt
    assert "Проблема клиента" in llm.last_generate_prompt


def test_prepare_incoming_message_strips_html_before_summary():
    llm = _FakeLLM()

    prepared = prepare_incoming_message(
        user_text="",
        attachments=[
            {
                "type": "document",
                "file_name": "page.html",
                "mime_type": "text/html; charset=utf-8",
                "text_content": (
                    "<html><body><h1>Заявка</h1><script>alert('x')</script>"
                    "<p>Клиент оплатил счет</p></body></html>"
                ),
            }
        ],
        llm=llm,
    )

    assert prepared.media_used is True
    assert "page.html" in prepared.text
    assert "Заявка Клиент оплатил счет" in llm.last_generate_prompt
    assert "<script>" not in llm.last_generate_prompt


def test_prepare_incoming_message_builds_document_media_meta():
    llm = _FakeLLM(
        generate_response=(
            "Это сопроводительное письмо. Компания Альфа Логистик просит подключение. "
            "Контактное лицо: Алексей Петрович. Сфера: логистика. Город: Алматы."
        )
    )

    prepared = prepare_incoming_message(
        user_text="объясните пожалуйста что это за документ",
        attachments=[
            {
                "type": "document",
                "file_name": "letter.txt",
                "text_content": "Компания Альфа Логистик просит подключение.",
            }
        ],
        llm=llm,
    )

    assert prepared.media_meta["reply_mode"] == "media_first"
    assert prepared.media_meta["extracted_data"]["company_name"] == "Альфа Логистик"
    assert prepared.media_meta["extracted_data"]["contact_name"] == "Алексей Петрович"
    assert prepared.media_meta["extracted_data"]["city"] == "Алматы"
    assert prepared.media_meta["extracted_data"]["business_type"] == "логистика"
    assert prepared.media_meta["media_facts"]
    assert "Альфа Логистик" in prepared.media_meta["answer_context"]
    assert prepared.media_meta["knowledge_cards"][0]["summary"]
    assert prepared.media_meta["knowledge_cards"][0]["facts"]
    assert prepared.media_meta["knowledge_cards"][0]["knowledge_id"]


def test_prepare_incoming_message_builds_image_media_meta():
    llm = _FakeLLM(
        multimodal_response=(
            "На изображении визитка. Компания Альфа Логистик. Алексей Петрович. "
            "Логистика и доставка. Алматы."
        )
    )

    prepared = prepare_incoming_message(
        user_text="что на фото?",
        attachments=[
            {
                "type": "image",
                "file_name": "card.png",
                "mime_type": "image/png",
                "data_base64": _tiny_png_base64(),
            }
        ],
        llm=llm,
    )

    assert prepared.media_meta["reply_mode"] == "media_first"
    assert prepared.media_meta["extracted_data"]["company_name"] == "Альфа Логистик"
    assert prepared.media_meta["extracted_data"]["contact_name"] == "Алексей Петрович"
    assert prepared.media_meta["extracted_data"]["business_type"] == "логистика"


def test_prepare_incoming_message_builds_audio_media_meta(monkeypatch):
    llm = _FakeLLM()

    monkeypatch.setattr(
        "src.media_preprocessor.MediaPreprocessor._transcribe_audio",
        lambda _self, _data, **_kwargs: (
            "Меня зовут Алексей Петрович, компания Альфа Логистик, мы из Алматы."
        ),
    )

    prepared = prepare_incoming_message(
        user_text="что в голосовом?",
        attachments=[
            {
                "mime_type": "audio/ogg",
                "file_name": "voice.ogg",
                "data_base64": _audio_base64(),
            }
        ],
        llm=llm,
    )

    assert prepared.media_meta["reply_mode"] == "media_first"
    assert prepared.media_meta["extracted_data"]["contact_name"] == "Алексей Петрович"
    assert prepared.media_meta["extracted_data"]["company_name"] == "Альфа Логистик"
    assert prepared.media_meta["extracted_data"]["city"] == "Алматы"


def test_prepare_incoming_message_builds_video_media_meta(monkeypatch):
    llm = _FakeLLM(
        multimodal_response=(
            "На кадрах презентация компании Альфа Логистик. Основная тема: логистика и доставка."
        )
    )

    monkeypatch.setattr(
        "src.media_preprocessor.MediaPreprocessor._extract_video_frames",
        lambda _self, _data, _file_name: [base64.b64decode(_tiny_png_base64())],
    )

    prepared = prepare_incoming_message(
        user_text="посмотрите что в видео",
        attachments=[
            {
                "type": "video",
                "file_name": "demo.mp4",
                "mime_type": "video/mp4",
                "data_base64": base64.b64encode(b"fake-video").decode("ascii"),
            }
        ],
        llm=llm,
    )

    assert prepared.media_meta["reply_mode"] == "media_first"
    assert prepared.media_meta["extracted_data"]["company_name"] == "Альфа Логистик"
    assert prepared.media_meta["extracted_data"]["business_type"] == "логистика"


def test_prepare_incoming_message_builds_per_attachment_knowledge_cards():
    llm = _FakeLLM(
        generate_response=(
            "Это документ компании Альфа Логистик. Контактное лицо: Алексей Петрович. Город: Алматы."
        )
    )

    prepared = prepare_incoming_message(
        user_text="вот два файла",
        attachments=[
            {
                "type": "document",
                "file_name": "letter-1.txt",
                "text_content": "Компания Альфа Логистик просит подключение.",
            },
            {
                "type": "document",
                "file_name": "letter-2.txt",
                "text_content": "Компания Бета Маркет просит КП.",
            },
        ],
        llm=llm,
    )

    cards = prepared.media_meta["knowledge_cards"]
    assert len(cards) == 2
    assert cards[0]["file_name"] == "letter-1.txt"
    assert cards[1]["file_name"] == "letter-2.txt"
    assert cards[0]["attachment_fingerprint"] != cards[1]["attachment_fingerprint"]


def test_transcribe_audio_falls_back_to_cpu(monkeypatch):
    llm = _FakeLLM()

    class _CudaModel:
        def transcribe(self, *_args, **_kwargs):
            raise RuntimeError("CUDA out of memory")

    class _CpuModel:
        def transcribe(self, *_args, **_kwargs):
            segment = types.SimpleNamespace(text="Тестовая расшифровка")
            return [segment], None

    def _fake_get_stt_model(self, *, force_device=None):
        return _CudaModel() if force_device == "cuda" else _CpuModel()

    monkeypatch.setattr("src.media_preprocessor.MediaPreprocessor._resolve_stt_device", lambda _self: "cuda")
    monkeypatch.setattr("src.media_preprocessor.MediaPreprocessor._get_stt_model", _fake_get_stt_model)

    prepared = prepare_incoming_message(
        user_text="что в голосовом?",
        attachments=[
            {
                "mime_type": "audio/ogg",
                "file_name": "voice.ogg",
                "data_base64": _audio_base64(),
            }
        ],
        llm=llm,
    )

    assert prepared.media_used is True
    assert "Тестовая расшифровка" in prepared.text


def test_prepare_incoming_message_blocks_non_public_attachment_urls(monkeypatch):
    llm = _FakeLLM()

    class _FakeSession:
        def __init__(self):
            self.trust_env = True

        def get(self, *_args, **_kwargs):
            raise AssertionError("network GET must not happen for blocked URLs")

    monkeypatch.setattr("src.media_preprocessor.requests.Session", _FakeSession)
    monkeypatch.setattr(
        "src.media_preprocessor.MediaPreprocessor._resolve_hostname_ips",
        lambda _self, _hostname, _port: ["127.0.0.1"],
    )

    prepared = prepare_incoming_message(
        user_text="",
        attachments=[
            {
                "type": "document",
                "file_name": "internal.txt",
                "url": "http://internal.example.local/internal.txt",
            }
        ],
        llm=llm,
    )

    assert prepared.media_used is False
    assert prepared.used_attachments == []
    assert prepared.skipped_attachments
    assert prepared.skipped_attachments[0]["reason"] == "attachment url resolves to a non-public address"


def test_api_process_accepts_attachment_only_message(monkeypatch):
    api_mod = _import_api_module_with_fastapi_stub(monkeypatch)

    captured = {}

    class FakeBot:
        state_machine = types.SimpleNamespace(is_final=lambda: False)

        def process(self, text, *, media_turn_context=None):
            captured["text"] = text
            captured["media_turn_context"] = media_turn_context
            return {"response": "Ответ", "decision_trace": None}

    class FakeSessionManager:
        def __init__(self):
            self.bot = FakeBot()

        def serialize_inactive_final_sessions(self, *_args, **_kwargs):
            return 0

        def run_session_job(self, _session_id, *, client_id=None, job):
            captured["run_session_job_client_id"] = client_id
            return job()

        def get_or_create_with_status(self, *_args, **_kwargs):
            return types.SimpleNamespace(bot=self.bot, source="new")

        def touch(self, *_args, **_kwargs):
            return True

    monkeypatch.setattr(api_mod, "_llm", _FakeLLM())
    monkeypatch.setattr(api_mod, "_session_manager", FakeSessionManager())
    monkeypatch.setattr(api_mod, "_bootstrap_bot_memory", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(api_mod, "_save_user_profile", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(api_mod, "_save_media_knowledge", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        api_mod,
        "prepare_autonomous_incoming_message",
        lambda **_kwargs: PreparedMessage(
            text="",
            media_used=True,
            used_attachments=[{"type": "image"}],
            skipped_attachments=[],
            media_turn_context=MediaTurnContext(
                raw_user_text="",
                attachment_only=True,
                source_session_id="",
                source_user_id="",
                used_attachments=({"type": "image"},),
                skipped_attachments=(),
                current_cards=(
                    {
                        "knowledge_id": "card-1",
                        "attachment_fingerprint": "fp-1",
                        "summary": "Из вложения видно, что клиент оплатил счет.",
                        "facts": ["Клиент оплатил счет."],
                        "extracted_data": {"company_name": "Альфа Логистик"},
                    },
                ),
                historical_candidates=(),
                safe_extracted_data={"company_name": "Альфа Логистик"},
                safe_media_facts=("Клиент оплатил счет.",),
            ),
        ),
    )

    req = api_mod.ProcessRequest(
        session_id="sess-1",
        user_id="user-1",
        message=api_mod.MessagePayload(
            text="",
            attachments=[
                api_mod.AttachmentPayload(
                    type="image",
                    file_name="paid.png",
                    data_base64=_tiny_png_base64(),
                )
            ],
        ),
    )

    result = api_mod._process_message_request(req)

    assert captured["text"] == ""
    assert captured["media_turn_context"] is not None
    assert captured["media_turn_context"].attachment_only is True
    assert captured["run_session_job_client_id"] == "user-1"
    assert result["meta"]["media_used"] is True
    assert result["meta"]["attachments_used"] == 1


def test_api_process_accepts_voice_only_message(monkeypatch):
    api_mod = _import_api_module_with_fastapi_stub(monkeypatch)

    captured = {}

    class FakeBot:
        state_machine = types.SimpleNamespace(is_final=lambda: False)

        def process(self, text, *, media_turn_context=None):
            captured["text"] = text
            captured["media_turn_context"] = media_turn_context
            return {"response": "Ответ", "decision_trace": None}

    class FakeSessionManager:
        def __init__(self):
            self.bot = FakeBot()

        def serialize_inactive_final_sessions(self, *_args, **_kwargs):
            return 0

        def run_session_job(self, _session_id, *, client_id=None, job):
            captured["run_session_job_client_id"] = client_id
            return job()

        def get_or_create_with_status(self, *_args, **_kwargs):
            return types.SimpleNamespace(bot=self.bot, source="new")

        def touch(self, *_args, **_kwargs):
            return True

    monkeypatch.setattr(api_mod, "_llm", _FakeLLM())
    monkeypatch.setattr(api_mod, "_session_manager", FakeSessionManager())
    monkeypatch.setattr(api_mod, "_bootstrap_bot_memory", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(api_mod, "_save_user_profile", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(api_mod, "_save_media_knowledge", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        api_mod,
        "prepare_autonomous_incoming_message",
        lambda **_kwargs: PreparedMessage(
            text="",
            media_used=True,
            used_attachments=[{"type": "audio"}],
            skipped_attachments=[],
            media_turn_context=MediaTurnContext(
                raw_user_text="",
                attachment_only=True,
                source_session_id="",
                source_user_id="",
                used_attachments=({"type": "audio"},),
                skipped_attachments=(),
                current_cards=(
                    {
                        "knowledge_id": "voice-1",
                        "attachment_fingerprint": "voice-fp-1",
                        "summary": "Нужен учет по двум магазинам.",
                        "facts": ["Клиенту нужен учет по двум магазинам."],
                        "extracted_data": {"business_type": "розница"},
                    },
                ),
                historical_candidates=(),
                safe_extracted_data={"business_type": "розница"},
                safe_media_facts=("Клиенту нужен учет по двум магазинам.",),
            ),
        ),
    )

    req = api_mod.ProcessRequest(
        session_id="sess-voice",
        user_id="user-voice",
        message=api_mod.MessagePayload(
            text="",
            attachments=[
                api_mod.AttachmentPayload(
                    type="audio",
                    file_name="voice.ogg",
                    mime_type="audio/ogg",
                    data_base64=_audio_base64(),
                )
            ],
        ),
    )

    result = api_mod._process_message_request(req)

    assert captured["text"] == ""
    assert captured["media_turn_context"] is not None
    assert captured["media_turn_context"].attachment_only is True
    assert captured["run_session_job_client_id"] == "user-voice"
    assert result["meta"]["media_used"] is True
    assert result["meta"]["attachments_used"] == 1


def test_api_process_rejects_empty_message_without_attachments(monkeypatch):
    api_mod = _import_api_module_with_fastapi_stub(monkeypatch)

    req = api_mod.ProcessRequest(
        session_id="sess-2",
        user_id="user-2",
        message=api_mod.MessagePayload(text=""),
    )

    with pytest.raises(api_mod.APIError) as exc_info:
        api_mod._process_message_request(req)

    assert exc_info.value.code == "BAD_REQUEST"
