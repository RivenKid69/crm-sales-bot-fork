"""
REST API обёртка для CRM Sales Bot (Production — autonomous flow).
Пайплайн: WIPON → n8n → Redis → POST /api/v1/process → ответ

Запуск: API_KEY=<secret> uvicorn src.api:app --host 127.0.0.1 --port 8000

Two SQLite tables:
  - conversations: full bot snapshots by (session_id, user_id)
  - user_profiles: structured extracted data per (session_id, user_id)
  - media_knowledge: persistent media-derived knowledge per user
"""

import hmac
import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import replace

import requests
from fastapi.concurrency import run_in_threadpool
from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

from src.bot import SalesBot
from src.feature_flags import flags
from src.llm import OllamaLLM
from src.media_preprocessor import prepare_autonomous_incoming_message, prepare_incoming_message
from src.session_manager import SessionManager
from src.media_turn_context import (
    freeze_media_turn_context,
    redact_media_text,
    scrub_media_card_payload,
    scrub_media_extracted_data,
    scrub_media_fact_list,
)
from src.settings import settings

logger = logging.getLogger(__name__)

API_KEY = os.environ.get("API_KEY", "change-me-in-production")
DB_PATH = os.environ.get("DB_PATH", "data/conversations.db")
SQLITE_TIMEOUT_SECONDS = int(os.environ.get("SQLITE_TIMEOUT_SECONDS", "30"))
SQLITE_BUSY_TIMEOUT_MS = int(os.environ.get("SQLITE_BUSY_TIMEOUT_MS", "5000"))
DEPENDENCY_HEALTH_TIMEOUT_SECONDS = float(
    os.environ.get("DEPENDENCY_HEALTH_TIMEOUT_SECONDS", "3")
)
STARTUP_WARMUP_ENABLED = os.environ.get("STARTUP_WARMUP_ENABLED", "1") == "1"
STARTUP_WARMUP_ATTEMPTS = int(os.environ.get("STARTUP_WARMUP_ATTEMPTS", "3"))
STARTUP_WARMUP_DELAY_SECONDS = float(os.environ.get("STARTUP_WARMUP_DELAY_SECONDS", "2"))
ACTIVE_SESSION_FINAL_IDLE_SECONDS = int(
    os.environ.get("ACTIVE_SESSION_FINAL_IDLE_SECONDS", "3600")
)
ACTIVE_SESSION_SWEEP_INTERVAL_SECONDS = float(
    os.environ.get("ACTIVE_SESSION_SWEEP_INTERVAL_SECONDS", "60")
)

_llm = None
_session_manager: SessionManager | None = None
_session_sweeper_thread: threading.Thread | None = None
_session_sweeper_stop: threading.Event | None = None
_startup_warmup_state = {
    "status": "pending",
    "started_at": None,
    "finished_at": None,
    "details": {},
    "errors": [],
}
_startup_warmup_lock = threading.Lock()


# ── Error helpers ──────────────────────────────────────

class APIError(Exception):
    """Structured API exception with HTTP status code."""

    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


def _error_payload(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


# ── Auth ──────────────────────────────────────────────

def verify_api_key(authorization: str | None = Header(default=None)):
    """Проверка Bearer-токена."""
    if not authorization:
        raise APIError(401, "UNAUTHORIZED", "Missing Authorization header")
    if not authorization.startswith("Bearer "):
        raise APIError(401, "UNAUTHORIZED", "Missing Bearer token")
    token = authorization[7:]
    if not hmac.compare_digest(token, API_KEY):
        raise APIError(401, "UNAUTHORIZED", "Invalid API key")


# ── DB ────────────────────────────────────────────────

def _db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=SQLITE_TIMEOUT_SECONDS)
    conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
    return conn


def _init_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = _db_connect()
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            session_id TEXT NOT NULL,
            user_id    TEXT NOT NULL,
            snapshot   TEXT,
            updated_at REAL,
            PRIMARY KEY (session_id, user_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_profiles (
            session_id        TEXT NOT NULL,
            user_id           TEXT NOT NULL,
            company_name      TEXT,
            company_size      TEXT,
            industry          TEXT,
            contact_name      TEXT,
            contact_phone     TEXT,
            contact_email     TEXT,
            business_type     TEXT,
            current_tools     TEXT,
            budget_range      TEXT,
            timeline          TEXT,
            pain_category     TEXT,
            role              TEXT,
            users_count       TEXT,
            urgency           TEXT,
            preferred_channel TEXT,
            pain_points       TEXT,
            interested_features TEXT,
            objection_types   TEXT,
            lead_score        INTEGER,
            lead_temperature  TEXT,
            updated_at        REAL,
            PRIMARY KEY (session_id, user_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS media_knowledge (
            user_id               TEXT NOT NULL,
            session_id            TEXT NOT NULL,
            knowledge_id          TEXT NOT NULL,
            attachment_fingerprint TEXT NOT NULL,
            file_name             TEXT,
            media_kind            TEXT,
            source_user_text      TEXT,
            summary               TEXT,
            facts_json            TEXT,
            extracted_data_json   TEXT,
            answer_context        TEXT,
            created_at            REAL,
            updated_at            REAL,
            PRIMARY KEY (user_id, attachment_fingerprint)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_media_knowledge_user_updated ON media_knowledge(user_id, updated_at DESC)"
    )
    conn.commit()
    conn.close()


def _db_healthcheck() -> bool:
    try:
        conn = _db_connect()
        conn.execute("SELECT 1").fetchone()
        conn.close()
        return True
    except Exception as exc:
        logger.warning("DB healthcheck failed", extra={"error": str(exc)})
        return False


def _load_snapshot(session_id: str, user_id: str) -> dict | None:
    conn = _db_connect()
    row = conn.execute(
        "SELECT snapshot FROM conversations WHERE session_id=? AND user_id=?",
        (session_id, user_id),
    ).fetchone()
    conn.close()
    return json.loads(row[0]) if row and row[0] else None


def _split_storage_session_id(storage_session_id: str) -> tuple[str, str]:
    raw = str(storage_session_id or "")
    sep = SessionManager.STORAGE_KEY_SEPARATOR
    if sep in raw:
        client_id, session_id = raw.split(sep, 1)
        return session_id, client_id
    return raw, ""


def _load_storage_snapshot(storage_session_id: str) -> dict | None:
    session_id, user_id = _split_storage_session_id(storage_session_id)
    return _load_snapshot(session_id, user_id)


def _save_snapshot(session_id: str, user_id: str, snapshot: dict):
    conn = _db_connect()
    _save_snapshot_conn(
        conn,
        session_id=session_id,
        user_id=user_id,
        snapshot=snapshot,
        updated_at=time.time(),
    )
    conn.commit()
    conn.close()


def _save_storage_snapshot(storage_session_id: str, snapshot: dict) -> None:
    session_id, user_id = _split_storage_session_id(storage_session_id)
    _save_snapshot(session_id, user_id, snapshot)


def _save_snapshot_conn(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    user_id: str,
    snapshot: dict,
    updated_at: float,
) -> None:
    conn.execute(
        """INSERT INTO conversations (session_id, user_id, snapshot, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(session_id, user_id)
           DO UPDATE SET snapshot=excluded.snapshot, updated_at=excluded.updated_at""",
        (session_id, user_id, json.dumps(snapshot, ensure_ascii=False), updated_at),
    )


def _save_user_profile(session_id: str, user_id: str, bot: SalesBot):
    """Extract and persist structured user data from bot state."""
    conn = _db_connect()
    _save_user_profile_conn(
        conn,
        session_id=session_id,
        user_id=user_id,
        bot=bot,
        updated_at=time.time(),
    )
    conn.commit()
    conn.close()


def _save_user_profile_conn(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    user_id: str,
    bot: SalesBot,
    updated_at: float,
) -> None:
    """Extract and persist structured user data from bot state."""
    # Merge data from collected_data + client_profile
    collected = bot.state_machine.collected_data or {}

    # Client profile from episodic memory
    profile_dict = {}
    if hasattr(bot, "context_window") and hasattr(bot.context_window, "episodic_memory"):
        cp = bot.context_window.episodic_memory.client_profile
        if cp:
            profile_dict = cp.to_dict()

    # COALESCE: collected_data wins, then client_profile
    def _get(key):
        val = collected.get(key)
        if val and not str(val).startswith("_"):
            return str(val)
        val = profile_dict.get(key)
        if val:
            if isinstance(val, list):
                return json.dumps(val, ensure_ascii=False) if val else None
            return str(val) if val else None
        return None

    # Lead score
    lead_score = None
    lead_temperature = None
    if hasattr(bot, "lead_scorer"):
        try:
            ls = bot.lead_scorer.get_score()
            lead_score = ls.score
            lead_temperature = ls.temperature.value if hasattr(ls.temperature, "value") else str(ls.temperature)
        except Exception:
            pass

    # Pain points, features, objections — always from profile (list fields)
    pain_points = json.dumps(profile_dict.get("pain_points", []), ensure_ascii=False)
    interested_features = json.dumps(profile_dict.get("interested_features", []), ensure_ascii=False)
    objection_types = json.dumps(profile_dict.get("objection_types", []), ensure_ascii=False)

    conn.execute(
        """INSERT INTO user_profiles (
               session_id, user_id,
               company_name, company_size, industry, contact_name,
               contact_phone, contact_email,
               business_type, current_tools, budget_range, timeline,
               pain_category, role, users_count, urgency, preferred_channel,
               pain_points, interested_features, objection_types,
               lead_score, lead_temperature, updated_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(session_id, user_id) DO UPDATE SET
               company_name      = COALESCE(excluded.company_name, user_profiles.company_name),
               company_size      = COALESCE(excluded.company_size, user_profiles.company_size),
               industry          = COALESCE(excluded.industry, user_profiles.industry),
               contact_name      = COALESCE(excluded.contact_name, user_profiles.contact_name),
               contact_phone     = COALESCE(excluded.contact_phone, user_profiles.contact_phone),
               contact_email     = COALESCE(excluded.contact_email, user_profiles.contact_email),
               business_type     = COALESCE(excluded.business_type, user_profiles.business_type),
               current_tools     = COALESCE(excluded.current_tools, user_profiles.current_tools),
               budget_range      = COALESCE(excluded.budget_range, user_profiles.budget_range),
               timeline          = COALESCE(excluded.timeline, user_profiles.timeline),
               pain_category     = COALESCE(excluded.pain_category, user_profiles.pain_category),
               role              = COALESCE(excluded.role, user_profiles.role),
               users_count       = COALESCE(excluded.users_count, user_profiles.users_count),
               urgency           = COALESCE(excluded.urgency, user_profiles.urgency),
               preferred_channel = COALESCE(excluded.preferred_channel, user_profiles.preferred_channel),
               pain_points       = excluded.pain_points,
               interested_features = excluded.interested_features,
               objection_types   = excluded.objection_types,
               lead_score        = COALESCE(excluded.lead_score, user_profiles.lead_score),
               lead_temperature  = COALESCE(excluded.lead_temperature, user_profiles.lead_temperature),
               updated_at        = excluded.updated_at""",
        (
            session_id, user_id,
            _get("company_name"), _get("company_size"), _get("industry"), _get("contact_name"),
            _get("contact_phone"), _get("contact_email"),
            _get("business_type"), _get("current_tools"), _get("budget_range"), _get("timeline"),
            _get("pain_category"), _get("role"), _get("users_count"), _get("urgency"),
            _get("preferred_channel"),
            pain_points, interested_features, objection_types,
            lead_score, lead_temperature, updated_at,
        ),
    )


def _load_user_profile(user_id: str) -> list[dict]:
    """Load all profiles for a user across sessions."""
    conn = _db_connect()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM user_profiles WHERE user_id=? ORDER BY updated_at DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _load_recent_media_knowledge(user_id: str, limit: int = 20) -> list[dict]:
    conn = _db_connect()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT *
        FROM media_knowledge
        WHERE user_id=?
        ORDER BY updated_at DESC
        LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()
    conn.close()

    cards: list[dict] = []
    for row in rows:
        item = dict(row)
        item["facts"] = _safe_json_list(item.pop("facts_json", None))
        item["extracted_data"] = _safe_json_dict(item.pop("extracted_data_json", None))
        scrubbed = scrub_media_card_payload(item)
        if scrubbed:
            cards.append(scrubbed)
    return cards


def _safe_json_list(raw: str | None) -> list:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except Exception:
        return []
    return list(parsed) if isinstance(parsed, list) else []


def _safe_json_dict(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def _merge_user_profiles(user_id: str) -> dict:
    rows = _load_user_profile(user_id)
    merged: dict = {}
    list_fields = {"pain_points", "interested_features", "objection_types"}

    for row in rows:
        for key, value in row.items():
            if key in {"session_id", "user_id", "updated_at"}:
                continue
            if key in list_fields:
                existing = list(merged.get(key, []) or [])
                for item in _safe_json_list(value):
                    if item not in existing:
                        existing.append(item)
                if existing:
                    merged[key] = existing
                continue
            if key not in merged and value not in (None, ""):
                merged[key] = _coerce_profile_value(key, value)
    return merged


def _coerce_profile_value(key: str, value):
    if value in (None, ""):
        return value
    if key in {"company_size", "lead_score"}:
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    return value


def _save_media_knowledge_conn(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    user_id: str,
    bot: SalesBot,
    updated_at: float,
) -> None:
    if not hasattr(bot, "context_window") or not hasattr(bot.context_window, "episodic_memory"):
        return
    memory = bot.context_window.episodic_memory
    if not hasattr(memory, "get_recent_media_knowledge_cards"):
        return

    cards = memory.get_recent_media_knowledge_cards(limit=100)
    for raw_card in cards:
        card = scrub_media_card_payload(raw_card)
        if not card:
            continue
        conn.execute(
            """
            INSERT INTO media_knowledge (
                user_id, session_id, knowledge_id, attachment_fingerprint,
                file_name, media_kind, source_user_text, summary,
                facts_json, extracted_data_json, answer_context,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, attachment_fingerprint) DO UPDATE SET
                session_id=excluded.session_id,
                knowledge_id=excluded.knowledge_id,
                file_name=excluded.file_name,
                media_kind=excluded.media_kind,
                source_user_text=excluded.source_user_text,
                summary=excluded.summary,
                facts_json=excluded.facts_json,
                extracted_data_json=excluded.extracted_data_json,
                answer_context=excluded.answer_context,
                created_at=COALESCE(media_knowledge.created_at, excluded.created_at),
                updated_at=excluded.updated_at
            """,
            (
                user_id,
                session_id,
                str(card.get("knowledge_id") or ""),
                str(card.get("attachment_fingerprint") or ""),
                str(card.get("file_name") or ""),
                str(card.get("media_kind") or ""),
                redact_media_text(card.get("source_user_text")),
                redact_media_text(card.get("summary")),
                json.dumps(scrub_media_fact_list(card.get("facts", []) or [], limit=8), ensure_ascii=False),
                json.dumps(scrub_media_extracted_data(card.get("extracted_data", {}) or {}), ensure_ascii=False),
                redact_media_text(card.get("answer_context")),
                float(card.get("created_at") or updated_at),
                float(card.get("updated_at") or updated_at),
            ),
        )

    conn.execute(
        """
        DELETE FROM media_knowledge
        WHERE user_id=?
          AND attachment_fingerprint NOT IN (
              SELECT attachment_fingerprint
              FROM media_knowledge
              WHERE user_id=?
              ORDER BY updated_at DESC
              LIMIT 100
          )
        """,
        (user_id, user_id),
    )


def _persist_bot_state(session_id: str, user_id: str, bot: SalesBot) -> None:
    snapshot = bot.to_snapshot()
    updated_at = time.time()
    conn = _db_connect()
    try:
        _save_snapshot_conn(
            conn,
            session_id=session_id,
            user_id=user_id,
            snapshot=snapshot,
            updated_at=updated_at,
        )
        _save_user_profile_conn(
            conn,
            session_id=session_id,
            user_id=user_id,
            bot=bot,
            updated_at=updated_at,
        )
        _save_media_knowledge_conn(
            conn,
            session_id=session_id,
            user_id=user_id,
            bot=bot,
            updated_at=updated_at,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _save_media_knowledge(session_id: str, user_id: str, bot: SalesBot) -> None:
    """Persist media-derived knowledge from bot memory."""
    conn = _db_connect()
    try:
        _save_media_knowledge_conn(
            conn,
            session_id=session_id,
            user_id=user_id,
            bot=bot,
            updated_at=time.time(),
        )
        conn.commit()
    finally:
        conn.close()


def _run_session_sweeper(stop_event: threading.Event) -> None:
    while not stop_event.wait(ACTIVE_SESSION_SWEEP_INTERVAL_SECONDS):
        manager = _session_manager
        if manager is None:
            continue
        try:
            serialized = manager.serialize_inactive_final_sessions(
                ACTIVE_SESSION_FINAL_IDLE_SECONDS
            )
            if serialized:
                logger.info(
                    "Serialized inactive final sessions",
                    count=serialized,
                    idle_seconds=ACTIVE_SESSION_FINAL_IDLE_SECONDS,
                )
        except Exception:
            logger.exception("Session sweeper failed")


def _bootstrap_bot_memory(bot: SalesBot, *, user_id: str) -> None:
    try:
        profile_data = _merge_user_profiles(user_id)
        media_cards = _load_recent_media_knowledge(user_id, limit=20)
    except sqlite3.OperationalError as exc:
        logger.warning("cross-session media bootstrap skipped", extra={"error": str(exc)})
        return
    if hasattr(bot, "hydrate_external_memory"):
        bot.hydrate_external_memory(profile_data=profile_data, media_cards=media_cards)


# ── Production flag setup ─────────────────────────────

def _setup_production_flags():
    """Set production flags (mirrors CLI pattern at bot.py:2175-2180)."""
    flags.set_override("autonomous_flow", True)
    flags.set_override("lead_scoring", True)
    flags.set_override("personalization_session_memory", True)
    flags.set_override("tone_semantic_tier2", False)
    # Embeddings served via TEI, no in-process model


def _set_startup_warmup_state(
    status: str,
    *,
    details: dict | None = None,
    errors: list[str] | None = None,
) -> None:
    with _startup_warmup_lock:
        if _startup_warmup_state["started_at"] is None:
            _startup_warmup_state["started_at"] = time.time()
        _startup_warmup_state["status"] = status
        _startup_warmup_state["details"] = details or {}
        _startup_warmup_state["errors"] = list(errors or [])
        if status in {"ready", "failed"}:
            _startup_warmup_state["finished_at"] = time.time()


def _get_startup_warmup_state() -> dict:
    with _startup_warmup_lock:
        return {
            "status": _startup_warmup_state["status"],
            "started_at": _startup_warmup_state["started_at"],
            "finished_at": _startup_warmup_state["finished_at"],
            "details": dict(_startup_warmup_state["details"]),
            "errors": list(_startup_warmup_state["errors"]),
        }


def _tei_healthcheck(base_url: str) -> bool:
    try:
        response = requests.get(
            f"{base_url.rstrip('/')}/health",
            timeout=DEPENDENCY_HEALTH_TIMEOUT_SECONDS,
        )
        return response.status_code == 200
    except Exception as exc:
        logger.warning(
            "TEI healthcheck failed",
            extra={"base_url": base_url, "error": str(exc)},
        )
        return False


def _dependency_snapshot() -> dict[str, bool]:
    return {
        "db": _db_healthcheck(),
        "llm": bool(_llm and _llm.health_check()),
        "tei_embed": _tei_healthcheck(settings.retriever.embedder_url),
        "tei_rerank": _tei_healthcheck(settings.reranker.url),
    }


def _warmup_retrieval_caches() -> dict:
    from src.knowledge.pain_retriever import get_pain_retriever, reset_pain_retriever
    from src.knowledge.retriever import get_retriever, reset_retriever

    errors: list[str] = []
    for attempt in range(1, STARTUP_WARMUP_ATTEMPTS + 1):
        try:
            reset_retriever()
            reset_pain_retriever()

            retriever = get_retriever(use_embeddings=settings.retriever.use_embeddings)
            if settings.retriever.use_embeddings and not retriever._embeddings_ready:
                raise RuntimeError("KB embeddings were not initialized")

            pain_retriever = get_pain_retriever()
            if getattr(pain_retriever, "_embeddings_ready", False) is not True:
                raise RuntimeError("Pain embeddings were not initialized")

            return {
                "attempts_used": attempt,
                "kb_embeddings_ready": bool(retriever._embeddings_ready),
                "pain_embeddings_ready": bool(getattr(pain_retriever, "_embeddings_ready", False)),
            }
        except Exception as exc:
            err = f"attempt {attempt}: {exc}"
            errors.append(err)
            logger.exception("Startup warmup attempt failed", extra={"attempt": attempt})
            if attempt < STARTUP_WARMUP_ATTEMPTS:
                time.sleep(STARTUP_WARMUP_DELAY_SECONDS)

    raise RuntimeError("; ".join(errors))


def _run_startup_warmup() -> None:
    started_at = time.time()
    _set_startup_warmup_state("running")
    try:
        details = _warmup_retrieval_caches()
        details["duration_seconds"] = round(time.time() - started_at, 2)
        _set_startup_warmup_state("ready", details=details)
        logger.info("Startup warmup completed", extra=details)
    except Exception as exc:
        _set_startup_warmup_state(
            "failed",
            errors=[str(exc)],
            details={"duration_seconds": round(time.time() - started_at, 2)},
        )
        logger.exception("Startup warmup failed")


def _start_startup_warmup() -> None:
    if not STARTUP_WARMUP_ENABLED:
        _set_startup_warmup_state("ready", details={"warmup_skipped": True})
        logger.info("Startup warmup disabled")
        return

    with _startup_warmup_lock:
        _startup_warmup_state["status"] = "pending"
        _startup_warmup_state["started_at"] = None
        _startup_warmup_state["finished_at"] = None
        _startup_warmup_state["details"] = {}
        _startup_warmup_state["errors"] = []

    thread = threading.Thread(
        target=_run_startup_warmup,
        name="crm-sales-bot-startup-warmup",
        daemon=True,
    )
    thread.start()


# ── App ───────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _llm, _session_manager, _session_sweeper_thread, _session_sweeper_stop
    _setup_production_flags()
    if API_KEY == "change-me-in-production":
        logger.warning("API_KEY is set to insecure default value")
    _init_db()
    _llm = OllamaLLM()
    _session_manager = SessionManager(
        load_snapshot=_load_storage_snapshot,
        save_snapshot=_save_storage_snapshot,
        require_client_id=True,
    )
    _session_sweeper_stop = threading.Event()
    _session_sweeper_thread = threading.Thread(
        target=_run_session_sweeper,
        args=(_session_sweeper_stop,),
        name="crm-sales-bot-session-sweeper",
        daemon=True,
    )
    _session_sweeper_thread.start()
    _start_startup_warmup()
    logger.info("LLM client initialized, DB ready, autonomous flags set")
    yield
    if _session_sweeper_stop is not None:
        _session_sweeper_stop.set()
    if _session_sweeper_thread is not None:
        _session_sweeper_thread.join(timeout=2)
    if _session_manager is not None:
        try:
            closed = _session_manager.close_all_sessions()
            if closed:
                logger.info("Serialized sessions on shutdown", count=closed)
        except Exception:
            logger.exception("Failed to serialize sessions on shutdown")
    _session_sweeper_stop = None
    _session_sweeper_thread = None
    _session_manager = None
    _llm = None


app = FastAPI(title="CRM Sales Bot API", version="1.0.0", lifespan=lifespan)


@app.exception_handler(APIError)
async def api_error_handler(_: Request, exc: APIError):
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_payload(exc.code, exc.message),
    )


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(_: Request, exc: RequestValidationError):
    errors = exc.errors()
    first_error = errors[0].get("msg") if errors else "Invalid request payload"
    return JSONResponse(
        status_code=400,
        content=_error_payload("BAD_REQUEST", first_error),
    )


# ── Models ────────────────────────────────────────────

class AttachmentPayload(BaseModel):
    type: str | None = None
    mime_type: str | None = None
    file_name: str | None = None
    url: str | None = None
    data_base64: str | None = None
    text_content: str | None = None
    caption: str | None = None


class MessagePayload(BaseModel):
    text: str = ""
    timestamp_ms: int = 0
    attachments: list[AttachmentPayload] = Field(default_factory=list)


class ContextPayload(BaseModel):
    time_of_day: str = "day"
    timezone: str = "Asia/Almaty"
    meta: dict = Field(default_factory=dict)


class ProcessRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    channel: str = "whatsapp"
    session_id: str
    user_id: str
    message: MessagePayload
    context: ContextPayload = Field(default_factory=ContextPayload)


def _build_sula_request(payload: dict) -> tuple[ProcessRequest, dict]:
    if not isinstance(payload, dict):
        raise APIError(400, "BAD_REQUEST", "Sula payload item must be an object")

    phone = payload.get("cleint_phone")
    if phone is None:
        phone = payload.get("client_phone")

    if phone is None:
        raise APIError(400, "BAD_REQUEST", "Sula payload must contain cleint_phone")

    timestamp = payload.get("timestamp", 0)
    try:
        timestamp_ms = int(timestamp)
    except (TypeError, ValueError) as err:
        raise APIError(400, "BAD_REQUEST", "Sula timestamp must be an integer") from err

    normalized = {
        "id": str(payload.get("id") or str(uuid.uuid4())),
        "timestamp": timestamp_ms,
        "session": str(payload.get("session") or ""),
        "client_text": str(payload.get("client_text") or ""),
        "cleint_phone": str(phone),
    }

    return (
        ProcessRequest(
            channel="sula",
            session_id=normalized["session"],
            user_id=normalized["cleint_phone"],
            message=MessagePayload(
                text=normalized["client_text"],
                timestamp_ms=normalized["timestamp"],
            ),
        ),
        normalized,
    )


def _parse_process_payload(payload: object) -> tuple[str, ProcessRequest, dict | None]:
    if isinstance(payload, list):
        if not payload:
            raise APIError(400, "BAD_REQUEST", "Sula payload list must not be empty")
        request_payload, normalized = _build_sula_request(payload[-1])
        return "sula_list", request_payload, normalized

    if isinstance(payload, dict):
        if {"session_id", "user_id", "message"} <= set(payload.keys()):
            try:
                return "default", ProcessRequest.model_validate(payload), None
            except ValidationError as err:
                first_error = err.errors()[0].get("msg") if err.errors() else "Invalid request payload"
                raise APIError(400, "BAD_REQUEST", first_error) from err

        if {"session", "client_text"} <= set(payload.keys()) and (
            "cleint_phone" in payload or "client_phone" in payload
        ):
            request_payload, normalized = _build_sula_request(payload)
            return "sula_object", request_payload, normalized

    raise APIError(400, "BAD_REQUEST", "Unsupported request payload")


def _render_sula_response(response: dict, normalized: dict, wrap_in_list: bool) -> dict | list[dict]:
    payload = {
        "id": normalized["id"],
        "timestamp": normalized["timestamp"],
        "session": normalized["session"],
        "client_text": normalized["client_text"],
        "cleint_phone": normalized["cleint_phone"],
        "ai_text": response["answer"],
    }
    return [payload] if wrap_in_list else payload


def _process_message_request(req: ProcessRequest) -> dict:
    if not req.message.text.strip() and not req.message.attachments:
        raise APIError(400, "BAD_REQUEST", "message.text must not be empty when attachments are absent")

    start = time.time()
    prepared_message = prepare_autonomous_incoming_message(
        user_text=req.message.text,
        attachments=[item.model_dump(exclude_none=True) for item in req.message.attachments],
        llm=_llm,
    )
    if not prepared_message.text.strip() and not prepared_message.media_used:
        raise APIError(400, "BAD_REQUEST", "message must contain text or a supported attachment")

    if _session_manager is None:
        raise APIError(503, "SERVICE_UNAVAILABLE", "Session manager is not initialized")

    serialized = _session_manager.serialize_inactive_final_sessions(
        ACTIVE_SESSION_FINAL_IDLE_SECONDS
    )
    if serialized:
        logger.info(
            "Serialized inactive final sessions on request path",
            count=serialized,
            idle_seconds=ACTIVE_SESSION_FINAL_IDLE_SECONDS,
        )

    acquire = _session_manager.get_or_create_with_status(
        req.session_id,
        llm=_llm,
        client_id=req.user_id,
        flow_name="autonomous",
        config_name="default",
        enable_tracing=True,
    )
    bot = acquire.bot
    if acquire.source == "new":
        _bootstrap_bot_memory(bot, user_id=req.user_id)

    media_turn_context = prepared_message.media_turn_context
    if media_turn_context is not None:
        media_turn_context = freeze_media_turn_context(
            replace(
                media_turn_context,
                source_session_id=req.session_id,
                source_user_id=req.user_id,
            )
        )

    result = bot.process(
        prepared_message.text,
        media_turn_context=media_turn_context,
    )
    processing_ms = int((time.time() - start) * 1000)
    _session_manager.touch(
        req.session_id,
        client_id=req.user_id,
        is_final=bot.state_machine.is_final(),
    )
    _save_user_profile(req.session_id, req.user_id, bot)
    _save_media_knowledge(req.session_id, req.user_id, bot)

    # kb_used: check KB results in traces
    trace = result.get("decision_trace") or {}
    kb_used = any(
        t.get("purpose") in ("knowledge_search", "knowledge_retrieval")
        for t in trace.get("llm_traces", [])
    )

    return {
        "answer": result["response"],
        "meta": {
            "model": settings.llm.model,
            "processing_ms": processing_ms,
            "kb_used": kb_used,
            "media_used": prepared_message.media_used,
            "attachments_used": len(prepared_message.used_attachments),
            "attachments_skipped": len(prepared_message.skipped_attachments),
        },
    }


# ── Endpoints ─────────────────────────────────────────

@app.get("/health")
def health():
    warmup = _get_startup_warmup_state()
    return {
        "status": "ok",
        "model": settings.llm.model,
        "warmup_status": warmup["status"],
    }


@app.get("/ready")
def ready():
    dependencies = _dependency_snapshot()
    warmup = _get_startup_warmup_state()
    is_ready = all(dependencies.values()) and warmup["status"] == "ready"
    payload = {
        "status": "ready" if is_ready else "not_ready",
        "model": settings.llm.model,
        "dependencies": dependencies,
        "warmup": warmup,
    }
    return JSONResponse(status_code=200 if is_ready else 503, content=payload)


@app.post("/api/v1/process", dependencies=[Depends(verify_api_key)])
@app.post("/api/v1/process/sula", dependencies=[Depends(verify_api_key)])
async def process_message(request: Request):
    """
    Обработка одного хода диалога (autonomous flow).

    1. Загрузить snapshot из SQLite по (session_id, user_id).
    2. Восстановить / создать бота (flow_name="autonomous").
    3. Обработать сообщение.
    4. Сохранить snapshot + извлечь данные в user_profiles.
    5. Вернуть { answer, meta }.

    NOTE: `def` (не `async def`) — bot.process() синхронный (Ollama HTTP).
    FastAPI автоматически запустит в threadpool.
    """
    try:
        try:
            raw_payload = await request.json()
        except json.JSONDecodeError as err:
            raise APIError(400, "BAD_REQUEST", "Invalid JSON body") from err

        payload_kind, req, normalized_sula = _parse_process_payload(raw_payload)
        response = await run_in_threadpool(_process_message_request, req)

        if payload_kind == "default":
            return response

        return _render_sula_response(
            response,
            normalized_sula,
            wrap_in_list=payload_kind == "sula_list",
        )
    except APIError:
        raise
    except Exception as err:
        logger.exception("Error processing message")
        raise APIError(500, "INTERNAL", "Internal server error") from err


@app.get("/api/v1/users/{user_id}/profile", dependencies=[Depends(verify_api_key)])
def get_user_profile(user_id: str):
    """Query collected user data across all sessions."""
    profiles = _load_user_profile(user_id)
    if not profiles:
        raise APIError(404, "NOT_FOUND", "No profiles found for this user")
    return {"user_id": user_id, "profiles": profiles}
