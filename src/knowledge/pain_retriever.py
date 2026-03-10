"""Isolated retrieval layer for pain-point KB."""

from __future__ import annotations

import re
import threading
from typing import Any, Optional

from src.logger import logger

from .pain_loader import load_pain_knowledge_base
from .retriever import CascadeRetriever


_pain_retriever: Optional[CascadeRetriever] = None
_pain_lock = threading.Lock()

_PAIN_TOP_K = 2
_PAIN_CONTEXT_RESULTS = 2
_YES_RE = re.compile(r"\b(?:yes|да)\b", re.IGNORECASE)
_NO_RE = re.compile(r"\b(?:no|нет)\b", re.IGNORECASE)
_PAIN_GATE_PROMPT = (
    "Ты бинарный классификатор. Определи, описывает ли сообщение клиента БИЗНЕС-БОЛЬ.\n"
    "Верни строго одно слово: YES или NO.\n"
    "YES: клиент описывает проблему, риск, страх, сбой, потери, замедление, ошибки, сложность процесса.\n"
    "NO: приветствие, благодарность, нейтральный контекст, общий вопрос без описания боли.\n"
    "Никаких пояснений."
)


def get_pain_retriever() -> CascadeRetriever:
    """Thread-safe singleton CascadeRetriever для БД по болям."""
    global _pain_retriever

    if _pain_retriever is not None:
        return _pain_retriever

    with _pain_lock:
        if _pain_retriever is not None:
            return _pain_retriever

        pain_kb = load_pain_knowledge_base()

        # Create with embeddings — TEI handles all encoding server-side,
        # no in-process model to worry about duplicating.
        retriever = CascadeRetriever(knowledge_base=pain_kb, use_embeddings=True, cache_name="pain_sections")

        _pain_retriever = retriever
        return _pain_retriever


def reset_pain_retriever() -> None:
    """Reset pain retriever singleton (useful for tests)."""
    global _pain_retriever
    with _pain_lock:
        _pain_retriever = None



def _llm_has_pain_signal(
    *,
    llm: Any,
    user_message: str,
    intent: Optional[str] = None,
) -> Optional[bool]:
    """LLM-driven pain detection: returns True/False or None on classifier failure."""
    if llm is None or not hasattr(llm, "generate"):
        return None

    intent_part = str(intent or "").strip()
    prompt = (
        f"{_PAIN_GATE_PROMPT}\n\n"
        f"INTENT: {intent_part or 'unknown'}\n"
        f"СООБЩЕНИЕ: {user_message}\n"
        "ОТВЕТ:"
    )
    try:
        raw = llm.generate(
            prompt,
            allow_fallback=False,
            purpose="pain_signal_detection",
        )
    except TypeError:
        # Compatibility with minimal test doubles.
        raw = llm.generate(prompt)
    except Exception as exc:
        logger.warning("Pain LLM gate failed; fallback to retrieval-only decision", error=str(exc))
        return None

    text = str(raw or "").strip()
    if not text:
        return None

    first_token = text.split()[0].lower()
    if first_token in {"yes", "да"}:
        return True
    if first_token in {"no", "нет"}:
        return False
    if _YES_RE.search(text):
        return True
    if _NO_RE.search(text):
        return False
    return None


def retrieve_pain_context(
    user_message: str,
    max_chars: int = 800,
    intent: Optional[str] = None,
    llm: Any = None,
) -> str:
    """Поиск по БД болей → форматированный текст для промпта."""
    message = str(user_message or "").strip()
    if not message:
        return ""

    try:
        retriever = get_pain_retriever()
        results = retriever.search(message, top_k=_PAIN_TOP_K)
    except Exception:
        logger.exception("Pain retrieval failed")
        return ""

    if not results:
        return ""

    llm_gate = _llm_has_pain_signal(
        llm=llm,
        user_message=message,
        intent=intent,
    )
    # If classifier explicitly says NO, suppress pain context.
    if llm_gate is False:
        return ""

    return _format_pain_results(results[:_PAIN_CONTEXT_RESULTS], max_chars=max_chars)


def _format_pain_results(results, max_chars: int = 800) -> str:
    parts = []
    total = 0

    for result in results:
        block = f"[{result.section.category}/{result.section.topic}]\n{result.section.facts.strip()}"
        if total + len(block) > max_chars:
            break
        parts.append(block)
        total += len(block)

    if not parts:
        return ""

    header = (
        "=== РЕШЕНИЕ ДЛЯ БОЛИ КЛИЕНТА ===\n"
        "Клиент упомянул проблему — НЕ выделяй отдельным блоком, "
        "вплети решение в свой основной ответ одним связным текстом.\n\n"
    )

    return header + "\n\n".join(parts)
