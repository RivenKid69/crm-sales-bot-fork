"""
REST API обёртка для CRM Sales Bot (Production — autonomous flow).
Пайплайн: WIPON → n8n → Redis → POST /api/v1/process → ответ

Запуск: API_KEY=<secret> uvicorn src.api:app --host 127.0.0.1 --port 8000

Two SQLite tables:
  - conversations: full bot snapshots by (session_id, user_id)
  - user_profiles: structured extracted data per (session_id, user_id)
"""

import json
import logging
import os
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel, Field

from src.bot import SalesBot
from src.llm import OllamaLLM
from src.feature_flags import flags
from src.settings import settings

logger = logging.getLogger(__name__)

API_KEY = os.environ.get("API_KEY", "change-me-in-production")
DB_PATH = os.environ.get("DB_PATH", "data/conversations.db")

_llm = None


# ── Auth ──────────────────────────────────────────────

def verify_api_key(authorization: str = Header(...)):
    """Проверка Bearer-токена."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    if authorization[7:] != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


# ── DB ────────────────────────────────────────────────

def _init_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
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
    conn.commit()
    conn.close()


def _load_snapshot(session_id: str, user_id: str) -> dict | None:
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT snapshot FROM conversations WHERE session_id=? AND user_id=?",
        (session_id, user_id),
    ).fetchone()
    conn.close()
    return json.loads(row[0]) if row and row[0] else None


def _save_snapshot(session_id: str, user_id: str, snapshot: dict):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """INSERT INTO conversations (session_id, user_id, snapshot, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(session_id, user_id)
           DO UPDATE SET snapshot=excluded.snapshot, updated_at=excluded.updated_at""",
        (session_id, user_id, json.dumps(snapshot, ensure_ascii=False), time.time()),
    )
    conn.commit()
    conn.close()


def _save_user_profile(session_id: str, user_id: str, bot: SalesBot):
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

    conn = sqlite3.connect(DB_PATH)
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
            lead_score, lead_temperature, time.time(),
        ),
    )
    conn.commit()
    conn.close()


def _load_user_profile(user_id: str) -> list[dict]:
    """Load all profiles for a user across sessions."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM user_profiles WHERE user_id=? ORDER BY updated_at DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Production flag setup ─────────────────────────────

def _setup_production_flags():
    """Set production flags (mirrors CLI pattern at bot.py:2175-2180)."""
    flags.set_override("autonomous_flow", True)
    flags.set_override("lead_scoring", True)
    flags.set_override("personalization_session_memory", True)
    flags.set_override("tone_semantic_tier2", False)   # GPU OOM prevention
    settings["retriever"]["use_embeddings"] = False     # GPU OOM prevention


# ── App ───────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _llm
    _setup_production_flags()
    _init_db()
    _llm = OllamaLLM()
    logger.info("LLM client initialized, DB ready, autonomous flags set")
    yield
    _llm = None


app = FastAPI(title="CRM Sales Bot API", version="1.0.0", lifespan=lifespan)


# ── Models ────────────────────────────────────────────

class MessagePayload(BaseModel):
    text: str
    timestamp_ms: int = 0


class ContextPayload(BaseModel):
    time_of_day: str = "day"
    timezone: str = "Asia/Almaty"
    meta: dict = {}


class ProcessRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    channel: str = "whatsapp"
    session_id: str
    user_id: str
    message: MessagePayload
    context: ContextPayload = ContextPayload()


# ── Endpoints ─────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "model": "qwen-14b"}


@app.post("/api/v1/process", dependencies=[Depends(verify_api_key)])
def process_message(req: ProcessRequest):
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
        snapshot = _load_snapshot(req.session_id, req.user_id)

        start = time.time()
        if snapshot:
            history_tail = [
                {"user": t["user_message"], "bot": t["bot_response"]}
                for t in snapshot.get("context_window", [])
                if "user_message" in t and "bot_response" in t
            ]
            bot = SalesBot.from_snapshot(
                snapshot, llm=_llm, history_tail=history_tail,
            )
            bot.enable_tracing = True
        else:
            bot = SalesBot(
                _llm, flow_name="autonomous", config_name="default",
                enable_tracing=True,
            )

        result = bot.process(req.message.text)
        processing_ms = int((time.time() - start) * 1000)

        # Persist snapshot + structured user profile
        _save_snapshot(req.session_id, req.user_id, bot.to_snapshot())
        _save_user_profile(req.session_id, req.user_id, bot)

        # kb_used: check KB results in traces
        trace = result.get("decision_trace") or {}
        kb_used = any(
            t.get("purpose") in ("knowledge_search", "knowledge_retrieval")
            for t in trace.get("llm_traces", [])
        )

        return {
            "answer": result["response"],
            "meta": {
                "model": "qwen-14b",
                "processing_ms": processing_ms,
                "kb_used": kb_used,
            },
        }
    except Exception as e:
        logger.exception("Error processing message")
        return {
            "error": {
                "code": "INTERNAL",
                "message": str(e),
            }
        }


@app.get("/api/v1/users/{user_id}/profile", dependencies=[Depends(verify_api_key)])
def get_user_profile(user_id: str):
    """Query collected user data across all sessions."""
    profiles = _load_user_profile(user_id)
    if not profiles:
        raise HTTPException(status_code=404, detail="No profiles found for this user")
    return {"user_id": user_id, "profiles": profiles}
