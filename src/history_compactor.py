"""
HistoryCompactor - structured LLM compaction for dialog history.

Compacts only the "old" part of history (all but last N messages).
Supports incremental compaction using previous compact + metadata.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from src.logger import logger


class HistoryCompactSchema(BaseModel):
    """Structured summary format for compacted history."""
    summary: List[str] = Field(default_factory=list)
    key_facts: List[str] = Field(default_factory=list)
    objections: List[str] = Field(default_factory=list)
    decisions: List[str] = Field(default_factory=list)
    open_questions: List[str] = Field(default_factory=list)
    next_steps: List[str] = Field(default_factory=list)


class HistoryCompactor:
    """Compaction utility for dialog history."""

    VERSION = "1.0"

    @classmethod
    def compact(
        cls,
        history_full: List[Dict[str, Any]],
        history_tail_size: int = 4,
        previous_compact: Optional[Dict[str, Any]] = None,
        previous_meta: Optional[Dict[str, Any]] = None,
        llm: Optional[Any] = None,
        fallback_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Compact dialog history and return (compact, meta)."""
        history_full = history_full or []
        tail_size = max(0, min(int(history_tail_size), len(history_full)))
        history_old = history_full[:-tail_size] if tail_size > 0 else list(history_full)

        already_compacted = 0
        if previous_meta and previous_meta.get("compacted_turns") is not None:
            try:
                already_compacted = int(previous_meta.get("compacted_turns", 0))
            except (TypeError, ValueError):
                already_compacted = 0
        already_compacted = max(0, min(already_compacted, len(history_old)))
        new_old = history_old[already_compacted:]

        history_compact: Optional[Dict[str, Any]] = None
        llm_model = getattr(llm, "model", None)

        if new_old and llm is not None and hasattr(llm, "generate_structured"):
            try:
                prompt = cls._build_prompt(previous_compact, new_old)
                result = llm.generate_structured(prompt, HistoryCompactSchema)
                if isinstance(result, dict):
                    history_compact = result
                elif result is not None and hasattr(result, "model_dump"):
                    dumped = result.model_dump()
                    if isinstance(dumped, dict):
                        history_compact = dumped
            except Exception as exc:
                logger.warning("History compaction via LLM failed", error=str(exc))

        if history_compact is None:
            # Fallback compaction (non-LLM or failure)
            history_compact = cls._fallback_compact(
                history_old=history_old,
                previous_compact=previous_compact,
                fallback_context=fallback_context,
            )

        meta = {
            "compacted_turns": len(history_old),
            "tail_size": tail_size,
            "compacted_at": time.time(),
            "compaction_version": cls.VERSION,
            "llm_model": llm_model,
        }
        return history_compact, meta

    @classmethod
    def _build_prompt(
        cls,
        previous_compact: Optional[Dict[str, Any]],
        new_messages: List[Dict[str, Any]],
    ) -> str:
        """Build compaction prompt for structured output."""
        return (
            "You are a CRM dialog summarizer. Update the compacted history.\n"
            "Return JSON matching the schema with keys:\n"
            "summary, key_facts, objections, decisions, open_questions, next_steps.\n"
            "Requirements:\n"
            "- summary: 5-10 short bullet-like statements.\n"
            "- keep facts about the client and commitments.\n"
            "- do not include the last 4 messages (they are provided separately).\n\n"
            f"Previous compact (JSON or null):\n{json.dumps(previous_compact)}\n\n"
            f"New old messages (chronological, list of {{user, bot}}):\n"
            f"{json.dumps(new_messages)}\n"
        )

    @classmethod
    def _fallback_compact(
        cls,
        history_old: List[Dict[str, Any]],
        previous_compact: Optional[Dict[str, Any]],
        fallback_context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Fallback compaction when LLM is unavailable."""
        summary: List[str] = []
        key_facts: List[str] = []
        objections: List[str] = []
        decisions: List[str] = []
        open_questions: List[str] = []
        next_steps: List[str] = []

        if previous_compact:
            summary.extend(previous_compact.get("summary", []) or [])
            key_facts.extend(previous_compact.get("key_facts", []) or [])
            objections.extend(previous_compact.get("objections", []) or [])
            decisions.extend(previous_compact.get("decisions", []) or [])
            open_questions.extend(previous_compact.get("open_questions", []) or [])
            next_steps.extend(previous_compact.get("next_steps", []) or [])

        if history_old:
            summary.append(f"Compacted {len(history_old)} earlier turns.")

        if fallback_context:
            collected_data = fallback_context.get("collected_data", {}) or {}
            for key, value in collected_data.items():
                key_facts.append(f"{key}: {value}")

            metrics = fallback_context.get("metrics", {}) or {}
            for obj in metrics.get("objections", []) or []:
                obj_type = obj.get("type")
                if obj_type:
                    objections.append(str(obj_type))

            ctx = fallback_context.get("context_window", {}) or {}
            for turn in ctx.get("context_window", []) or []:
                if turn.get("intent") and "objection" in str(turn.get("intent")):
                    objections.append(str(turn.get("intent")))

        # De-duplicate while preserving order
        def dedupe(items: List[str]) -> List[str]:
            seen = set()
            result = []
            for item in items:
                if item not in seen:
                    seen.add(item)
                    result.append(item)
            return result

        return {
            "summary": dedupe(summary)[:10],
            "key_facts": dedupe(key_facts)[:10],
            "objections": dedupe(objections)[:10],
            "decisions": dedupe(decisions)[:10],
            "open_questions": dedupe(open_questions)[:10],
            "next_steps": dedupe(next_steps)[:10],
        }
