from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from src.logger import logger


TranscriptStatus = str
TranscriptProvenance = str


@dataclass(frozen=True)
class HistoryProjectionPolicy:
    """Centralized window sizes for transcript-backed history consumers."""

    classifier_window_turns: int = 4
    decision_window_turns: int = 4
    prompt_window_turns: int = 30
    verifier_window_turns: int = 4
    retrieval_window_turns: int = 6
    generator_dialogue_max_chars: int = 18000
    decision_dialogue_max_chars: int = 12000
    retrieval_dialogue_max_chars: int = 10000
    verifier_dialogue_max_chars: int = 10000
    recent_bot_responses_limit: int = 3
    recent_user_messages_limit: int = 5


@dataclass(frozen=True)
class DialogTranscriptTurn:
    """Canonical completed dialogue turn."""

    turn_index: int
    user_text: str
    bot_text: str
    created_at: float
    committed_at: float
    intent: Optional[str] = None
    state: Optional[str] = None
    action: Optional[str] = None
    reason_codes: tuple[str, ...] = field(default_factory=tuple)
    source_branch: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_legacy_dict(self) -> Dict[str, str]:
        return {"user": self.user_text, "bot": self.bot_text}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "turn_index": self.turn_index,
            "user_text": self.user_text,
            "bot_text": self.bot_text,
            "created_at": self.created_at,
            "committed_at": self.committed_at,
            "intent": self.intent,
            "state": self.state,
            "action": self.action,
            "reason_codes": list(self.reason_codes),
            "source_branch": self.source_branch,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "DialogTranscriptTurn":
        return cls(
            turn_index=int(payload.get("turn_index", 0)),
            user_text=str(payload.get("user_text", "") or ""),
            bot_text=str(payload.get("bot_text", "") or ""),
            created_at=float(payload.get("created_at", time.time())),
            committed_at=float(payload.get("committed_at", time.time())),
            intent=payload.get("intent"),
            state=payload.get("state"),
            action=payload.get("action"),
            reason_codes=tuple(payload.get("reason_codes", []) or []),
            source_branch=payload.get("source_branch"),
            metadata=dict(payload.get("metadata", {}) or {}),
        )


class DialogTranscript:
    """Append-only canonical dialog transcript with named projections."""

    def __init__(
        self,
        *,
        turns: Optional[Sequence[DialogTranscriptTurn]] = None,
        policy: Optional[HistoryProjectionPolicy] = None,
        status: TranscriptStatus = "empty",
        provenance: TranscriptProvenance = "live",
        degraded_continuity: bool = False,
    ) -> None:
        self._turns: List[DialogTranscriptTurn] = list(turns or [])
        self.policy = policy or HistoryProjectionPolicy()
        self.status = status
        self.provenance = provenance
        self.degraded_continuity = bool(degraded_continuity)
        if self._turns and self.status == "empty":
            self.status = "full"

    def __len__(self) -> int:
        return len(self._turns)

    def __bool__(self) -> bool:
        return bool(self._turns)

    def full_transcript(self) -> List[DialogTranscriptTurn]:
        return list(self._turns)

    def completed_turns(self) -> List[DialogTranscriptTurn]:
        return self.full_transcript()

    def full_history_list(self) -> List[Dict[str, str]]:
        return self.legacy_history_view()

    def recent_turns(self, n: int) -> List[DialogTranscriptTurn]:
        limit = max(0, int(n or 0))
        if limit == 0:
            return []
        return list(self._turns[-limit:])

    def recent_bot_responses(self, n: Optional[int] = None) -> List[str]:
        limit = self.policy.recent_bot_responses_limit if n is None else max(0, int(n or 0))
        return [
            turn.bot_text
            for turn in self.recent_turns(limit)
            if str(turn.bot_text or "").strip()
        ]

    def recent_user_messages(self, n: Optional[int] = None) -> List[str]:
        limit = self.policy.recent_user_messages_limit if n is None else max(0, int(n or 0))
        return [
            turn.user_text
            for turn in self.recent_turns(limit)
            if str(turn.user_text or "").strip()
        ]

    def legacy_history_view(self, max_turns: Optional[int] = None) -> List[Dict[str, str]]:
        turns = self._turns if max_turns is None else self.recent_turns(max_turns)
        return [turn.to_legacy_dict() for turn in turns]

    def as_legacy_history(self, max_turns: Optional[int] = None) -> List[Dict[str, str]]:
        return self.legacy_history_view(max_turns=max_turns)

    def classifier_window(self, n: Optional[int] = None) -> List[Dict[str, str]]:
        limit = self.policy.classifier_window_turns if n is None else n
        return self.legacy_history_view(max_turns=limit)

    def decision_window(self, n: Optional[int] = None) -> List[Dict[str, str]]:
        limit = self.policy.decision_window_turns if n is None else n
        return self.legacy_history_view(max_turns=limit)

    def prompt_window(self, max_turns: Optional[int] = None) -> List[Dict[str, str]]:
        limit = self.policy.prompt_window_turns if max_turns is None else max_turns
        return self.legacy_history_view(max_turns=limit)

    def verifier_window(self, n: Optional[int] = None) -> List[Dict[str, str]]:
        limit = self.policy.verifier_window_turns if n is None else n
        return self.legacy_history_view(max_turns=limit)

    def retrieval_window(self, n: Optional[int] = None) -> List[Dict[str, str]]:
        limit = self.policy.retrieval_window_turns if n is None else n
        return self.legacy_history_view(max_turns=limit)

    @staticmethod
    def _render_legacy_history(
        history: Sequence[Dict[str, Any]],
        *,
        max_chars: Optional[int] = None,
        trim_from: str = "head",
        log_consumer: str = "dialogue",
    ) -> str:
        turns = [item for item in list(history or []) if isinstance(item, dict)]
        if not turns:
            return "(начало разговора)"

        blocks: List[tuple[int, str]] = []
        for index, turn in enumerate(turns):
            parts = [f"Клиент: {str(turn.get('user', '') or '')}"]
            bot_text = turn.get("bot", "")
            if str(bot_text or ""):
                parts.append(f"Вы: {str(bot_text or '')}")
            blocks.append((index, "\n".join(parts)))

        rendered = "\n".join(block for _, block in blocks)
        limit = max_chars if max_chars is None else max(0, int(max_chars or 0))
        if limit is None or limit <= 0 or len(rendered) <= limit:
            return rendered

        if trim_from != "head":
            raise ValueError(f"Unsupported trim_from policy: {trim_from}")

        kept = list(blocks)
        trimmed = 0
        while len(kept) > 1:
            candidate = "\n".join(block for _, block in kept)
            if len(candidate) <= limit:
                rendered = candidate
                break
            kept.pop(0)
            trimmed += 1
        else:
            rendered = "\n".join(block for _, block in kept)

        if len(rendered) > limit and len(kept) == 1:
            rendered = "\n".join(block for _, block in kept)

        if len(rendered) > limit:
            # Hard-cap the final payload even when a single remaining turn is longer
            # than the consumer budget. Keep the newest suffix because trim_from=head.
            if limit <= 0:
                rendered = ""
            elif limit <= 3:
                rendered = rendered[-limit:]
            else:
                rendered = "..." + rendered[-(limit - 3):]

        if trimmed > 0:
            first_kept_turn_index = kept[0][0] if kept else 0
            logger.info(
                "Transcript dialogue trimmed",
                consumer=log_consumer,
                trimmed_turns_count=trimmed,
                first_kept_turn_index=first_kept_turn_index,
                reason="ctx_overflow",
                max_chars=limit,
            )
        return rendered

    def render_verbatim_dialogue(
        self,
        max_chars: Optional[int] = None,
        trim_from: str = "head",
        *,
        log_consumer: str = "dialogue",
    ) -> str:
        return self._render_legacy_history(
            self.full_history_list(),
            max_chars=max_chars,
            trim_from=trim_from,
            log_consumer=log_consumer,
        )

    def generator_dialogue_text(self, max_chars: Optional[int] = None) -> str:
        limit = self.policy.generator_dialogue_max_chars if max_chars is None else max_chars
        return self.render_verbatim_dialogue(
            max_chars=limit,
            trim_from="head",
            log_consumer="generator",
        )

    def decision_dialogue_text(self, max_chars: Optional[int] = None) -> str:
        limit = self.policy.decision_dialogue_max_chars if max_chars is None else max_chars
        return self.render_verbatim_dialogue(
            max_chars=limit,
            trim_from="head",
            log_consumer="decision",
        )

    def verifier_dialogue_text(self, max_chars: Optional[int] = None) -> str:
        limit = self.policy.verifier_dialogue_max_chars if max_chars is None else max_chars
        return self.render_verbatim_dialogue(
            max_chars=limit,
            trim_from="head",
            log_consumer="verifier",
        )

    def retrieval_history_list(self, max_turns: Optional[int] = None) -> List[Dict[str, str]]:
        return self.full_history_list() if max_turns is None else self.legacy_history_view(max_turns=max_turns)

    def retrieval_dialogue_text(self, max_chars: Optional[int] = None) -> str:
        limit = self.policy.retrieval_dialogue_max_chars if max_chars is None else max_chars
        return self.render_verbatim_dialogue(
            max_chars=limit,
            trim_from="head",
            log_consumer="retrieval",
        )

    def boundary_history_list(self, max_turns: Optional[int] = None) -> List[Dict[str, str]]:
        return self.full_history_list() if max_turns is None else self.legacy_history_view(max_turns=max_turns)

    def projection_bundle(self) -> Dict[str, List[Dict[str, str]]]:
        return {
            "classifier_window": self.classifier_window(),
            "decision_window": self.decision_window(),
            "prompt_window": self.prompt_window(),
            "verifier_window": self.verifier_window(),
            "retrieval_window": self.retrieval_window(),
            "legacy_history": self.legacy_history_view(),
        }

    def append_turn_internal(
        self,
        *,
        user_text: str,
        bot_text: str,
        created_at: Optional[float] = None,
        committed_at: Optional[float] = None,
        intent: Optional[str] = None,
        state: Optional[str] = None,
        action: Optional[str] = None,
        reason_codes: Optional[Sequence[str]] = None,
        source_branch: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DialogTranscriptTurn:
        timestamp = float(committed_at if committed_at is not None else time.time())
        turn = DialogTranscriptTurn(
            turn_index=len(self._turns),
            user_text=str(user_text or ""),
            bot_text=str(bot_text or ""),
            created_at=float(created_at if created_at is not None else timestamp),
            committed_at=timestamp,
            intent=intent,
            state=state,
            action=action,
            reason_codes=tuple(reason_codes or ()),
            source_branch=source_branch,
            metadata=dict(metadata or {}),
        )
        self._turns.append(turn)
        if self.status == "empty":
            self.status = "full"
        return turn

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "provenance": self.provenance,
            "degraded_continuity": self.degraded_continuity,
            "turns": [turn.to_dict() for turn in self._turns],
        }

    @classmethod
    def from_dict(
        cls,
        payload: Optional[Dict[str, Any]],
        *,
        policy: Optional[HistoryProjectionPolicy] = None,
    ) -> "DialogTranscript":
        data = dict(payload or {})
        turns = [
            DialogTranscriptTurn.from_dict(item)
            for item in list(data.get("turns", []) or [])
            if isinstance(item, dict)
        ]
        return cls(
            turns=turns,
            policy=policy,
            status=str(data.get("status", "empty") or "empty"),
            provenance=str(data.get("provenance", "live") or "live"),
            degraded_continuity=bool(data.get("degraded_continuity", False)),
        )

    @classmethod
    def from_legacy_history(
        cls,
        history: Optional[Sequence[Dict[str, Any]]],
        *,
        policy: Optional[HistoryProjectionPolicy] = None,
        status: TranscriptStatus = "full",
        provenance: TranscriptProvenance = "live",
        degraded_continuity: bool = False,
    ) -> "DialogTranscript":
        transcript = cls(
            policy=policy,
            status=status if history else "empty",
            provenance=provenance,
            degraded_continuity=degraded_continuity,
        )
        now = time.time()
        for index, item in enumerate(list(history or [])):
            if not isinstance(item, dict):
                continue
            transcript._turns.append(
                DialogTranscriptTurn(
                    turn_index=index,
                    user_text=str(item.get("user", "") or ""),
                    bot_text=str(item.get("bot", "") or ""),
                    created_at=now,
                    committed_at=now,
                )
            )
        if transcript._turns and transcript.status == "empty":
            transcript.status = "full"
        return transcript

    @classmethod
    def from_restore_payload(
        cls,
        history_tail: Optional[Sequence[Dict[str, Any]]],
        *,
        policy: Optional[HistoryProjectionPolicy] = None,
        provenance: TranscriptProvenance = "history_tail",
    ) -> "DialogTranscript":
        return cls.from_legacy_history(
            history_tail,
            policy=policy,
            status="partial" if history_tail else "empty",
            provenance=provenance if history_tail else "explicit_restore_payload",
            degraded_continuity=bool(history_tail),
        )


def get_transcript_from_context(context: Optional[Dict[str, Any]]) -> Optional[DialogTranscript]:
    if not isinstance(context, dict):
        return None
    transcript = context.get("transcript")
    if isinstance(transcript, DialogTranscript):
        return transcript
    return None


def project_history_from_context(
    context: Optional[Dict[str, Any]],
    projection: str = "prompt_window",
    *,
    max_turns: Optional[int] = None,
) -> List[Dict[str, str]]:
    transcript = get_transcript_from_context(context)
    if transcript is not None:
        method = getattr(transcript, projection, None)
        if callable(method):
            if max_turns is None:
                return list(method())
            return list(method(max_turns))
        return transcript.legacy_history_view(max_turns=max_turns)

    if isinstance(context, dict):
        projections = context.get("history_projections")
        if isinstance(projections, dict):
            projected = projections.get(projection)
            if isinstance(projected, list):
                if max_turns is None:
                    return list(projected)
                return list(projected[-max(0, int(max_turns or 0)):])

        history = context.get("history")
        if isinstance(history, list):
            if max_turns is None:
                return list(history)
            return list(history[-max(0, int(max_turns or 0)):])

    return []


def history_list_from_context(
    context: Optional[Dict[str, Any]],
    consumer: str = "generator",
    *,
    max_turns: Optional[int] = None,
) -> List[Dict[str, str]]:
    transcript = get_transcript_from_context(context)
    if transcript is not None:
        method = getattr(transcript, f"{consumer}_history_list", None)
        if callable(method):
            if max_turns is None:
                return list(method())
            return list(method(max_turns))
        if max_turns is None:
            return transcript.full_history_list()
        return transcript.legacy_history_view(max_turns=max_turns)

    if isinstance(context, dict):
        history = context.get("history")
        if isinstance(history, list):
            if max_turns is None:
                return list(history)
            return list(history[-max(0, int(max_turns or 0)):])

        projections = context.get("history_projections")
        if isinstance(projections, dict):
            fallback = projections.get("prompt_window") or projections.get("legacy_history")
            if isinstance(fallback, list):
                if max_turns is None:
                    return list(fallback)
                return list(fallback[-max(0, int(max_turns or 0)):])

    return []


def render_dialogue_from_context(
    context: Optional[Dict[str, Any]],
    consumer: str = "generator",
    *,
    max_chars: Optional[int] = None,
) -> str:
    transcript = get_transcript_from_context(context)
    if transcript is not None:
        method = getattr(transcript, f"{consumer}_dialogue_text", None)
        if callable(method):
            if max_chars is None:
                return str(method())
            return str(method(max_chars))
        return transcript.render_verbatim_dialogue(
            max_chars=max_chars,
            trim_from="head",
            log_consumer=consumer,
        )

    history = history_list_from_context(context, consumer, max_turns=None)
    return DialogTranscript._render_legacy_history(
        history,
        max_chars=max_chars,
        trim_from="head",
        log_consumer=consumer,
    )
