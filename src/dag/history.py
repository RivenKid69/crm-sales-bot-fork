"""
History Manager - управление history states для прерванных диалогов.

Позволяет:
- Сохранять состояние перед прерыванием
- Возвращаться к предыдущему состоянию
- Поддержка shallow и deep history

Пример использования:
    User: "Хочу забронировать" -> booking_flow (collect_date)
    User: "А какие цены?" -> price_inquiry (прерывание с сохранением истории)
    User: "Понял, вернёмся к бронированию" -> booking_flow (resume at collect_date)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import logging
import time

from src.dag.models import HistoryType

logger = logging.getLogger(__name__)


@dataclass
class HistoryEntry:
    """Запись в истории состояний."""
    state: str
    region_id: str
    timestamp: float = field(default_factory=time.time)
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            "state": self.state,
            "region_id": self.region_id,
            "timestamp": self.timestamp,
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HistoryEntry":
        """Deserialize from dict."""
        return cls(
            state=data["state"],
            region_id=data["region_id"],
            timestamp=data.get("timestamp", time.time()),
            data=data.get("data", {}),
        )


class HistoryManager:
    """
    Управление history states для прерванных диалогов.

    Позволяет вернуться к предыдущему состоянию после прерывания,
    поддерживая как shallow (только последнее), так и deep (полная
    история) режимы.

    Usage:
        manager = HistoryManager()

        # Save state before interruption
        manager.save("booking_flow", "collect_date", data={"step": 1})

        # ... user interrupts to ask about prices ...

        # Restore state when returning
        state = manager.restore("booking_flow")
        # Returns "collect_date"
    """

    def __init__(self, max_deep_history: int = 10):
        """
        Initialize history manager.

        Args:
            max_deep_history: Maximum entries in deep history per region
        """
        self.max_deep_history = max_deep_history

        # region_id -> last_state (shallow history)
        self._shallow: Dict[str, str] = {}

        # region_id -> list of HistoryEntry (deep history)
        self._deep: Dict[str, List[HistoryEntry]] = {}

        # region_id -> associated data at time of save
        self._data: Dict[str, Dict[str, Any]] = {}

        # Track which regions have been interrupted
        self._interrupted: Dict[str, bool] = {}

    def save(
        self,
        region_id: str,
        state: str,
        history_type: HistoryType = HistoryType.SHALLOW,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Save current state to history.

        Args:
            region_id: Region/flow identifier
            state: Current state to save
            history_type: Type of history to use
            data: Optional associated data to save
        """
        logger.debug(f"Saving history for region '{region_id}': state='{state}'")

        # Always save shallow
        self._shallow[region_id] = state
        self._data[region_id] = data.copy() if data else {}
        self._interrupted[region_id] = True

        # For deep history, maintain a list
        if history_type == HistoryType.DEEP:
            if region_id not in self._deep:
                self._deep[region_id] = []

            entry = HistoryEntry(
                state=state,
                region_id=region_id,
                data=data.copy() if data else {},
            )
            self._deep[region_id].append(entry)

            # Trim if exceeds max
            if len(self._deep[region_id]) > self.max_deep_history:
                self._deep[region_id] = self._deep[region_id][-self.max_deep_history:]

    def restore(
        self,
        region_id: str,
        history_type: HistoryType = HistoryType.SHALLOW,
        pop: bool = False,
    ) -> Optional[str]:
        """
        Restore state from history.

        Args:
            region_id: Region/flow identifier
            history_type: Type of history to use
            pop: If True, remove the entry from history

        Returns:
            Saved state or None if no history
        """
        if history_type == HistoryType.SHALLOW:
            state = self._shallow.get(region_id)
            if pop and state:
                self._shallow.pop(region_id, None)
                self._interrupted.pop(region_id, None)
            return state

        elif history_type == HistoryType.DEEP:
            entries = self._deep.get(region_id, [])
            if not entries:
                return None

            if pop:
                entry = entries.pop()
            else:
                entry = entries[-1]

            return entry.state

        return None

    def restore_with_data(
        self,
        region_id: str,
        history_type: HistoryType = HistoryType.SHALLOW,
        pop: bool = False,
    ) -> Optional[tuple]:
        """
        Restore state and associated data from history.

        Args:
            region_id: Region/flow identifier
            history_type: Type of history to use
            pop: If True, remove the entry from history

        Returns:
            Tuple of (state, data) or None
        """
        state = self.restore(region_id, history_type, pop)
        if state is None:
            return None

        data = self._data.get(region_id, {})
        if pop:
            self._data.pop(region_id, None)

        return state, data

    def has_history(self, region_id: str) -> bool:
        """Check if region has saved history."""
        return region_id in self._shallow or region_id in self._deep

    def is_interrupted(self, region_id: str) -> bool:
        """Check if region was interrupted."""
        return self._interrupted.get(region_id, False)

    def clear_interrupted(self, region_id: str) -> None:
        """Clear interrupted flag (e.g., after successful resume)."""
        self._interrupted.pop(region_id, None)

    def get_deep_history(self, region_id: str) -> List[HistoryEntry]:
        """Get full deep history for a region."""
        return self._deep.get(region_id, []).copy()

    def get_history_depth(self, region_id: str) -> int:
        """Get depth of history for a region."""
        return len(self._deep.get(region_id, []))

    def clear_region(self, region_id: str) -> None:
        """Clear all history for a region."""
        self._shallow.pop(region_id, None)
        self._deep.pop(region_id, None)
        self._data.pop(region_id, None)
        self._interrupted.pop(region_id, None)
        logger.debug(f"Cleared history for region '{region_id}'")

    def clear_all(self) -> None:
        """Clear all history."""
        self._shallow.clear()
        self._deep.clear()
        self._data.clear()
        self._interrupted.clear()

    def get_all_interrupted_regions(self) -> List[str]:
        """Get list of all interrupted regions."""
        return [r for r, v in self._interrupted.items() if v]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for persistence."""
        return {
            "shallow": self._shallow.copy(),
            "deep": {
                region_id: [e.to_dict() for e in entries]
                for region_id, entries in self._deep.items()
            },
            "data": {k: v.copy() for k, v in self._data.items()},
            "interrupted": self._interrupted.copy(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HistoryManager":
        """Deserialize from dict."""
        manager = cls()
        manager._shallow = data.get("shallow", {}).copy()
        manager._deep = {
            region_id: [HistoryEntry.from_dict(e) for e in entries]
            for region_id, entries in data.get("deep", {}).items()
        }
        manager._data = {k: v.copy() for k, v in data.get("data", {}).items()}
        manager._interrupted = data.get("interrupted", {}).copy()
        return manager


class ConversationFlowTracker:
    """
    Track flow of conversation with support for interruptions.

    Higher-level abstraction that combines history management
    with flow tracking for natural conversation interruptions.
    """

    def __init__(self):
        self.history = HistoryManager()
        self.current_flow: Optional[str] = None
        self.flow_stack: List[str] = []

    def start_flow(self, flow_id: str, initial_state: str) -> None:
        """Start a new flow."""
        if self.current_flow:
            # Save current flow before starting new one
            self.flow_stack.append(self.current_flow)

        self.current_flow = flow_id
        logger.debug(f"Started flow '{flow_id}' at state '{initial_state}'")

    def interrupt_flow(
        self,
        state: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Interrupt current flow (e.g., user asks unrelated question).

        Saves current state to history for later resume.
        """
        if self.current_flow:
            self.history.save(
                self.current_flow,
                state,
                HistoryType.SHALLOW,
                data,
            )
            logger.debug(f"Interrupted flow '{self.current_flow}' at state '{state}'")

    def resume_flow(self) -> Optional[tuple]:
        """
        Resume interrupted flow.

        Returns:
            Tuple of (flow_id, state, data) or None
        """
        if self.current_flow and self.history.is_interrupted(self.current_flow):
            result = self.history.restore_with_data(
                self.current_flow,
                HistoryType.SHALLOW,
            )
            if result:
                state, data = result
                self.history.clear_interrupted(self.current_flow)
                logger.debug(
                    f"Resumed flow '{self.current_flow}' at state '{state}'"
                )
                return self.current_flow, state, data

        return None

    def pop_flow(self) -> Optional[str]:
        """
        Return to previous flow (from flow_stack).

        Returns:
            Previous flow_id or None
        """
        if self.flow_stack:
            previous = self.flow_stack.pop()
            self.current_flow = previous
            return previous
        return None

    def complete_flow(self) -> None:
        """Mark current flow as complete."""
        if self.current_flow:
            self.history.clear_region(self.current_flow)
            logger.debug(f"Completed flow '{self.current_flow}'")

        # Return to previous flow if any
        self.pop_flow()
