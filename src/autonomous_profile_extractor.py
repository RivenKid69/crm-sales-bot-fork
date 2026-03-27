from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from pydantic import BaseModel, Field

from src.dialog_transcript import DialogTranscript
from src.logger import logger


AUTONOMOUS_PROFILE_FIELDS: tuple[str, ...] = (
    "contact_name",
    "business_type",
    "city",
    "automation_before",
)


class AutonomousProfileSnapshot(BaseModel):
    contact_name: Optional[str] = Field(
        default=None,
        description="Имя клиента, только если клиент сам его сообщил.",
    )
    business_type: Optional[str] = Field(
        default=None,
        description="Тип бизнеса клиента, если он явно понятен из сообщений клиента.",
    )
    city: Optional[str] = Field(
        default=None,
        description="Город клиента, если он явно упомянут клиентом.",
    )
    automation_before: Optional[bool] = Field(
        default=None,
        description=(
            "true если клиент уже использует или использовал систему/автоматизацию; "
            "false если клиент явно сказал, что этого нет; null если данных недостаточно."
        ),
    )


class AutonomousProfileExtractor:
    def __init__(self, llm: Any) -> None:
        self._llm = llm

    def extract(
        self,
        history: Sequence[Dict[str, Any]],
    ) -> Optional[AutonomousProfileSnapshot]:
        prompt = self._build_prompt(history)

        try:
            try:
                raw = self._llm.generate_structured(
                    prompt,
                    AutonomousProfileSnapshot,
                    allow_fallback=False,
                    purpose="autonomous_profile_snapshot",
                    temperature=0.0,
                    num_predict=160,
                )
            except TypeError:
                raw = self._llm.generate_structured(prompt, AutonomousProfileSnapshot)
        except Exception as exc:
            logger.warning(
                "autonomous profile extractor llm call failed",
                error=str(exc),
            )
            return None

        try:
            if raw is None:
                return None
            if isinstance(raw, AutonomousProfileSnapshot):
                return raw
            return AutonomousProfileSnapshot.model_validate(raw)
        except Exception as exc:
            logger.warning(
                "autonomous profile extractor validation failed",
                error=str(exc),
            )
            return None

    def _build_prompt(self, history: Sequence[Dict[str, Any]]) -> str:
        rendered_history = DialogTranscript._render_legacy_history(
            list(history or []),
            log_consumer="autonomous_profile_snapshot",
        )
        return (
            "Ты извлекаешь профиль клиента для автономного sales pipeline.\n"
            "Ниже дана полная история диалога в формате:\n"
            "Клиент: ...\n"
            "Вы: ...\n\n"
            "Правила извлечения:\n"
            "1. Используй только строки с префиксом 'Клиент:' как доказательство.\n"
            "2. Строки с префиксом 'Вы:' переданы только для контекста и должны быть полностью "
            "проигнорированы как источник данных.\n"
            "3. Заполняй только 4 поля схемы: contact_name, business_type, city, automation_before.\n"
            "4. Если данных недостаточно или есть сомнение, верни null для поля.\n"
            "5. automation_before=true, если клиент ясно говорит, что уже использует или использовал "
            "систему/автоматизацию/кассовое ПО/CRM/учетную систему. "
            "Примеры: 'у нас сейчас UMAG стоит', 'работаем в 1С'.\n"
            "6. automation_before=false, только если клиент явно говорит, что ничего такого нет.\n"
            "7. Не придумывай и не переноси данные из слов бота.\n\n"
            "История диалога:\n"
            f"{rendered_history}\n"
        )

    @staticmethod
    def non_empty_payload(snapshot: AutonomousProfileSnapshot) -> Dict[str, Any]:
        payload = snapshot.model_dump()
        return {
            key: value
            for key, value in payload.items()
            if value not in (None, "", [], {})
        }
