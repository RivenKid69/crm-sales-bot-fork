"""Preprocess inbound media attachments into text for the dialogue pipeline."""

from __future__ import annotations

import base64
import binascii
import hashlib
import html
import io
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Mapping, Optional, Sequence
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET

import requests

from src.media_turn_context import (
    MediaTurnContext,
    freeze_media_turn_context,
    scrub_media_card_payload,
    scrub_media_extracted_data,
    scrub_media_fact_list,
)


MEDIA_MAX_ATTACHMENTS = int(os.environ.get("MEDIA_MAX_ATTACHMENTS", "6"))
MEDIA_MAX_INLINE_BYTES = int(os.environ.get("MEDIA_MAX_INLINE_BYTES", str(15 * 1024 * 1024)))
MEDIA_DOWNLOAD_TIMEOUT_SECONDS = float(os.environ.get("MEDIA_DOWNLOAD_TIMEOUT_SECONDS", "20"))
MEDIA_MAX_DOCUMENT_CHARS = int(os.environ.get("MEDIA_MAX_DOCUMENT_CHARS", "12000"))
MEDIA_MAX_SUMMARY_CHARS = int(os.environ.get("MEDIA_MAX_SUMMARY_CHARS", "2200"))
MEDIA_MAX_VIDEO_FRAMES = int(os.environ.get("MEDIA_MAX_VIDEO_FRAMES", "4"))
MEDIA_MAX_DOWNLOAD_REDIRECTS = int(os.environ.get("MEDIA_MAX_DOWNLOAD_REDIRECTS", "3"))
MEDIA_MAX_TABLE_SHEETS = int(os.environ.get("MEDIA_MAX_TABLE_SHEETS", "5"))
MEDIA_MAX_TABLE_ROWS = int(os.environ.get("MEDIA_MAX_TABLE_ROWS", "200"))
MEDIA_MAX_TABLE_COLS = int(os.environ.get("MEDIA_MAX_TABLE_COLS", "20"))
MEDIA_MAX_PRESENTATION_SLIDES = int(os.environ.get("MEDIA_MAX_PRESENTATION_SLIDES", "30"))
MEDIA_STT_MODEL = os.environ.get("MEDIA_STT_MODEL", "large-v3-turbo")
MEDIA_STT_LANGUAGE = os.environ.get("MEDIA_STT_LANGUAGE", "ru").strip() or None
MEDIA_STT_BEAM_SIZE = int(os.environ.get("MEDIA_STT_BEAM_SIZE", "5"))
MEDIA_STT_DEVICE = os.environ.get("MEDIA_STT_DEVICE", "auto").strip().lower()
MEDIA_STT_COMPUTE_TYPE = os.environ.get("MEDIA_STT_COMPUTE_TYPE", "").strip().lower()

_STT_MODEL: Any | None = None
_STT_MODEL_DEVICE: str | None = None
_STT_MODEL_LOCK = threading.Lock()

HTML_MIME_TYPES = {"text/html", "application/xhtml+xml"}
RTF_MIME_TYPES = {"application/rtf", "text/rtf"}
OOXML_WORD_MIME_TYPES = {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
OOXML_SPREADSHEET_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel.sheet.macroenabled.12",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.template",
    "application/vnd.ms-excel.template.macroenabled.12",
}
LEGACY_SPREADSHEET_MIME_TYPES = {
    "application/vnd.ms-excel",
    "application/vnd.ms-excel.sheet.binary.macroenabled.12",
}
OOXML_PRESENTATION_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.ms-powerpoint.presentation.macroenabled.12",
    "application/vnd.openxmlformats-officedocument.presentationml.slideshow",
    "application/vnd.openxmlformats-officedocument.presentationml.template",
    "application/vnd.ms-powerpoint.slideshow.macroenabled.12",
    "application/vnd.ms-powerpoint.template.macroenabled.12",
}
ODF_MIME_TYPES = {
    "application/vnd.oasis.opendocument.text",
    "application/vnd.oasis.opendocument.spreadsheet",
    "application/vnd.oasis.opendocument.presentation",
}
PLAIN_TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".tsv", ".json", ".xml", ".yaml", ".yml"}
HTML_EXTENSIONS = {".html", ".htm"}
OOXML_WORD_EXTENSIONS = {".docx"}
OOXML_SPREADSHEET_EXTENSIONS = {".xlsx", ".xlsm", ".xltx", ".xltm"}
LEGACY_SPREADSHEET_EXTENSIONS = {".xls"}
OOXML_PRESENTATION_EXTENSIONS = {".pptx", ".pptm", ".ppsx", ".potx", ".potm"}
ODF_EXTENSIONS = {".odt", ".ods", ".odp"}
RTF_EXTENSIONS = {".rtf"}
PDF_EXTENSIONS = {".pdf"}
LEGACY_WORD_EXTENSIONS = {".doc"}


class MediaProcessingError(RuntimeError):
    """Raised when an attachment cannot be prepared."""


@dataclass
class PreparedMessage:
    """Result of media preprocessing."""

    text: str
    media_used: bool
    used_attachments: list[dict[str, Any]] = field(default_factory=list)
    skipped_attachments: list[dict[str, Any]] = field(default_factory=list)
    media_meta: dict[str, Any] = field(default_factory=dict)
    media_turn_context: Optional[MediaTurnContext] = None


@dataclass
class LoadedAttachment:
    """Normalized attachment content."""

    kind: str
    mime_type: Optional[str]
    file_name: Optional[str]
    caption: Optional[str]
    data: Optional[bytes]
    source: str


@dataclass
class AnalyzedAttachment:
    """Attachment block plus structured knowledge card."""

    block: str
    knowledge_card: dict[str, Any]
    used_payload: dict[str, Any]


class MediaPreprocessor:
    """Converts images, videos and documents into compact text context."""

    def __init__(self, llm: Any):
        self.llm = llm
        self._last_document_summary_prompt: str = ""

    def prepare(
        self,
        user_text: str,
        attachments: Sequence[Mapping[str, Any]] | None,
        *,
        routing_mode: Literal["legacy", "autonomous"] = "legacy",
    ) -> PreparedMessage:
        text = str(user_text or "").strip()
        items = list(attachments or [])
        if not items:
            return PreparedMessage(text=text, media_used=False)

        blocks: list[str] = []
        knowledge_cards: list[dict[str, Any]] = []
        used: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []

        for index, raw_attachment in enumerate(items[:MEDIA_MAX_ATTACHMENTS], start=1):
            try:
                loaded = self._load_attachment(raw_attachment)
                analyzed = self._analyze_attachment(
                    index=index,
                    attachment=loaded,
                    source_user_text=text,
                )
                if not analyzed.block:
                    raise MediaProcessingError("empty summary")
                blocks.append(f"[Вложение {index}]\n{analyzed.block}")
                used.append(analyzed.used_payload)
                if analyzed.knowledge_card:
                    knowledge_cards.append(analyzed.knowledge_card)
            except Exception as exc:
                skipped.append(
                    {
                        "type": raw_attachment.get("type"),
                        "file_name": raw_attachment.get("file_name"),
                        "reason": str(exc),
                    }
                )

        if len(items) > MEDIA_MAX_ATTACHMENTS:
            skipped.append(
                {
                    "type": "overflow",
                    "reason": f"too many attachments: got {len(items)}, max {MEDIA_MAX_ATTACHMENTS}",
                }
            )

        if routing_mode == "autonomous":
            media_turn_context = self._build_media_turn_context(
                user_text=text,
                knowledge_cards=knowledge_cards,
                used_attachments=used,
                skipped_attachments=skipped,
            )
            return PreparedMessage(
                text=text,
                media_used=bool(blocks),
                used_attachments=used,
                skipped_attachments=skipped,
                media_turn_context=media_turn_context,
            )

        combined = self._compose_message(text, blocks)
        media_meta = self._build_media_meta(user_text=text, blocks=blocks, knowledge_cards=knowledge_cards)
        return PreparedMessage(
            text=combined,
            media_used=bool(blocks),
            used_attachments=used,
            skipped_attachments=skipped,
            media_meta=media_meta,
        )

    def _compose_message(self, user_text: str, blocks: Sequence[str]) -> str:
        if not blocks:
            return user_text

        parts: list[str] = []
        if user_text:
            parts.append(user_text)
        parts.append("Дополнительный контекст из вложений клиента:")
        parts.extend(blocks)
        return "\n\n".join(parts).strip()

    def _build_attachment_block(self, attachment: LoadedAttachment) -> str:
        if attachment.kind == "image":
            return self._process_image(attachment)
        if attachment.kind == "video":
            return self._process_video(attachment)
        if attachment.kind == "audio":
            return self._process_audio(attachment)
        if attachment.kind == "document":
            return self._process_document(attachment)
        raise MediaProcessingError(f"unsupported attachment type: {attachment.kind}")

    def _analyze_attachment(
        self,
        *,
        index: int,
        attachment: LoadedAttachment,
        source_user_text: str,
    ) -> AnalyzedAttachment:
        block = self._build_attachment_block(attachment)
        knowledge_card = self._build_media_knowledge_card(
            attachment=attachment,
            block=block,
            source_user_text=source_user_text,
            source_turn=index,
        )
        used_payload = {
            "type": attachment.kind,
            "mime_type": attachment.mime_type,
            "file_name": attachment.file_name,
            "source": attachment.source,
        }
        return AnalyzedAttachment(
            block=block,
            knowledge_card=knowledge_card,
            used_payload=used_payload,
        )

    def _load_attachment(self, raw: Mapping[str, Any]) -> LoadedAttachment:
        file_name = self._clean_optional(raw.get("file_name"))
        mime_type = self._clean_optional(raw.get("mime_type"))
        caption = self._clean_optional(raw.get("caption"))
        data: Optional[bytes] = None
        source = "inline"

        text_content = self._clean_optional(raw.get("text_content"))
        if text_content is not None:
            data = text_content.encode("utf-8")
            source = "inline_text"
            if not mime_type:
                mime_type = "text/plain"

        data_base64 = self._clean_optional(raw.get("data_base64"))
        if data is None and data_base64:
            data = self._decode_base64(data_base64)
            source = "base64"

        url = self._clean_optional(raw.get("url"))
        if data is None and url:
            data, guessed_mime, guessed_name = self._download_attachment(url)
            source = "url"
            mime_type = mime_type or guessed_mime
            file_name = file_name or guessed_name

        kind = self._infer_kind(raw.get("type"), mime_type, file_name)
        if data is None and kind != "image":
            raise MediaProcessingError("attachment has no downloadable content")

        return LoadedAttachment(
            kind=kind,
            mime_type=mime_type,
            file_name=file_name,
            caption=caption,
            data=data,
            source=source,
        )

    @staticmethod
    def _clean_optional(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _decode_base64(self, payload: str) -> bytes:
        base64_payload = payload
        if "," in payload and payload.lower().startswith("data:"):
            base64_payload = payload.split(",", 1)[1]
        try:
            data = base64.b64decode(base64_payload, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise MediaProcessingError("invalid base64 attachment") from exc
        if len(data) > MEDIA_MAX_INLINE_BYTES:
            raise MediaProcessingError(f"attachment exceeds {MEDIA_MAX_INLINE_BYTES} bytes")
        return data

    def _download_attachment(self, url: str) -> tuple[bytes, Optional[str], Optional[str]]:
        final_url, response = self._open_safe_attachment_stream(url)
        try:
            chunks: list[bytes] = []
            total_bytes = 0
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                total_bytes += len(chunk)
                if total_bytes > MEDIA_MAX_INLINE_BYTES:
                    raise MediaProcessingError(
                        f"downloaded attachment exceeds {MEDIA_MAX_INLINE_BYTES} bytes"
                    )
                chunks.append(chunk)
        finally:
            response.close()

        content_type = self._normalize_mime_type(response.headers.get("Content-Type"))
        file_name = Path(urlparse(final_url).path).name or None
        return b"".join(chunks), content_type, file_name

    def _open_safe_attachment_stream(self, url: str) -> tuple[str, requests.Response]:
        session = requests.Session()
        session.trust_env = False
        current_url = url

        for redirect_count in range(MEDIA_MAX_DOWNLOAD_REDIRECTS + 1):
            parsed = self._validate_external_url(current_url)
            try:
                response = session.get(
                    current_url,
                    timeout=MEDIA_DOWNLOAD_TIMEOUT_SECONDS,
                    stream=True,
                    allow_redirects=False,
                )
            except requests.RequestException as exc:
                raise MediaProcessingError("failed to download attachment") from exc

            self._validate_connected_peer(response)

            if 300 <= response.status_code < 400:
                redirect_to = response.headers.get("Location")
                response.close()
                if not redirect_to:
                    raise MediaProcessingError("attachment redirect is missing location header")
                if redirect_count >= MEDIA_MAX_DOWNLOAD_REDIRECTS:
                    raise MediaProcessingError(
                        f"attachment redirect limit exceeded ({MEDIA_MAX_DOWNLOAD_REDIRECTS})"
                    )
                current_url = urljoin(parsed.geturl(), redirect_to)
                continue

            try:
                response.raise_for_status()
            except requests.RequestException as exc:
                response.close()
                raise MediaProcessingError("failed to download attachment") from exc

            return parsed.geturl(), response

        raise MediaProcessingError("attachment redirect limit exceeded")

    def _validate_external_url(self, url: str):
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise MediaProcessingError("only http/https attachment urls are supported")
        if not parsed.hostname:
            raise MediaProcessingError("attachment url must include a hostname")
        if parsed.username or parsed.password:
            raise MediaProcessingError("attachment urls must not include credentials")

        try:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except ValueError as exc:
            raise MediaProcessingError("attachment url contains an invalid port") from exc

        resolved_ips = self._resolve_hostname_ips(parsed.hostname, port)
        if not resolved_ips:
            raise MediaProcessingError("attachment host could not be resolved")

        for resolved_ip in resolved_ips:
            if not self._is_public_ip(resolved_ip):
                raise MediaProcessingError("attachment url resolves to a non-public address")

        return parsed

    def _resolve_hostname_ips(self, hostname: str, port: int) -> list[str]:
        try:
            resolved = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise MediaProcessingError("attachment host could not be resolved") from exc

        ips: list[str] = []
        for _family, _socktype, _proto, _canonname, sockaddr in resolved:
            ip = sockaddr[0]
            if ip not in ips:
                ips.append(ip)
        return ips

    @staticmethod
    def _is_public_ip(raw_ip: str) -> bool:
        try:
            candidate = ipaddress.ip_address(raw_ip.split("%", 1)[0])
        except ValueError:
            return False
        return candidate.is_global

    def _validate_connected_peer(self, response: requests.Response) -> None:
        peer_ip = self._extract_peer_ip(response)
        if peer_ip and not self._is_public_ip(peer_ip):
            response.close()
            raise MediaProcessingError("attachment download connected to a non-public address")

    @staticmethod
    def _extract_peer_ip(response: requests.Response) -> Optional[str]:
        candidates = []
        raw = getattr(response, "raw", None)
        if raw is not None:
            candidates.extend(
                [
                    getattr(raw, "_connection", None),
                    getattr(raw, "connection", None),
                    getattr(getattr(getattr(raw, "_fp", None), "fp", None), "raw", None),
                ]
            )

        for candidate in candidates:
            if candidate is None:
                continue
            sock = getattr(candidate, "sock", None) or getattr(candidate, "_sock", None) or candidate
            getpeername = getattr(sock, "getpeername", None)
            if callable(getpeername):
                try:
                    peer = getpeername()
                except OSError:
                    continue
                if peer:
                    return str(peer[0])
        return None

    @staticmethod
    def _normalize_mime_type(value: Optional[str]) -> str:
        return (value or "").split(";", 1)[0].strip().lower()

    def _infer_kind(self, declared_type: Any, mime_type: Optional[str], file_name: Optional[str]) -> str:
        kind = str(declared_type or "").strip().lower()
        if kind in {"image", "photo", "picture"}:
            return "image"
        if kind in {"video"}:
            return "video"
        if kind in {"audio", "voice", "voice_note", "voice_message", "audio_message"}:
            return "audio"
        if kind in {"document", "file", "pdf", "doc", "docx", "txt"}:
            return "document"

        mime_low = self._normalize_mime_type(mime_type)
        if mime_low.startswith("image/"):
            return "image"
        if mime_low.startswith("video/"):
            return "video"
        if mime_low.startswith("audio/"):
            return "audio"
        if mime_low.startswith("text/") or mime_low in {
            "application/pdf",
            "application/json",
            "application/xml",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            *OOXML_SPREADSHEET_MIME_TYPES,
            *LEGACY_SPREADSHEET_MIME_TYPES,
            *OOXML_PRESENTATION_MIME_TYPES,
            *ODF_MIME_TYPES,
            *RTF_MIME_TYPES,
        }:
            return "document"

        ext = Path(file_name or "").suffix.lower()
        if ext in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}:
            return "image"
        if ext in {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}:
            return "video"
        if ext in {".mp3", ".wav", ".ogg", ".oga", ".opus", ".m4a", ".aac", ".flac"}:
            return "audio"
        if ext in (
            PLAIN_TEXT_EXTENSIONS
            | HTML_EXTENSIONS
            | PDF_EXTENSIONS
            | OOXML_WORD_EXTENSIONS
            | OOXML_SPREADSHEET_EXTENSIONS
            | LEGACY_SPREADSHEET_EXTENSIONS
            | OOXML_PRESENTATION_EXTENSIONS
            | ODF_EXTENSIONS
            | RTF_EXTENSIONS
            | LEGACY_WORD_EXTENSIONS
        ):
            return "document"
        return "document"

    def _process_image(self, attachment: LoadedAttachment) -> str:
        if not attachment.data:
            raise MediaProcessingError("image has no content")
        prompt = (
            "Проанализируй изображение, которое прислал клиент. "
            "Кратко опиши, что на нём, перепиши важный текст с изображения, "
            "выдели проблему или запрос клиента. Ответ дай по-русски, без воды."
        )
        summary = self._multimodal_summary(prompt, [attachment.data], attachment.mime_type)
        return self._format_block(
            attachment=attachment,
            header="Тип: изображение",
            body=summary,
        )

    def _process_video(self, attachment: LoadedAttachment) -> str:
        if not attachment.data:
            raise MediaProcessingError("video has no content")
        frames = self._extract_video_frames(attachment.data, attachment.file_name)
        if not frames:
            raise MediaProcessingError("could not extract video frames")
        prompt = (
            "Это ключевые кадры видео от клиента. "
            "Определи, что показано, какой текст виден на экране, "
            "и в чём может быть суть проблемы или запроса. Ответ дай кратко по-русски."
        )
        summary = self._multimodal_summary(prompt, frames, "image/jpeg")
        return self._format_block(
            attachment=attachment,
            header=f"Тип: видео, извлечено кадров: {len(frames)}",
            body=summary,
        )

    def _process_audio(self, attachment: LoadedAttachment) -> str:
        if not attachment.data:
            raise MediaProcessingError("audio has no content")
        transcript = self._transcribe_audio(
            attachment.data,
            file_name=attachment.file_name,
            mime_type=attachment.mime_type,
        )
        return self._format_block(
            attachment=attachment,
            header="Тип: голосовое сообщение",
            body=f"Расшифровка голосового сообщения клиента:\n{transcript}",
        )

    def _process_document(self, attachment: LoadedAttachment) -> str:
        text = self._extract_document_text(attachment)
        if not text.strip():
            raise MediaProcessingError("document text could not be extracted")

        clipped = text[:MEDIA_MAX_DOCUMENT_CHARS].strip()
        summary = self._summarize_document_text(clipped, attachment.file_name)
        return self._format_block(
            attachment=attachment,
            header="Тип: документ",
            body=summary,
        )

    def _format_block(self, *, attachment: LoadedAttachment, header: str, body: str) -> str:
        lines = [header]
        if attachment.file_name:
            lines.append(f"Файл: {attachment.file_name}")
        if attachment.caption:
            lines.append(f"Подпись клиента: {attachment.caption}")
        lines.append(body.strip())
        return "\n".join(line for line in lines if line).strip()

    def _multimodal_summary(
        self,
        prompt: str,
        images: Sequence[bytes],
        mime_type: Optional[str],
    ) -> str:
        if hasattr(self.llm, "generate_multimodal"):
            encoded = [base64.b64encode(item).decode("ascii") for item in images]
            response = self.llm.generate_multimodal(
                prompt,
                images=encoded,
                mime_type=mime_type,
                allow_fallback=False,
                purpose="media_understanding",
            )
            response_text = str(response or "").strip()
            if response_text:
                return response_text[:MEDIA_MAX_SUMMARY_CHARS]

        fallback = "Клиент прислал визуальное вложение. Автоанализ недоступен, нужен ручной просмотр."
        return fallback

    def _build_media_meta(
        self,
        *,
        user_text: str,
        blocks: Sequence[str],
        knowledge_cards: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        if not blocks and not knowledge_cards:
            return {}

        cards = [dict(card) for card in knowledge_cards if card]
        answer_context = "\n\n".join(
            str(card.get("answer_context") or "").strip()
            for card in cards
            if str(card.get("answer_context") or "").strip()
        ).strip()
        if not answer_context:
            answer_context = "\n\n".join(str(block).strip() for block in blocks if str(block).strip()).strip()
        extracted_data = self._merge_card_extracted_data(cards)
        media_facts = self._derive_media_facts_from_cards(cards)
        reply_mode = "media_first" if self._looks_like_explicit_media_question(user_text) else "none"
        return {
            "source_user_text": user_text,
            "extracted_data": extracted_data,
            "media_facts": media_facts,
            "answer_context": answer_context,
            "reply_mode": reply_mode,
            "knowledge_cards": cards,
        }

    def _build_media_turn_context(
        self,
        *,
        user_text: str,
        knowledge_cards: Sequence[Mapping[str, Any]],
        used_attachments: Sequence[Mapping[str, Any]],
        skipped_attachments: Sequence[Mapping[str, Any]],
    ) -> Optional[MediaTurnContext]:
        current_cards = [
            scrub_media_card_payload(card)
            for card in knowledge_cards
            if card
        ]
        safe_extracted_data = scrub_media_extracted_data(
            self._merge_card_extracted_data(current_cards)
        )
        safe_media_facts = scrub_media_fact_list(
            self._derive_media_facts_from_cards(current_cards),
            limit=8,
        )
        return freeze_media_turn_context(
            MediaTurnContext(
                raw_user_text=str(user_text or ""),
                attachment_only=not str(user_text or "").strip() and bool(current_cards),
                source_session_id="",
                source_user_id="",
                used_attachments=tuple(dict(item) for item in used_attachments if item),
                skipped_attachments=tuple(dict(item) for item in skipped_attachments if item),
                current_cards=tuple(current_cards),
                historical_candidates=tuple(),
                safe_extracted_data=safe_extracted_data,
                safe_media_facts=tuple(safe_media_facts),
            )
        )

    def _build_media_knowledge_card(
        self,
        *,
        attachment: LoadedAttachment,
        block: str,
        source_user_text: str,
        source_turn: int,
    ) -> dict[str, Any]:
        summary = self._extract_block_summary(block)
        analysis = self._generate_media_card_analysis(
            summary=summary,
            answer_context=block,
            attachment=attachment,
        )
        if attachment.kind == "document" and hasattr(self.llm, "last_generate_prompt") and self._last_document_summary_prompt:
            self.llm.last_generate_prompt = self._last_document_summary_prompt
        extracted_data = self._extract_media_structured_data(
            str(analysis.get("answer_context") or analysis.get("summary") or summary or block),
            attachment=attachment,
        )
        if attachment.kind == "document" and hasattr(self.llm, "last_generate_prompt") and self._last_document_summary_prompt:
            self.llm.last_generate_prompt = self._last_document_summary_prompt

        facts = self._dedupe_media_facts(
            list(analysis.get("facts", []) or []) + self._extract_media_facts(analysis.get("answer_context") or block)
        )[:8]
        answer_context = str(analysis.get("answer_context") or block).strip()[:1800]
        return scrub_media_card_payload(
            {
            "knowledge_id": self._build_knowledge_id(attachment=attachment, block=block),
            "attachment_fingerprint": self._attachment_fingerprint(attachment=attachment, block=block),
            "source_session_id": "",
            "source_turn": int(source_turn or 0),
            "file_name": attachment.file_name or "",
            "media_kind": attachment.kind,
            "source_user_text": str(source_user_text or "").strip(),
            "summary": str(analysis.get("summary") or summary).strip()[:600],
            "facts": facts,
            "extracted_data": extracted_data,
            "answer_context": answer_context,
            }
        )

    def _generate_media_card_analysis(
        self,
        *,
        summary: str,
        answer_context: str,
        attachment: LoadedAttachment,
    ) -> dict[str, Any]:
        fallback = {
            "summary": str(summary or answer_context).strip()[:600],
            "facts": self._extract_media_facts(answer_context),
            "extracted_data": {},
            "answer_context": str(answer_context or "").strip()[:1800],
        }
        if not hasattr(self.llm, "generate"):
            return fallback

        prompt = (
            "Ниже уже извлечено содержимое media-вложения клиента.\n"
            "Преобразуй его во внутреннюю карточку знаний в JSON.\n"
            "Верни объект с ключами summary, facts, extracted_data, answer_context.\n"
            "summary: 1-2 предложения до 600 символов.\n"
            "facts: список коротких фактов до 8 элементов.\n"
            "extracted_data: включай только поля, которые явно и достоверно есть во вложении.\n"
            "Не додумывай и не угадывай. Не заполняй поле, если его нет в файле.\n"
            "Лучше пропустить поле, чем вернуть предположение.\n"
            "Если ничего из profile-полей не найдено, верни extracted_data как пустой объект {}.\n"
            "answer_context: компактный, но достаточный контекст для ответа по вложению.\n"
            "Без markdown и без пояснений вне JSON.\n\n"
            f"Тип вложения: {attachment.kind}\n"
            f"Имя файла: {attachment.file_name or 'unknown'}\n"
            f"Извлечённое содержание:\n{answer_context}\n"
        )
        try:
            response = str(
                self.llm.generate(
                    prompt,
                    allow_fallback=False,
                    purpose="media_knowledge_card",
                )
                or ""
            ).strip()
        except TypeError:
            response = str(self.llm.generate(prompt) or "").strip()
        except Exception:
            response = ""

        if not response:
            return fallback

        parsed = self._extract_json_object(response)
        if not parsed:
            return fallback

        return {
            "summary": str(parsed.get("summary") or fallback["summary"]).strip()[:600],
            "facts": self._dedupe_media_facts(parsed.get("facts", []) or fallback["facts"])[:8],
            "extracted_data": dict(parsed.get("extracted_data", {}) or {}),
            "answer_context": str(parsed.get("answer_context") or fallback["answer_context"]).strip()[:1800],
        }

    @staticmethod
    def _extract_json_object(raw_text: str) -> dict[str, Any]:
        text = str(raw_text or "").strip()
        if not text:
            return {}
        candidates = [text]
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidates.append(text[start:end + 1])
        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except Exception:
                continue
            if isinstance(parsed, dict):
                return parsed
        return {}

    @staticmethod
    def _extract_block_summary(block: str) -> str:
        lines = []
        for raw_line in str(block or "").splitlines():
            line = str(raw_line or "").strip()
            if not line or line.startswith(("Тип:", "Файл:", "Подпись клиента:")):
                continue
            lines.append(line)
        return "\n".join(lines).strip()[:600]

    def _merge_card_extracted_data(self, cards: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for card in cards:
            extracted = dict(card.get("extracted_data", {}) or {})
            for key, value in extracted.items():
                if value in (None, "", [], {}):
                    continue
                merged[key] = value
        return merged

    def _derive_media_facts_from_cards(self, cards: Sequence[Mapping[str, Any]]) -> list[str]:
        facts: list[str] = []
        for card in reversed(list(cards or [])):
            for fact in list(card.get("facts", []) or []):
                cleaned = self._clean_fact_text(fact)
                if not cleaned or cleaned in facts or self._is_sensitive_media_fact(cleaned):
                    continue
                facts.append(cleaned)
                if len(facts) >= 5:
                    return facts
        return facts

    @staticmethod
    def _attachment_fingerprint(*, attachment: LoadedAttachment, block: str) -> str:
        payload = attachment.data or block.encode("utf-8", errors="ignore")
        return hashlib.sha256(payload).hexdigest()

    def _build_knowledge_id(self, *, attachment: LoadedAttachment, block: str) -> str:
        base = (
            f"{attachment.kind}|{attachment.file_name or ''}|{self._attachment_fingerprint(attachment=attachment, block=block)}"
        )
        return hashlib.sha256(base.encode("utf-8")).hexdigest()

    def _extract_media_structured_data(
        self,
        text: str,
        *,
        attachment: Optional[LoadedAttachment] = None,
    ) -> dict[str, Any]:
        cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
        if not cleaned:
            return {}

        safe_fields = {
            "company_name",
            "contact_name",
            "client_name",
            "city",
            "company_size",
            "business_type",
            "current_tools",
            "pain_point",
            "pain_category",
            "budget_range",
            "desired_outcome",
            "contact_info",
            "automation_before",
            "automation_now",
            "urgency",
            "industry",
            "timeline",
            "users_count",
        }
        if not hasattr(self.llm, "generate"):
            return {}

        prompt = (
            "Ниже содержимое media-вложения клиента.\n"
            "Извлеки ТОЛЬКО явно присутствующие поля профиля и верни ОДИН JSON-объект.\n"
            "Разрешённые ключи: "
            + ", ".join(sorted(safe_fields))
            + ".\n"
            "Критические правила:\n"
            "- не додумывай;\n"
            "- не угадывай;\n"
            "- не подставляй правдоподобные значения;\n"
            "- не заполняй поле, если его нет в тексте/кадре/документе;\n"
            "- лучше вернуть пустой объект {}, чем предположение.\n"
            "Не возвращай пустые поля, null, пустые строки, 'unknown', 'не указано'.\n"
            "Если во вложении нет явных данных для этих ключей, верни {}.\n"
            "Без markdown и без пояснений вне JSON.\n\n"
            f"Тип вложения: {(attachment.kind if attachment else 'unknown')}\n"
            f"Имя файла: {(attachment.file_name if attachment else 'unknown') or 'unknown'}\n"
            f"Содержимое:\n{cleaned}\n"
        )
        try:
            response = str(
                self.llm.generate(
                    prompt,
                    allow_fallback=False,
                    purpose="media_sparse_extraction",
                )
                or ""
            ).strip()
        except TypeError:
            response = str(self.llm.generate(prompt) or "").strip()
        except Exception:
            response = ""

        parsed = self._extract_json_object(response) if response else {}
        if "extracted_data" in parsed and isinstance(parsed.get("extracted_data"), dict):
            parsed = dict(parsed.get("extracted_data") or {})

        extracted: dict[str, Any] = {}
        for key, value in dict(parsed or {}).items():
            if key not in safe_fields or value in (None, "", [], {}):
                continue
            if isinstance(value, str):
                normalized = value.strip()
                if not normalized or normalized.lower() in {"unknown", "не указано", "нет данных", "n/a", "null"}:
                    continue
                extracted[key] = normalized
                continue
            if isinstance(value, list):
                compact = [item for item in value if item not in (None, "", [], {})]
                if compact:
                    extracted[key] = compact
                continue
            extracted[key] = value

        return extracted

    def _extract_media_structured_data_heuristic(self, text: str) -> dict[str, Any]:
        extracted: dict[str, Any] = {}
        company_token = r"(?-i:[А-ЯA-Z][A-Za-zА-Яа-яЁё0-9&/-]*)"

        company_patterns = (
            rf"(?:компан(?:ия|ии)|организаци(?:я|и)|фирм(?:а|ы)|бренд)\s*[:,-]?\s*[«\"]?({company_token}(?:\s+{company_token}){{0,4}})[»\"]?",
            rf"\b(?:ооо|тоо|ип|ao|ао|пао|зао)\s+[«\"]?({company_token}(?:\s+{company_token}){{0,4}})[»\"]?",
        )
        for pattern in company_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                company_name = self._clean_entity_candidate(match.group(1))
                if company_name and not self._looks_like_person_name(company_name):
                    extracted["company_name"] = company_name
                    break

        contact_patterns = (
            r"(?:контакт(?:ное\s+лицо)?|контакт|представитель|ответственный|меня\s+зовут|зовут)\s*[:,-]?\s*([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+){0,2})",
            r"(?:директор|менеджер|руководитель)\s*[:,-]?\s*([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+){0,2})",
        )
        for pattern in contact_patterns:
            match = re.search(pattern, text)
            if match:
                contact_name = self._clean_entity_candidate(match.group(1))
                if contact_name and self._looks_like_person_name(contact_name):
                    extracted["contact_name"] = contact_name
                    extracted.setdefault("client_name", contact_name)
                    break

        if not extracted.get("contact_name"):
            candidates = re.findall(r"\b([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+){1,2})\b", text)
            for candidate in candidates:
                person_name = self._clean_entity_candidate(candidate)
                if not person_name or not self._looks_like_person_name(person_name):
                    continue
                if extracted.get("company_name") and person_name == extracted["company_name"]:
                    continue
                extracted["contact_name"] = person_name
                extracted.setdefault("client_name", person_name)
                break

        city_match = re.search(
            r"(?:город|г\.|из|в|по)\s*[:,-]?\s*(алмат[ыы]|астан[аеы]?|шымкент[аеи]?|караганд[аеы]?|актоб[еы]?|павлодар[аеи]?|костанай[аеи]?|уральск[аеи]?|атырау|семе[йе]|актау|тараз[аеи]?|кызылорд[аеы]?|туркестан[аеи]?|петропавловск[аеи]?)",
            text,
            re.IGNORECASE,
        )
        if city_match:
            extracted["city"] = self._normalize_city(city_match.group(1))

        if "business_type" not in extracted:
            lower_text = text.lower()
            business_patterns = (
                (r"(?:сфера|отрасль|деятельность|направление|основная тема)\s*[:,-]?\s*логистик[аи]?", "логистика"),
                (r"(?:сфера|отрасль|деятельность|направление|основная тема)\s*[:,-]?\s*доставк[аи]?", "логистика"),
                (r"логистик|доставк", "логистика"),
                (r"магазин|розниц|ритейл|retail", "розничная торговля"),
                (r"опт|b2b", "оптовые продажи"),
                (r"ресторан|кафе|общепит", "общепит"),
                (r"услуг|сервис", "сфера услуг"),
                (r"производств|завод|фабрик", "производство"),
                (r"it|айти|разработ", "IT"),
            )
            for pattern, business_type in business_patterns:
                if re.search(pattern, lower_text, re.IGNORECASE):
                    extracted["business_type"] = business_type
                    break

        return extracted

    def _extract_media_facts(self, text: str) -> list[str]:
        raw_text = str(text or "").strip()
        if not raw_text:
            return []

        lines = [
            self._clean_fact_text(line)
            for line in raw_text.splitlines()
        ]
        facts: list[str] = []
        for line in lines:
            if not line:
                continue
            if line.lower().startswith(("тип:", "файл:", "подпись клиента:")):
                continue
            if self._is_sensitive_media_fact(line):
                continue
            facts.append(line)

        if not facts:
            sentence_candidates = [
                self._clean_fact_text(chunk)
                for chunk in re.split(r"(?<=[.!?])\s+", raw_text)
            ]
            facts = [
                item for item in sentence_candidates
                if item and not self._is_sensitive_media_fact(item)
            ]

        return self._dedupe_media_facts(facts)[:5]

    @staticmethod
    def _clean_fact_text(text: str) -> str:
        value = str(text or "").strip()
        value = re.sub(r"^[*\-•\d.)\s]+", "", value)
        value = re.sub(r"\s+", " ", value)
        return value.strip(" :")

    @staticmethod
    def _dedupe_media_facts(facts: Sequence[str]) -> list[str]:
        unique: list[str] = []
        seen: set[str] = set()
        for fact in facts:
            normalized = re.sub(r"\s+", " ", str(fact or "").strip()).lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            unique.append(str(fact).strip())
        return unique

    @staticmethod
    def _is_sensitive_media_fact(text: str) -> bool:
        value = str(text or "").strip()
        if not value:
            return True
        if re.search(r"\b\d{12}\b", value):
            return True
        if re.search(r"\b(?:\+?\d[\d\s\-()]{8,}\d)\b", value):
            return True
        if re.search(r"\b\S+@\S+\.\S+\b", value):
            return True
        if re.search(r"\b(?:фио|иин|inn|паспорт|mrz|iban|сч[её]т|номер документа)\b", value, re.IGNORECASE):
            return True
        return False

    @staticmethod
    def _clean_entity_candidate(text: str) -> str:
        value = str(text or "").strip(" \t\n\r.,;:!?\"'«»()[]{}")
        value = re.sub(r"\s+", " ", value)
        return value

    @staticmethod
    def _looks_like_person_name(text: str) -> bool:
        value = str(text or "").strip()
        if not value:
            return False
        if re.search(r"\b(?:ооо|тоо|ип|ао|пао|зао|компания|фирма|организация|логистик|доставк)\b", value, re.IGNORECASE):
            return False
        parts = value.split()
        if not 1 <= len(parts) <= 3:
            return False
        return all(re.fullmatch(r"[А-ЯЁ][а-яё]+", part) for part in parts)

    @staticmethod
    def _normalize_city(raw_city: str) -> str:
        city = str(raw_city or "").strip().lower()
        mapping = {
            "алматы": "Алматы",
            "астана": "Астана",
            "астане": "Астана",
            "астаны": "Астана",
            "шымкент": "Шымкент",
            "шымкента": "Шымкент",
            "шымкенте": "Шымкент",
            "караганда": "Караганда",
            "караганды": "Караганда",
            "караганде": "Караганда",
            "актобе": "Актобе",
            "павлодар": "Павлодар",
            "павлодара": "Павлодар",
            "павлодаре": "Павлодар",
            "костанай": "Костанай",
            "костанайе": "Костанай",
            "костаная": "Костанай",
            "уральск": "Уральск",
            "уральске": "Уральск",
            "уральска": "Уральск",
            "атырау": "Атырау",
            "семей": "Семей",
            "семее": "Семей",
            "актау": "Актау",
            "тараз": "Тараз",
            "тараза": "Тараз",
            "таразе": "Тараз",
            "кызылорда": "Кызылорда",
            "кызылорды": "Кызылорда",
            "туркестан": "Туркестан",
            "туркестана": "Туркестан",
            "туркестане": "Туркестан",
            "петропавловск": "Петропавловск",
            "петропавловска": "Петропавловск",
            "петропавловске": "Петропавловск",
        }
        return mapping.get(city, raw_city.strip().title())

    @staticmethod
    def _looks_like_explicit_media_question(user_text: str) -> bool:
        text = str(user_text or "").strip().lower()
        if not text:
            return False

        direct_patterns = (
            "что на фото",
            "что на картинке",
            "что на изображении",
            "что на скрине",
            "что в документе",
            "что это за документ",
            "что это за файл",
            "что в файле",
            "что в голосовом",
            "что в аудио",
            "что на видео",
            "что в видео",
            "что в презентации",
            "что там написано",
            "что человек пишет",
            "что там",
            "что основное",
            "что по сути",
            "в двух словах",
            "коротко объяс",
            "объясни",
            "объясните",
            "опиши",
            "опишите",
            "послушай",
            "послушайте",
            "посмотри",
            "посмотрите",
            "глянь",
            "гляньте",
        )
        return any(pattern in text for pattern in direct_patterns)

    def _summarize_document_text(self, text: str, file_name: Optional[str]) -> str:
        cleaned = re.sub(r"\s+\n", "\n", text).strip()
        if not cleaned:
            return ""

        if hasattr(self.llm, "generate"):
            prompt = (
                "Ниже текст документа от клиента.\n"
                "Сделай краткую выжимку по-русски: что это за документ, какие там ключевые данные, "
                "какой запрос или проблема клиента следует из документа.\n\n"
                f"Имя файла: {file_name or 'unknown'}\n"
                f"Текст документа:\n{cleaned}"
            )
            self._last_document_summary_prompt = prompt
            response = str(self.llm.generate(prompt, allow_fallback=False, purpose="document_summary") or "").strip()
            if response:
                return response[:MEDIA_MAX_SUMMARY_CHARS]

        return cleaned[:MEDIA_MAX_SUMMARY_CHARS]

    def _extract_document_text(self, attachment: LoadedAttachment) -> str:
        data = attachment.data or b""
        mime_type = self._normalize_mime_type(attachment.mime_type)
        suffix = Path(attachment.file_name or "").suffix.lower()

        if suffix in HTML_EXTENSIONS or mime_type in HTML_MIME_TYPES:
            return self._html_to_text(self._decode_text_bytes(data))
        if suffix in OOXML_WORD_EXTENSIONS or mime_type in OOXML_WORD_MIME_TYPES:
            return self._extract_docx_text(data)
        if suffix in OOXML_SPREADSHEET_EXTENSIONS or mime_type in OOXML_SPREADSHEET_MIME_TYPES:
            return self._extract_xlsx_text(data)
        if suffix in LEGACY_SPREADSHEET_EXTENSIONS or mime_type in LEGACY_SPREADSHEET_MIME_TYPES:
            return self._extract_xls_text(data)
        if suffix in OOXML_PRESENTATION_EXTENSIONS or mime_type in OOXML_PRESENTATION_MIME_TYPES:
            return self._extract_pptx_text(data)
        if suffix in ODF_EXTENSIONS or mime_type in ODF_MIME_TYPES:
            return self._extract_odf_text(data)
        if suffix in PDF_EXTENSIONS or mime_type == "application/pdf":
            return self._extract_pdf_text(data)
        if suffix in RTF_EXTENSIONS or mime_type in RTF_MIME_TYPES:
            return self._extract_rtf_text(data)
        if mime_type.startswith("text/") or suffix in PLAIN_TEXT_EXTENSIONS:
            return self._decode_text_bytes(data)
        if suffix in LEGACY_WORD_EXTENSIONS or mime_type == "application/msword":
            return self._extract_doc_text(data)
        return self._decode_text_bytes(data)

    def _transcribe_audio(
        self,
        data: bytes,
        *,
        file_name: Optional[str],
        mime_type: Optional[str],
    ) -> str:
        suffix = self._guess_audio_suffix(file_name=file_name, mime_type=mime_type)

        devices = [self._resolve_stt_device()]
        if devices[0] == "cuda":
            devices.append("cpu")

        last_exc: Exception | None = None
        for device in devices:
            model = self._get_stt_model(force_device=device)

            with tempfile.TemporaryDirectory(prefix="crm_audio_") as temp_dir:
                audio_path = Path(temp_dir) / f"input{suffix}"
                audio_path.write_bytes(data)
                try:
                    segments, _ = model.transcribe(
                        str(audio_path),
                        language=MEDIA_STT_LANGUAGE,
                        beam_size=MEDIA_STT_BEAM_SIZE,
                        vad_filter=True,
                    )
                    transcript = " ".join(
                        segment.text.strip()
                        for segment in segments
                        if getattr(segment, "text", "").strip()
                    )
                except Exception as exc:
                    last_exc = exc
                    if device == "cuda":
                        continue
                    raise MediaProcessingError("audio transcription failed") from exc

            cleaned = re.sub(r"\s+", " ", transcript).strip()
            if not cleaned:
                raise MediaProcessingError("audio speech could not be transcribed")
            return cleaned[:MEDIA_MAX_DOCUMENT_CHARS]

        raise MediaProcessingError("audio transcription failed") from last_exc

    def _get_stt_model(self, *, force_device: Optional[str] = None) -> Any:
        global _STT_MODEL, _STT_MODEL_DEVICE
        device = force_device or self._resolve_stt_device()
        if _STT_MODEL is not None and _STT_MODEL_DEVICE == device:
            return _STT_MODEL

        with _STT_MODEL_LOCK:
            if _STT_MODEL is not None and _STT_MODEL_DEVICE == device:
                return _STT_MODEL

            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise MediaProcessingError("faster-whisper is not installed") from exc

            compute_type = MEDIA_STT_COMPUTE_TYPE or ("float16" if device == "cuda" else "int8")

            try:
                _STT_MODEL = WhisperModel(
                    MEDIA_STT_MODEL,
                    device=device,
                    compute_type=compute_type,
                )
                _STT_MODEL_DEVICE = device
            except Exception as exc:
                raise MediaProcessingError("failed to initialize speech-to-text model") from exc

            return _STT_MODEL

    @staticmethod
    def _resolve_stt_device() -> str:
        if MEDIA_STT_DEVICE in {"cpu", "cuda"}:
            return MEDIA_STT_DEVICE

        try:
            import torch
        except ImportError:
            return "cpu"

        return "cuda" if torch.cuda.is_available() else "cpu"

    def _guess_audio_suffix(self, *, file_name: Optional[str], mime_type: Optional[str]) -> str:
        suffix = Path(file_name or "").suffix.lower()
        if suffix:
            return suffix

        mime_map = {
            "audio/aac": ".aac",
            "audio/flac": ".flac",
            "audio/m4a": ".m4a",
            "audio/mp3": ".mp3",
            "audio/mp4": ".m4a",
            "audio/mpeg": ".mp3",
            "audio/ogg": ".ogg",
            "audio/opus": ".opus",
            "audio/wav": ".wav",
            "audio/webm": ".webm",
            "audio/x-m4a": ".m4a",
            "audio/x-wav": ".wav",
        }
        return mime_map.get(self._normalize_mime_type(mime_type), ".ogg")

    @staticmethod
    def _decode_text_bytes(data: bytes) -> str:
        for encoding in ("utf-8", "utf-8-sig", "cp1251", "latin-1"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="ignore")

    @staticmethod
    def _html_to_text(text: str) -> str:
        without_scripts = re.sub(r"<(script|style)\b.*?</\1>", " ", text, flags=re.IGNORECASE | re.DOTALL)
        plain = re.sub(r"<[^>]+>", " ", without_scripts)
        return html.unescape(re.sub(r"\s+", " ", plain)).strip()

    def _extract_docx_text(self, data: bytes) -> str:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                with archive.open("word/document.xml") as doc:
                    tree = ET.parse(doc)
        except Exception as exc:
            raise MediaProcessingError("failed to parse docx") from exc

        root = tree.getroot()
        texts = [node.text for node in root.iter() if node.text]
        return "\n".join(item.strip() for item in texts if item and item.strip())

    def _extract_xlsx_text(self, data: bytes) -> str:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                shared_strings = self._read_xlsx_shared_strings(archive)
                sheet_entries = self._read_xlsx_sheet_entries(archive)
                chunks: list[str] = []
                for sheet_name, sheet_path in sheet_entries[:MEDIA_MAX_TABLE_SHEETS]:
                    try:
                        sheet_bytes = archive.read(sheet_path)
                    except KeyError:
                        continue
                    row_texts = self._read_xlsx_sheet_rows(sheet_bytes, shared_strings)
                    if not row_texts:
                        continue
                    chunks.append(f"Лист: {sheet_name}")
                    chunks.extend(row_texts)
        except Exception as exc:
            raise MediaProcessingError("failed to parse xlsx") from exc

        text = "\n".join(chunks).strip()
        if text:
            return text
        raise MediaProcessingError("xlsx text could not be extracted")

    def _extract_xls_text(self, data: bytes) -> str:
        try:
            import xlrd
        except ImportError as exc:
            raise MediaProcessingError("xlrd is not installed") from exc

        try:
            workbook = xlrd.open_workbook(file_contents=data)
        except Exception as exc:
            raise MediaProcessingError("failed to parse xls") from exc

        chunks: list[str] = []
        for sheet in workbook.sheets()[:MEDIA_MAX_TABLE_SHEETS]:
            row_texts: list[str] = []
            for row_idx in range(min(sheet.nrows, MEDIA_MAX_TABLE_ROWS)):
                values = [
                    self._normalize_tabular_value(sheet.cell_value(row_idx, col_idx))
                    for col_idx in range(min(sheet.ncols, MEDIA_MAX_TABLE_COLS))
                ]
                values = [value for value in values if value]
                if values:
                    row_texts.append(" | ".join(values))
            if row_texts:
                chunks.append(f"Лист: {sheet.name}")
                chunks.extend(row_texts)

        text = "\n".join(chunks).strip()
        if text:
            return text
        raise MediaProcessingError("xls text could not be extracted")

    def _extract_pptx_text(self, data: bytes) -> str:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                slide_entries = self._read_pptx_slide_entries(archive)
                chunks: list[str] = []
                for slide_index, slide_path in enumerate(slide_entries[:MEDIA_MAX_PRESENTATION_SLIDES], start=1):
                    try:
                        slide_bytes = archive.read(slide_path)
                    except KeyError:
                        continue
                    slide_text = self._read_pptx_slide_text(slide_bytes)
                    if slide_text:
                        chunks.append(f"Слайд {slide_index}: {slide_text}")
        except Exception as exc:
            raise MediaProcessingError("failed to parse pptx") from exc

        text = "\n".join(chunks).strip()
        if text:
            return text
        raise MediaProcessingError("pptx text could not be extracted")

    def _extract_odf_text(self, data: bytes) -> str:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                with archive.open("content.xml") as content:
                    tree = ET.parse(content)
        except Exception as exc:
            raise MediaProcessingError("failed to parse odf document") from exc

        root = tree.getroot()
        texts = [node.text for node in root.iter() if node.text and node.text.strip()]
        text = "\n".join(item.strip() for item in texts).strip()
        if text:
            return text
        raise MediaProcessingError("odf text could not be extracted")

    def _extract_rtf_text(self, data: bytes) -> str:
        raw_text = self._decode_text_bytes(data)

        def decode_hex(match: re.Match[str]) -> str:
            for encoding in ("cp1251", "latin-1"):
                try:
                    return bytes.fromhex(match.group(1)).decode(encoding)
                except UnicodeDecodeError:
                    continue
            return ""

        text = re.sub(r"\\'([0-9a-fA-F]{2})", decode_hex, raw_text)
        text = text.replace("\\par", "\n").replace("\\line", "\n").replace("\\tab", "\t")
        text = re.sub(r"\\[a-zA-Z]+-?\d* ?", " ", text)
        text = text.replace("{", " ").replace("}", " ")
        text = text.replace("\\\\", "\\").replace("\\{", "{").replace("\\}", "}")
        text = re.sub(r"\s+\n", "\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{2,}", "\n", text)
        cleaned = text.strip()
        if cleaned:
            return cleaned
        raise MediaProcessingError("rtf text could not be extracted")

    def _extract_doc_text(self, data: bytes) -> str:
        for tool in ("antiword", "catdoc"):
            tool_path = shutil.which(tool)
            if not tool_path:
                continue

            with tempfile.TemporaryDirectory(prefix="crm_doc_") as temp_dir:
                doc_path = Path(temp_dir) / "input.doc"
                doc_path.write_bytes(data)
                result = subprocess.run(
                    [tool_path, str(doc_path)],
                    capture_output=True,
                    check=False,
                )
                text = self._decode_text_bytes(result.stdout or b"").strip()
                if result.returncode == 0 and text:
                    return text

        raise MediaProcessingError("legacy .doc extraction backend is unavailable")

    @staticmethod
    def _xml_local_name(tag: str) -> str:
        return tag.split("}", 1)[-1]

    def _read_xlsx_shared_strings(self, archive: zipfile.ZipFile) -> list[str]:
        try:
            raw = archive.read("xl/sharedStrings.xml")
        except KeyError:
            return []

        root = ET.fromstring(raw)
        values: list[str] = []
        for item in root.iter():
            if self._xml_local_name(item.tag) != "si":
                continue
            text_parts = [
                node.text.strip()
                for node in item.iter()
                if self._xml_local_name(node.tag) == "t" and node.text and node.text.strip()
            ]
            values.append(" ".join(text_parts).strip())
        return values

    def _read_xlsx_sheet_entries(self, archive: zipfile.ZipFile) -> list[tuple[str, str]]:
        try:
            workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))
            rels_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        except KeyError:
            fallback_paths = sorted(
                path for path in archive.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", path)
            )
            return [(Path(path).stem, path) for path in fallback_paths]

        rel_targets: dict[str, str] = {}
        for rel in rels_root:
            if self._xml_local_name(rel.tag) != "Relationship":
                continue
            rel_id = rel.attrib.get("Id")
            target = rel.attrib.get("Target")
            if not rel_id or not target:
                continue
            if target.startswith("/"):
                normalized = target.lstrip("/")
            else:
                normalized = f"xl/{target}".replace("xl/./", "xl/")
            rel_targets[rel_id] = normalized

        entries: list[tuple[str, str]] = []
        for node in workbook_root.iter():
            if self._xml_local_name(node.tag) != "sheet":
                continue
            sheet_name = node.attrib.get("name") or "sheet"
            rel_id = next(
                (
                    value
                    for key, value in node.attrib.items()
                    if key == "r:id" or key.endswith("}id")
                ),
                None,
            )
            target = rel_targets.get(rel_id or "")
            if target:
                entries.append((sheet_name, target))
        return entries

    def _read_xlsx_sheet_rows(self, data: bytes, shared_strings: Sequence[str]) -> list[str]:
        root = ET.fromstring(data)
        rows: list[str] = []
        for row in root.iter():
            if self._xml_local_name(row.tag) != "row":
                continue
            values: list[str] = []
            for cell in row:
                if self._xml_local_name(cell.tag) != "c":
                    continue
                value = self._read_xlsx_cell_value(cell, shared_strings)
                if value:
                    values.append(value)
                if len(values) >= MEDIA_MAX_TABLE_COLS:
                    break
            if values:
                rows.append(" | ".join(values))
            if len(rows) >= MEDIA_MAX_TABLE_ROWS:
                break
        return rows

    def _read_xlsx_cell_value(self, cell: ET.Element, shared_strings: Sequence[str]) -> str:
        cell_type = cell.attrib.get("t", "")
        if cell_type == "inlineStr":
            parts = [
                node.text.strip()
                for node in cell.iter()
                if self._xml_local_name(node.tag) == "t" and node.text and node.text.strip()
            ]
            return " ".join(parts).strip()

        raw_value = None
        formula = None
        for node in cell:
            tag = self._xml_local_name(node.tag)
            if tag == "v" and node.text is not None:
                raw_value = node.text
            elif tag == "f" and node.text is not None:
                formula = node.text

        if cell_type == "s" and raw_value is not None:
            try:
                return shared_strings[int(raw_value)]
            except (ValueError, IndexError):
                return ""
        if cell_type == "b" and raw_value is not None:
            return "TRUE" if raw_value == "1" else "FALSE"
        if raw_value is not None:
            return self._normalize_tabular_value(raw_value)
        if formula:
            return f"={formula}"
        return ""

    def _read_pptx_slide_entries(self, archive: zipfile.ZipFile) -> list[str]:
        try:
            presentation_root = ET.fromstring(archive.read("ppt/presentation.xml"))
            rels_root = ET.fromstring(archive.read("ppt/_rels/presentation.xml.rels"))
        except KeyError:
            return sorted(
                path for path in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", path)
            )

        rel_targets: dict[str, str] = {}
        for rel in rels_root:
            if self._xml_local_name(rel.tag) != "Relationship":
                continue
            rel_id = rel.attrib.get("Id")
            target = rel.attrib.get("Target")
            if not rel_id or not target:
                continue
            if target.startswith("/"):
                normalized = target.lstrip("/")
            else:
                normalized = f"ppt/{target}".replace("ppt/./", "ppt/")
            rel_targets[rel_id] = normalized

        slide_paths: list[str] = []
        for node in presentation_root.iter():
            if self._xml_local_name(node.tag) != "sldId":
                continue
            rel_id = next(
                (
                    value
                    for key, value in node.attrib.items()
                    if key == "r:id" or key.endswith("}id")
                ),
                None,
            )
            target = rel_targets.get(rel_id or "")
            if target:
                slide_paths.append(target)
        return slide_paths

    def _read_pptx_slide_text(self, data: bytes) -> str:
        root = ET.fromstring(data)
        texts = [
            node.text.strip()
            for node in root.iter()
            if self._xml_local_name(node.tag) == "t" and node.text and node.text.strip()
        ]
        return re.sub(r"\s+", " ", " ".join(texts)).strip()

    @staticmethod
    def _normalize_tabular_value(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        return str(value).strip()

    def _extract_pdf_text(self, data: bytes) -> str:
        for module_name, class_name in (("pypdf", "PdfReader"), ("PyPDF2", "PdfReader")):
            try:
                module = __import__(module_name, fromlist=[class_name])
                reader = getattr(module, class_name)(io.BytesIO(data))
                chunks = []
                for page in reader.pages[:10]:
                    chunks.append(page.extract_text() or "")
                text = "\n".join(chunks).strip()
                if text:
                    return text
            except Exception:
                continue

        pdftotext = shutil.which("pdftotext")
        if pdftotext:
            with tempfile.TemporaryDirectory(prefix="crm_pdf_") as temp_dir:
                pdf_path = Path(temp_dir) / "input.pdf"
                pdf_path.write_bytes(data)
                result = subprocess.run(
                    [pdftotext, "-layout", "-nopgbrk", str(pdf_path), "-"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                text = (result.stdout or "").strip()
                if result.returncode == 0 and text:
                    return text

        raise MediaProcessingError("pdf extraction backend is unavailable")

    def _extract_video_frames(self, data: bytes, file_name: Optional[str]) -> list[bytes]:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise MediaProcessingError("ffmpeg is required for video analysis")

        suffix = Path(file_name or "video.mp4").suffix or ".mp4"
        with tempfile.TemporaryDirectory(prefix="crm_video_") as temp_dir:
            video_path = Path(temp_dir) / f"input{suffix}"
            frames_dir = Path(temp_dir) / "frames"
            frames_dir.mkdir(parents=True, exist_ok=True)
            video_path.write_bytes(data)

            output_pattern = str(frames_dir / "frame_%03d.jpg")
            result = subprocess.run(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    str(video_path),
                    "-vf",
                    "fps=1/2",
                    "-frames:v",
                    str(MEDIA_MAX_VIDEO_FRAMES),
                    output_pattern,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                raise MediaProcessingError("ffmpeg failed to extract frames")

            frames: list[bytes] = []
            for frame_path in sorted(frames_dir.glob("frame_*.jpg"))[:MEDIA_MAX_VIDEO_FRAMES]:
                frames.append(frame_path.read_bytes())
            return frames


def prepare_incoming_message(
    *,
    user_text: str,
    attachments: Sequence[Mapping[str, Any]] | None,
    llm: Any,
    routing_mode: Literal["legacy", "autonomous"] = "legacy",
) -> PreparedMessage:
    """Convenience helper used by the API layer."""

    return MediaPreprocessor(llm=llm).prepare(
        user_text=user_text,
        attachments=attachments,
        routing_mode=routing_mode,
    )


def prepare_autonomous_incoming_message(
    *,
    user_text: str,
    attachments: Sequence[Mapping[str, Any]] | None,
    llm: Any,
) -> PreparedMessage:
    """Autonomous wrapper that always returns immutable media context."""

    return prepare_incoming_message(
        user_text=user_text,
        attachments=attachments,
        llm=llm,
        routing_mode="autonomous",
    )
