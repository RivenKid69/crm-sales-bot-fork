"""
DAG State Machine Models.

Базовые модели данных для поддержки DAG (Directed Acyclic Graph)
переходов в стейт-машине.

Поддерживает:
- CHOICE: условное ветвление (XOR - только один путь)
- FORK: параллельное выполнение нескольких веток
- JOIN: точка слияния параллельных веток
- PARALLEL: compound state с параллельными регионами

Вдохновлено:
- XState (parallel states, history)
- AWS Step Functions (Choice, Parallel, Map)
- Temporal (durable execution, event sourcing)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
from enum import Enum
import time


class NodeType(Enum):
    """Типы узлов DAG."""
    SIMPLE = "simple"       # Обычное состояние (текущее поведение)
    CHOICE = "choice"       # Условное ветвление (XOR - один путь)
    FORK = "fork"           # Точка разветвления (1 → N)
    JOIN = "join"           # Точка слияния (N → 1)
    PARALLEL = "parallel"   # Параллельный регион (compound state)


class BranchStatus(Enum):
    """Статус ветки в параллельном выполнении."""
    PENDING = "pending"       # Ещё не начата
    ACTIVE = "active"         # В процессе выполнения
    COMPLETED = "completed"   # Успешно завершена
    SKIPPED = "skipped"       # Пропущена (условие не выполнено)
    FAILED = "failed"         # Завершена с ошибкой


class JoinCondition(Enum):
    """Условия для JOIN узла."""
    ALL_COMPLETE = "all_complete"   # Все ветки должны завершиться
    ANY_COMPLETE = "any_complete"   # Достаточно одной
    MAJORITY = "majority"           # Больше половины
    N_OF_M = "n_of_m"              # N из M веток


class HistoryType(Enum):
    """Типы history states для прерванных диалогов."""
    NONE = "none"           # Без истории
    SHALLOW = "shallow"     # Только последнее состояние
    DEEP = "deep"           # Полная история вложенных состояний


@dataclass
class DAGBranch:
    """
    Ветка в параллельном выполнении (FORK/JOIN).

    Представляет одну из параллельных веток, отслеживает её состояние
    и собранные в ней данные.

    Attributes:
        branch_id: Уникальный идентификатор ветки
        start_state: Начальное состояние ветки
        current_state: Текущее состояние (None если не начата)
        status: Статус выполнения ветки
        collected_data: Данные, собранные в этой ветке
        result: Результат выполнения ветки (при завершении)
        created_at: Время создания ветки
        completed_at: Время завершения (None если не завершена)
    """
    branch_id: str
    start_state: str
    current_state: Optional[str] = None
    status: BranchStatus = BranchStatus.PENDING
    collected_data: Dict[str, Any] = field(default_factory=dict)
    result: Optional[Any] = None
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None

    def activate(self) -> None:
        """Активировать ветку."""
        self.status = BranchStatus.ACTIVE
        self.current_state = self.start_state

    def complete(self, result: Any = None) -> None:
        """Завершить ветку успешно."""
        self.status = BranchStatus.COMPLETED
        self.result = result
        self.completed_at = time.time()

    def skip(self) -> None:
        """Пропустить ветку."""
        self.status = BranchStatus.SKIPPED
        self.completed_at = time.time()

    def fail(self, error: Any = None) -> None:
        """Завершить ветку с ошибкой."""
        self.status = BranchStatus.FAILED
        self.result = error
        self.completed_at = time.time()

    @property
    def is_terminal(self) -> bool:
        """Ветка в терминальном состоянии (завершена/пропущена/ошибка)."""
        return self.status in (
            BranchStatus.COMPLETED,
            BranchStatus.SKIPPED,
            BranchStatus.FAILED,
        )

    @property
    def duration_ms(self) -> Optional[float]:
        """Длительность выполнения в миллисекундах."""
        if self.completed_at:
            return (self.completed_at - self.created_at) * 1000
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Сериализация в словарь."""
        return {
            "branch_id": self.branch_id,
            "start_state": self.start_state,
            "current_state": self.current_state,
            "status": self.status.value,
            "collected_data": self.collected_data,
            "result": self.result,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DAGBranch":
        """Десериализация из словаря."""
        return cls(
            branch_id=data["branch_id"],
            start_state=data["start_state"],
            current_state=data.get("current_state"),
            status=BranchStatus(data.get("status", "pending")),
            collected_data=data.get("collected_data", {}),
            result=data.get("result"),
            created_at=data.get("created_at", time.time()),
            completed_at=data.get("completed_at"),
        )


@dataclass
class DAGEvent:
    """
    Событие в DAG execution (для event sourcing).

    Каждое событие записывается в лог для:
    - Отладки и трассировки
    - Replay диалога
    - Аналитики

    Attributes:
        event_type: Тип события
        node_id: ID узла, в котором произошло событие
        timestamp: Время события
        data: Дополнительные данные события
    """
    event_type: str
    node_id: str
    timestamp: float = field(default_factory=time.time)
    data: Dict[str, Any] = field(default_factory=dict)

    # Типы событий
    CHOICE_EVALUATED = "CHOICE_EVALUATED"
    CHOICE_TAKEN = "CHOICE_TAKEN"
    CHOICE_DEFAULT = "CHOICE_DEFAULT"
    FORK_STARTED = "FORK_STARTED"
    BRANCH_ACTIVATED = "BRANCH_ACTIVATED"
    BRANCH_COMPLETED = "BRANCH_COMPLETED"
    BRANCH_SKIPPED = "BRANCH_SKIPPED"
    JOIN_WAITING = "JOIN_WAITING"
    JOIN_COMPLETE = "JOIN_COMPLETE"
    TRANSITION = "TRANSITION"
    HISTORY_SAVED = "HISTORY_SAVED"
    HISTORY_RESTORED = "HISTORY_RESTORED"

    def to_dict(self) -> Dict[str, Any]:
        """Сериализация в словарь."""
        return {
            "event_type": self.event_type,
            "node_id": self.node_id,
            "timestamp": self.timestamp,
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DAGEvent":
        """Десериализация из словаря."""
        return cls(
            event_type=data["event_type"],
            node_id=data["node_id"],
            timestamp=data.get("timestamp", time.time()),
            data=data.get("data", {}),
        )


@dataclass
class DAGExecutionContext:
    """
    Контекст выполнения DAG.

    Хранит состояние DAG execution:
    - Активные и завершённые ветки
    - Стек fork'ов (для вложенных параллельных регионов)
    - История состояний (для прерванных диалогов)
    - Лог событий (event sourcing)

    Attributes:
        primary_state: Основное состояние (backward compat с single-state model)
        active_branches: Активные параллельные ветки
        completed_branches: Завершённые ветки
        fork_stack: Стек активных fork'ов (для вложенности)
        history: История состояний по регионам
        events: Лог событий
        metadata: Дополнительные метаданные
    """
    primary_state: str
    active_branches: Dict[str, DAGBranch] = field(default_factory=dict)
    completed_branches: Dict[str, DAGBranch] = field(default_factory=dict)
    fork_stack: List[str] = field(default_factory=list)
    history: Dict[str, str] = field(default_factory=dict)
    deep_history: Dict[str, List[str]] = field(default_factory=dict)
    events: List[DAGEvent] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_dag_mode(self) -> bool:
        """Активен ли DAG режим (есть активные ветки или fork'и)."""
        return len(self.active_branches) > 0 or len(self.fork_stack) > 0

    @property
    def all_branches_complete(self) -> bool:
        """Все ли активные ветки завершены."""
        if not self.active_branches:
            return True
        return all(
            branch.is_terminal
            for branch in self.active_branches.values()
        )

    @property
    def active_branch_ids(self) -> List[str]:
        """Список ID активных (не завершённых) веток."""
        return [
            b_id for b_id, branch in self.active_branches.items()
            if branch.status == BranchStatus.ACTIVE
        ]

    @property
    def current_fork(self) -> Optional[str]:
        """Текущий активный fork (верхний в стеке)."""
        return self.fork_stack[-1] if self.fork_stack else None

    def add_event(
        self,
        event_type: str,
        node_id: str,
        **data: Any,
    ) -> DAGEvent:
        """Добавить событие в лог."""
        event = DAGEvent(
            event_type=event_type,
            node_id=node_id,
            data=data,
        )
        self.events.append(event)
        return event

    def start_fork(self, fork_id: str, branches: Dict[str, DAGBranch]) -> None:
        """Начать fork с указанными ветками."""
        self.fork_stack.append(fork_id)
        self.active_branches.update(branches)
        self.add_event(
            DAGEvent.FORK_STARTED,
            fork_id,
            branches=list(branches.keys()),
        )

    def complete_fork(self, fork_id: str) -> Dict[str, DAGBranch]:
        """
        Завершить fork и вернуть завершённые ветки.

        Returns:
            Dict с завершёнными ветками
        """
        if fork_id in self.fork_stack:
            self.fork_stack.remove(fork_id)

        # Переместить ветки в completed
        completed = {}
        to_remove = []
        for b_id, branch in self.active_branches.items():
            if branch.is_terminal:
                completed[b_id] = branch
                self.completed_branches[b_id] = branch
                to_remove.append(b_id)

        for b_id in to_remove:
            del self.active_branches[b_id]

        return completed

    def save_history(
        self,
        region_id: str,
        state: str,
        history_type: HistoryType = HistoryType.SHALLOW,
    ) -> None:
        """Сохранить состояние в историю."""
        self.history[region_id] = state

        if history_type == HistoryType.DEEP:
            if region_id not in self.deep_history:
                self.deep_history[region_id] = []
            self.deep_history[region_id].append(state)

        self.add_event(
            DAGEvent.HISTORY_SAVED,
            region_id,
            state=state,
            history_type=history_type.value,
        )

    def restore_history(
        self,
        region_id: str,
        history_type: HistoryType = HistoryType.SHALLOW,
    ) -> Optional[str]:
        """Восстановить состояние из истории."""
        if history_type == HistoryType.SHALLOW:
            state = self.history.get(region_id)
        elif history_type == HistoryType.DEEP:
            states = self.deep_history.get(region_id, [])
            state = states[-1] if states else None
        else:
            state = None

        if state:
            self.add_event(
                DAGEvent.HISTORY_RESTORED,
                region_id,
                state=state,
                history_type=history_type.value,
            )

        return state

    def get_branch(self, branch_id: str) -> Optional[DAGBranch]:
        """Получить ветку по ID (активную или завершённую)."""
        return (
            self.active_branches.get(branch_id) or
            self.completed_branches.get(branch_id)
        )

    def get_branch_state(self, branch_id: str) -> Optional[str]:
        """Получить текущее состояние ветки."""
        branch = self.get_branch(branch_id)
        return branch.current_state if branch else None

    def update_branch_state(self, branch_id: str, new_state: str) -> bool:
        """Обновить состояние ветки."""
        branch = self.active_branches.get(branch_id)
        if branch:
            old_state = branch.current_state
            branch.current_state = new_state
            self.add_event(
                DAGEvent.TRANSITION,
                branch_id,
                from_state=old_state,
                to_state=new_state,
            )
            return True
        return False

    def update_branch_data(self, branch_id: str, data: Dict[str, Any]) -> bool:
        """Обновить собранные данные ветки."""
        branch = self.active_branches.get(branch_id)
        if branch:
            branch.collected_data.update(data)
            return True
        return False

    def complete_branch(self, branch_id: str, result: Any = None) -> bool:
        """Отметить ветку как завершённую."""
        branch = self.active_branches.get(branch_id)
        if branch:
            branch.complete(result)
            self.add_event(
                DAGEvent.BRANCH_COMPLETED,
                branch_id,
                result=result,
            )
            return True
        return False

    def get_aggregated_data(self) -> Dict[str, Dict[str, Any]]:
        """Получить агрегированные данные из всех завершённых веток."""
        result = {}
        for b_id, branch in self.completed_branches.items():
            if branch.status == BranchStatus.COMPLETED:
                result[b_id] = branch.collected_data
        return result

    def reset(self) -> None:
        """Сбросить DAG контекст."""
        self.active_branches.clear()
        self.completed_branches.clear()
        self.fork_stack.clear()
        self.history.clear()
        self.deep_history.clear()
        self.events.clear()

    def to_dict(self) -> Dict[str, Any]:
        """Сериализация в словарь."""
        return {
            "primary_state": self.primary_state,
            "active_branches": {
                k: v.to_dict() for k, v in self.active_branches.items()
            },
            "completed_branches": {
                k: v.to_dict() for k, v in self.completed_branches.items()
            },
            "fork_stack": self.fork_stack.copy(),
            "history": self.history.copy(),
            "deep_history": {k: v.copy() for k, v in self.deep_history.items()},
            "events": [e.to_dict() for e in self.events],
            "metadata": self.metadata.copy(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DAGExecutionContext":
        """Десериализация из словаря."""
        ctx = cls(primary_state=data["primary_state"])

        ctx.active_branches = {
            k: DAGBranch.from_dict(v)
            for k, v in data.get("active_branches", {}).items()
        }
        ctx.completed_branches = {
            k: DAGBranch.from_dict(v)
            for k, v in data.get("completed_branches", {}).items()
        }
        ctx.fork_stack = data.get("fork_stack", []).copy()
        ctx.history = data.get("history", {}).copy()
        ctx.deep_history = {
            k: v.copy() for k, v in data.get("deep_history", {}).items()
        }
        ctx.events = [
            DAGEvent.from_dict(e) for e in data.get("events", [])
        ]
        ctx.metadata = data.get("metadata", {}).copy()

        return ctx


@dataclass
class DAGNodeConfig:
    """
    Конфигурация DAG узла (из YAML).

    Attributes:
        node_id: Уникальный ID узла
        node_type: Тип узла (choice, fork, join, parallel)
        config: Полная конфигурация из YAML
    """
    node_id: str
    node_type: NodeType
    config: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_dag_node(self) -> bool:
        """Является ли узел DAG узлом (не simple)."""
        return self.node_type != NodeType.SIMPLE

    @property
    def goal(self) -> str:
        """Цель узла."""
        return self.config.get("goal", "")

    # CHOICE properties
    @property
    def choices(self) -> List[Dict[str, Any]]:
        """Варианты выбора для CHOICE узла."""
        return self.config.get("choices", [])

    @property
    def default_choice(self) -> Optional[str]:
        """Default путь для CHOICE узла."""
        return self.config.get("default")

    # FORK properties
    @property
    def branches(self) -> List[Dict[str, Any]]:
        """Ветки для FORK узла."""
        return self.config.get("branches", [])

    @property
    def join_at(self) -> Optional[str]:
        """Узел слияния для FORK."""
        return self.config.get("join_at")

    @property
    def join_condition(self) -> JoinCondition:
        """Условие слияния для FORK."""
        cond = self.config.get("join_condition", "all_complete")
        return JoinCondition(cond)

    # JOIN properties
    @property
    def expects_branches(self) -> List[str]:
        """Ожидаемые ветки для JOIN узла."""
        return self.config.get("expects_branches", [])

    @property
    def on_join_action(self) -> Optional[str]:
        """Действие при успешном JOIN."""
        on_join = self.config.get("on_join", {})
        return on_join.get("action") if isinstance(on_join, dict) else None

    # PARALLEL properties
    @property
    def regions(self) -> Dict[str, Dict[str, Any]]:
        """Регионы для PARALLEL узла."""
        return self.config.get("regions", {})

    @property
    def exit_condition(self) -> Optional[Dict[str, Any]]:
        """Условие выхода из PARALLEL."""
        return self.config.get("exit_when")

    # History
    @property
    def history_type(self) -> HistoryType:
        """Тип истории для compound state."""
        hist = self.config.get("history", "none")
        return HistoryType(hist)

    # Transitions (для обычных переходов после DAG)
    @property
    def transitions(self) -> Dict[str, Any]:
        """Переходы из узла."""
        return self.config.get("transitions", {})

    def to_dict(self) -> Dict[str, Any]:
        """Сериализация в словарь."""
        return {
            "node_id": self.node_id,
            "node_type": self.node_type.value,
            "config": self.config,
        }

    @classmethod
    def from_state_config(
        cls,
        state_id: str,
        state_config: Dict[str, Any],
    ) -> "DAGNodeConfig":
        """Создать из конфигурации состояния."""
        type_str = state_config.get("type", "simple")
        try:
            node_type = NodeType(type_str)
        except ValueError:
            node_type = NodeType.SIMPLE

        return cls(
            node_id=state_id,
            node_type=node_type,
            config=state_config,
        )
