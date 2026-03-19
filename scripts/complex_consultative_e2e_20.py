"""
Complex consultative E2E with 20 multi-step scenarios for the autonomous sales bot.

Goal:
- stress-test the real autonomous pipeline on requirement drift and evolving client context
- keep dialogs realistic: the client starts simple, then adds constraints and changes direction
- save both structured results and full dialog transcripts

Recommended launch pattern inside Docker network:
    python -m scripts.complex_consultative_e2e_20 --model qwen3.5:27b
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

import requests


sys.path.insert(0, str(Path(__file__).parent.parent))


SCENARIOS: List[Dict[str, object]] = [
    {
        "id": "CC01",
        "name": "Simple start, growing complexity",
        "theme": "Клиент хочет быстро и просто, но по ходу добавляет новые требования.",
        "messages": [
            "Мне нужно быстро и просто, без длинного внедрения.",
            "Но ещё надо, чтобы остатки считались нормально и продавцы не путались.",
            "И онлайн-заказы тоже, чтобы сайт не жил отдельно.",
            "И в идеале аналитику по сменам и по продавцам.",
        ],
        "dialog_groups": [
            ["быстр", "прост"],
            ["остат", "учет", "учёт", "продав"],
            ["онлайн", "сайт", "интернет"],
            ["аналит", "смен", "продав"],
        ],
        "dialog_groups_min": 3,
        "final_groups": [
            ["аналит", "отчет", "отчёт", "смен", "продав"],
            ["еди", "объедин", "система", "решени"],
        ],
    },
    {
        "id": "CC02",
        "name": "Wrong self-diagnosis, full rethink",
        "theme": "Клиент сначала уверен в решении, потом понимает, что ошибка глубже.",
        "messages": [
            "Я думал, мне просто нужен новый терминал и всё.",
            "Но, похоже, проблема глубже: по остаткам бардак и продажи не бьются.",
            "Сейчас я уже не уверен, что железо вообще главное.",
            "Если пересматривать подход, с чего правильно начать?",
        ],
        "dialog_groups": [
            ["терминал", "оборуд"],
            ["остат", "продаж"],
            ["подход", "система", "учет", "учёт"],
        ],
        "dialog_groups_min": 2,
        "final_groups": [
            ["нача", "этап", "сначала", "перв"],
            ["система", "учет", "учёт", "решени"],
        ],
    },
    {
        "id": "CC03",
        "name": "From hardware to replacement decision",
        "theme": "Клиент с оборудования переходит к программе, функциям и полной замене текущей системы.",
        "messages": [
            "Сначала хотел узнать только по оборудованию.",
            "Потом понял, что без программы, наверное, смысла нет?",
            "Если программу ставить, то что там по функциям для магазина?",
            "И ещё у нас текущая система постоянно ломается.",
            "Получается, можно всё это заменить одним решением?",
        ],
        "dialog_groups": [
            ["оборуд"],
            ["програм"],
            ["функц", "учет", "учёт", "аналит"],
            ["замен", "текущ", "систем"],
        ],
        "dialog_groups_min": 3,
        "final_groups": [
            ["замен", "еди", "комплекс"],
            ["оборуд", "програм", "решени"],
        ],
    },
    {
        "id": "CC04",
        "name": "Offline plus online plus price",
        "theme": "Магазин, онлайн-продажи, объединение, оборудование и возврат к цене.",
        "messages": [
            "Мне нужно для магазина.",
            "Хотя у меня ещё онлайн-продажи есть.",
            "Это всё можно объединить в одном месте?",
            "И какое оборудование тогда вообще нужно?",
            "Ладно, и сколько это примерно будет стоить?",
        ],
        "dialog_groups": [
            ["магазин", "розниц"],
            ["онлайн", "сайт", "интернет"],
            ["объедин", "еди"],
            ["оборуд"],
            ["цен", "стоим", "тариф"],
        ],
        "dialog_groups_min": 4,
        "final_groups": [
            ["цен", "стоим", "тариф"],
            ["объедин", "еди", "комплекс"],
        ],
    },
    {
        "id": "CC05",
        "name": "Safe replacement under penalty anxiety",
        "theme": "Клиент боится рисков и штрафов, просит безопасное решение.",
        "messages": [
            "Мне нужна касса.",
            "Но у меня уже есть какая-то программа.",
            "Судя по всему, она не закрывает требования нормально.",
            "Я уже переживаю из-за рисков и штрафов.",
            "Подберите мне безопасное решение, чтобы потом не переделывать.",
        ],
        "dialog_groups": [
            ["касс"],
            ["програм"],
            ["рис", "штраф", "безопас"],
        ],
        "dialog_groups_min": 3,
        "final_groups": [
            ["безопас", "штраф", "соответ"],
            ["решени", "подоб", "вариант"],
        ],
    },
    {
        "id": "CC06",
        "name": "Dry start, engaged finish",
        "theme": "Клиент сначала отвечает сухо, затем начинает раскрываться и просит рекомендацию.",
        "messages": [
            "Нужна касса.",
            "Для маленькой точки.",
            "А если потом станет две точки и склад?",
            "И чтобы отчёты нормальные были.",
            "Окей, уже подробнее: что конкретно мне лучше взять?",
        ],
        "dialog_groups": [
            ["касс"],
            ["точ", "склад", "несколько"],
            ["отчет", "отчёт", "аналит"],
        ],
        "dialog_groups_min": 3,
        "final_groups": [
            ["лучше", "подойд", "рекоменд", "вариант"],
            ["касс", "склад", "точ"],
        ],
    },
    {
        "id": "CC07",
        "name": "One request, several hidden problems",
        "theme": "Один запрос постепенно раскрывается как комплексная задача.",
        "messages": [
            "Нужно просто, чтобы продажи проходили без хаоса.",
            "Но ещё сотрудники постоянно путают остатки.",
            "Доставки мы вообще ведём в таблицах.",
            "И мне нужно видеть всё по точке и по сотрудникам.",
            "Похоже, вопрос уже не в кассе, а в комплексном решении?",
        ],
        "dialog_groups": [
            ["продаж"],
            ["остат"],
            ["достав"],
            ["сотруд", "аналит", "вид"],
        ],
        "dialog_groups_min": 4,
        "final_groups": [
            ["комплекс", "еди", "система"],
            ["продаж", "остат", "достав"],
        ],
    },
    {
        "id": "CC08",
        "name": "Like a friend, but unclear",
        "theme": "Клиент хочет как у знакомого, но сам не может сформулировать требования.",
        "messages": [
            "Мне нужно как у знакомого, у него всё удобно.",
            "Но я толком не могу объяснить, что именно у него настроено.",
            "Там вроде и остатки видно, и касса простая, и отчёты понятные.",
            "Поможете перевести это в нормальные требования?",
        ],
        "dialog_groups": [
            ["остат"],
            ["касс"],
            ["отчет", "отчёт"],
            ["требован", "подоб", "решен"],
        ],
        "dialog_groups_min": 3,
        "final_groups": [
            ["требован", "какие", "нужно", "важно"],
            ["подоб", "вариант", "решени"],
        ],
    },
    {
        "id": "CC09",
        "name": "Possibilities, limits, risks, catch",
        "theme": "Клиент хочет понять не только возможности, но и ограничения с рисками.",
        "messages": [
            "Сначала расскажите, что у вас вообще можно делать.",
            "Теперь честно: а какие ограничения есть?",
            "И какие риски, если взять систему и потом упереться в эти ограничения?",
            "Короче, где подвох?",
        ],
        "dialog_groups": [
            ["можно", "функц", "возмож"],
            ["огранич"],
            ["рис", "подвох"],
        ],
        "dialog_groups_min": 3,
        "final_groups": [
            ["огранич", "честно", "важно"],
            ["рис", "подходит", "сценар"],
        ],
    },
    {
        "id": "CC10",
        "name": "Act versus do nothing",
        "theme": "Клиент сравнивает сценарии изменений и бездействия.",
        "messages": [
            "Я не уверен, что мне вообще нужно что-то менять.",
            "Если взять систему, один сценарий.",
            "Если ничего не делать, другой сценарий.",
            "Как лучше именно в моём случае?",
        ],
        "dialog_groups": [
            ["менять", "система"],
            ["ничего не делать", "без системы", "остав"],
            ["лучше", "в вашем случае", "для вас"],
        ],
        "dialog_groups_min": 2,
        "final_groups": [
            ["для вас", "в вашем случае", "лучше", "рекоменд"],
            ["менять", "остав", "этап"],
        ],
    },
    {
        "id": "CC11",
        "name": "Functions, reliability, price, arguments",
        "theme": "Клиент сравнивает функции, стабильность и цену, просит аргументы.",
        "messages": [
            "Я смотрю варианты.",
            "Какие функции у вас реально сильные для розницы?",
            "А у вас это точно работает без сбоев?",
            "Теперь возвращаюсь к цене.",
            "Дайте аргументы, почему это имеет смысл брать.",
        ],
        "dialog_groups": [
            ["функц", "розниц"],
            ["сбо", "стабил", "надеж"],
            ["цен", "стоим"],
            ["аргумент", "выгод", "смысл"],
        ],
        "dialog_groups_min": 4,
        "final_groups": [
            ["аргумент", "выгод", "окуп", "смысл"],
            ["цен", "тариф", "стоим"],
        ],
    },
    {
        "id": "CC12",
        "name": "Everything freezes, replace all?",
        "theme": "Клиент раздражён из-за зависаний и хочет понять, спасёт ли полная замена.",
        "messages": [
            "У меня всё зависает.",
            "Похоже, часть проблемы в оборудовании.",
            "Но и сама система работает неровно.",
            "Я уже раздражён, если честно.",
            "Если всё поменять целиком, будет нормально работать?",
        ],
        "dialog_groups": [
            ["завис", "тормоз", "сбо"],
            ["оборуд"],
            ["систем"],
            ["замен", "целиком"],
        ],
        "dialog_groups_min": 3,
        "final_groups": [
            ["замен", "диагност", "комплекс"],
            ["оборуд", "систем"],
        ],
    },
    {
        "id": "CC13",
        "name": "Deep consultation without immediate decision",
        "theme": "Клиент уходит в детали, не готов решать сразу, но хочет понятный следующий шаг.",
        "messages": [
            "Мне нужна консультация, но я пока не готов решать.",
            "Расскажите, как это обычно внедряется.",
            "А обучение сотрудников у вас как проходит?",
            "А интеграции с моими сервисами потом отдельно обсуждаются?",
            "Я сейчас всё равно не решусь, но хочу понять, какой следующий шаг без давления.",
        ],
        "dialog_groups": [
            ["внедр"],
            ["обуч"],
            ["интеграц"],
            ["следующ", "без давления", "этап"],
        ],
        "dialog_groups_min": 4,
        "final_groups": [
            ["следующ", "этап", "без давления", "можно начать"],
            ["внедр", "обуч", "интеграц"],
        ],
    },
    {
        "id": "CC14",
        "name": "Expensive, explain value, fit budget",
        "theme": "Клиент упирается в цену, просит расшифровать ценность и вариант под бюджет.",
        "messages": [
            "Сколько стоит?",
            "Если честно, дорого.",
            "Объясните, за что я вообще плачу.",
            "И дайте вариант под мой бюджет.",
        ],
        "dialog_groups": [
            ["цен", "стоим", "дорог"],
            ["за что", "ценност", "плат"],
            ["бюджет", "вариант"],
        ],
        "dialog_groups_min": 3,
        "final_groups": [
            ["бюджет", "вариант", "тариф"],
            ["ценност", "за что", "получ"],
        ],
    },
    {
        "id": "CC15",
        "name": "Chain management and analytics",
        "theme": "Сеть магазинов, единый контроль, аналитика и цена.",
        "messages": [
            "У меня сеть магазинов.",
            "Можно ли всё контролировать в одном месте?",
            "Что у вас с аналитикой по точкам?",
            "И по деньгам как это считается?",
        ],
        "dialog_groups": [
            ["сеть", "точк"],
            ["контрол", "одном месте", "еди"],
            ["аналит"],
            ["деньг", "цен", "стоим"],
        ],
        "dialog_groups_min": 4,
        "final_groups": [
            ["еди", "контрол", "аналит"],
            ["цен", "тариф", "стоим"],
        ],
    },
    {
        "id": "CC16",
        "name": "Knows nothing, wants full kit",
        "theme": "Клиент задаёт базовые вопросы и просит полный комплект под себя.",
        "messages": [
            "Я вообще ничего не понимаю.",
            "Что мне вообще нужно в самом начале?",
            "Касса, программа и оборудование — это всё отдельно или вместе?",
            "А как понять, что брать именно мне?",
            "Помогите подобрать полный комплект.",
        ],
        "dialog_groups": [
            ["что нужно", "сначала"],
            ["касс"],
            ["програм"],
            ["оборуд"],
            ["комплект", "подоб"],
        ],
        "dialog_groups_min": 4,
        "final_groups": [
            ["полный комплект", "комплект", "под ключ"],
            ["касс", "програм", "оборуд"],
        ],
    },
    {
        "id": "CC17",
        "name": "Cash register, taxes 2026, SNR",
        "theme": "Клиент запутан в налогах и СНР, просит подобрать решение под ключ.",
        "messages": [
            "Мне нужна касса.",
            "А что с налогами в 2026 году?",
            "Я запутался в СНР и вообще не понимаю, что мне можно.",
            "Не хочу потом из-за этого переделывать всё.",
            "Подберите решение под ключ с учётом этого.",
        ],
        "dialog_groups": [
            ["касс"],
            ["налог", "2026"],
            ["снр"],
            ["под ключ", "решени"],
        ],
        "dialog_groups_min": 4,
        "final_groups": [
            ["налог", "снр", "режим"],
            ["под ключ", "решени", "вариант"],
        ],
    },
    {
        "id": "CC18",
        "name": "Russian plus Kazakh mixed consultation",
        "theme": "Клиент переходит на смешанный русский и казахский и просит проще объяснить.",
        "messages": [
            "Здравствуйте, мне нужна касса для магазина.",
            "Бірақ түсінікті етіп айтыңызшы, мен техниканы жақсы білмеймін.",
            "Онлайн тапсырыстар да бар, бәрін бірге жүргізуге бола ма?",
            "Бағасы мен бағдарламасы қалай болады?",
            "Қарапайым тілмен, маған қандай шешім дұрыс?",
        ],
        "dialog_groups": [
            ["касс", "дүкен", "магаз"],
            ["онлайн", "тапсырыс", "интернет"],
            ["баға", "цен", "стоим"],
            ["програм", "бағдар"],
            ["қарапайым", "прост"],
        ],
        "dialog_groups_min": 4,
        "final_groups": [
            ["қарапайым", "прост", "түсінікті"],
            ["шешім", "решени", "дұрыс", "подойд"],
        ],
    },
    {
        "id": "CC19",
        "name": "Returns after partner review",
        "theme": "Клиент возвращается после обсуждения с партнёром и добавляет второй набор требований.",
        "messages": [
            "Я с партнером обсужу и потом вернусь.",
            "Вернулся: у него вопрос по оборудованию.",
            "У меня вопрос по программе и учёту.",
            "И он ещё спросил, можно ли потом масштабироваться.",
            "С учётом двух мнений, что вы бы рекомендовали?",
        ],
        "dialog_groups": [
            ["оборуд"],
            ["програм", "учет", "учёт"],
            ["масштаб", "сеть", "расти"],
            ["рекоменд", "для вас"],
        ],
        "dialog_groups_min": 4,
        "final_groups": [
            ["рекоменд", "для вас", "лучше"],
            ["оборуд", "програм", "масштаб"],
        ],
    },
    {
        "id": "CC20",
        "name": "Open business from scratch, knowledge stress",
        "theme": "Клиент открывает бизнес с нуля и проверяет знания по запуску, налогам, интеграциям и ограничениям.",
        "messages": [
            "Хочу открыть бизнес с нуля.",
            "Что мне нужно по оборудованию, программе и запуску?",
            "И как это связано с налогами и кассой?",
            "Плюс у меня будут интеграции с маркетплейсами и доставкой.",
            "Скажите честно, какие ограничения есть и что вы бы собрали под ключ?",
        ],
        "dialog_groups": [
            ["открыть бизнес", "с нуля", "запуск"],
            ["оборуд"],
            ["програм"],
            ["налог", "касс"],
            ["интеграц", "маркетплейс", "достав"],
            ["огранич"],
        ],
        "dialog_groups_min": 5,
        "final_groups": [
            ["под ключ", "собрал", "решени"],
            ["огранич", "честно"],
            ["оборуд", "програм", "налог"],
        ],
    },
]

FORBIDDEN_INTERNAL_MARKERS: Sequence[str] = (
    "база знаний",
    "в базе",
    "в бд",
    "по базе",
    "фактах бд",
    "предоставленных данных",
    "уточню у коллег",
    "у коллег",
    "не удалось найти",
    "не могу найти",
    "внутренн",
)

DEFAULT_RECOMMENDATION_GROUP: Sequence[str] = (
    "подойд",
    "рекоменд",
    "лучше",
    "для вас",
    "вариант",
    "решени",
    "под ключ",
    "шешім",
    "дұрыс",
)


@dataclass
class GroupCheck:
    group: List[str]
    matched: List[str]

    @property
    def passed(self) -> bool:
        return bool(self.matched)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def evaluate_groups(
    text: str,
    groups: Sequence[Sequence[str]],
    minimum_required: int | None = None,
) -> Dict[str, object]:
    normalized = normalize_text(text)
    checks: List[GroupCheck] = []

    for group in groups:
        normalized_group = [normalize_text(item) for item in group]
        matched = [item for item in normalized_group if item and item in normalized]
        checks.append(GroupCheck(group=list(normalized_group), matched=matched))

    required = minimum_required if minimum_required is not None else len(checks)
    matched_count = sum(1 for check in checks if check.passed)
    return {
        "passed": matched_count >= required,
        "required": required,
        "matched_count": matched_count,
        "checks": [
            {
                "group": check.group,
                "matched": check.matched,
                "passed": check.passed,
            }
            for check in checks
        ],
    }


def check_live_dependencies(base_url: str, embed_url: str, rerank_url: str) -> Dict[str, Dict[str, object]]:
    endpoints = {
        "ollama": f"{base_url.rstrip('/')}/api/tags",
        "tei_embed": f"{embed_url.rstrip('/')}/health",
        "tei_rerank": f"{rerank_url.rstrip('/')}/health",
    }
    health: Dict[str, Dict[str, object]] = {}
    for name, url in endpoints.items():
        try:
            started = time.time()
            response = requests.get(url, timeout=5)
            try:
                payload: object = response.json()
            except Exception:
                payload = response.text[:200]
            health[name] = {
                "ok": response.status_code == 200,
                "status_code": response.status_code,
                "elapsed_ms": round((time.time() - started) * 1000, 1),
                "url": url,
                "payload": payload,
            }
        except Exception as exc:
            health[name] = {
                "ok": False,
                "status_code": 0,
                "elapsed_ms": None,
                "url": url,
                "payload": str(exc),
            }
    return health


@contextmanager
def patched_settings(
    *,
    model: str | None,
    base_url: str | None,
    embed_url: str | None,
    rerank_url: str | None,
):
    from src.settings import settings

    original = {
        "llm_model": settings.llm.model,
        "llm_base_url": settings.llm.base_url,
        "retriever_embedder_url": settings.retriever.embedder_url,
        "reranker_url": settings.reranker.url,
    }

    if model:
        settings.llm.model = model
    if base_url:
        settings.llm.base_url = base_url
    if embed_url:
        settings.retriever.embedder_url = embed_url
    if rerank_url:
        settings.reranker.url = rerank_url

    try:
        yield settings
    finally:
        settings.llm.model = original["llm_model"]
        settings.llm.base_url = original["llm_base_url"]
        settings.retriever.embedder_url = original["retriever_embedder_url"]
        settings.reranker.url = original["reranker_url"]


@contextmanager
def count_tei_calls(counters: Dict[str, int]):
    import src.knowledge.reranker as reranker_module
    import src.knowledge.tei_client as tei_client_module

    original_embed_texts = tei_client_module.embed_texts
    original_embed_single = tei_client_module.embed_single
    original_embed_cached = tei_client_module.embed_texts_cached
    original_rerank = reranker_module.Reranker.rerank

    def counted_embed_texts(*args, **kwargs):
        counters["embed_calls"] = counters.get("embed_calls", 0) + 1
        return original_embed_texts(*args, **kwargs)

    def counted_embed_single(*args, **kwargs):
        counters["embed_single_calls"] = counters.get("embed_single_calls", 0) + 1
        return original_embed_single(*args, **kwargs)

    def counted_embed_cached(*args, **kwargs):
        counters["embed_cached_calls"] = counters.get("embed_cached_calls", 0) + 1
        return original_embed_cached(*args, **kwargs)

    def counted_rerank(self, *args, **kwargs):
        counters["rerank_calls"] = counters.get("rerank_calls", 0) + 1
        return original_rerank(self, *args, **kwargs)

    tei_client_module.embed_texts = counted_embed_texts
    tei_client_module.embed_single = counted_embed_single
    tei_client_module.embed_texts_cached = counted_embed_cached
    reranker_module.Reranker.rerank = counted_rerank

    try:
        yield
    finally:
        tei_client_module.embed_texts = original_embed_texts
        tei_client_module.embed_single = original_embed_single
        tei_client_module.embed_texts_cached = original_embed_cached
        reranker_module.Reranker.rerank = original_rerank


def run_dialog(bot, scenario: Dict[str, object]) -> Dict[str, object]:
    bot.reset()
    turns: List[Dict[str, object]] = []

    for index, message in enumerate(scenario["messages"], start=1):
        print(f"  U{index}: {message}", flush=True)
        started = time.time()
        result = bot.process(message)
        elapsed_ms = round((time.time() - started) * 1000, 1)
        print(f"  B{index}: {str(result.get('response', '') or '')}", flush=True)
        print(
            "     "
            f"[intent={str(result.get('intent', '') or '')} "
            f"state={str(result.get('state', '') or '')} "
            f"action={str(result.get('action', '') or '')} "
            f"{elapsed_ms}ms]",
            flush=True,
        )
        turns.append(
            {
                "turn": index,
                "user": message,
                "bot": str(result.get("response", "") or ""),
                "intent": str(result.get("intent", "") or ""),
                "state": str(result.get("state", "") or ""),
                "action": str(result.get("action", "") or ""),
                "elapsed_ms": elapsed_ms,
                "is_final": bool(result.get("is_final")),
            }
        )
        if result.get("is_final"):
            break

    return {
        "id": scenario["id"],
        "name": scenario["name"],
        "theme": scenario["theme"],
        "turns": turns,
        "final_response": turns[-1]["bot"] if turns else "",
        "total_turn_time_ms": round(sum(float(turn["elapsed_ms"]) for turn in turns), 1),
        "completed_all_turns": len(turns) == len(scenario["messages"]),
    }


def evaluate_dialog(scenario: Dict[str, object], result: Dict[str, object]) -> Dict[str, object]:
    turns = list(result.get("turns") or [])
    all_bot_text = normalize_text(" ".join(str(turn.get("bot", "")) for turn in turns))
    final_response = normalize_text(result.get("final_response", ""))

    dialog_groups = evaluate_groups(
        all_bot_text,
        scenario.get("dialog_groups", []),
        int(scenario.get("dialog_groups_min", 0)) or None,
    )
    final_groups = evaluate_groups(
        final_response,
        list(scenario.get("final_groups", [])) + [list(DEFAULT_RECOMMENDATION_GROUP)],
        int(scenario.get("final_groups_min", 0)) or None,
    )

    leaked_markers = [marker for marker in FORBIDDEN_INTERNAL_MARKERS if marker in all_bot_text]
    empty_turns = [int(turn["turn"]) for turn in turns if not normalize_text(str(turn.get("bot", "")))]
    short_turns = [
        int(turn["turn"])
        for turn in turns
        if len(normalize_text(str(turn.get("bot", "")))) < 25
    ]

    passed = (
        bool(turns)
        and result.get("completed_all_turns", False)
        and not leaked_markers
        and not empty_turns
        and dialog_groups["passed"]
        and final_groups["passed"]
    )

    return {
        "passed": passed,
        "completed_all_turns": bool(result.get("completed_all_turns", False)),
        "dialog_groups": dialog_groups,
        "final_groups": final_groups,
        "leaked_markers": leaked_markers,
        "empty_turns": empty_turns,
        "short_turns": short_turns,
    }


def render_markdown(
    *,
    settings_snapshot: Dict[str, object],
    health: Dict[str, Dict[str, object]],
    tei_counters: Dict[str, int],
    reports: Iterable[Dict[str, object]],
) -> str:
    items = list(reports)
    passed_count = sum(1 for item in items if item["evaluation"]["passed"])

    lines = [
        "# Complex Consultative E2E 20",
        "",
        f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Stack",
        "",
        f"- llm.model: `{settings_snapshot['llm_model']}`",
        f"- llm.base_url: `{settings_snapshot['llm_base_url']}`",
        f"- retriever.embedder_url: `{settings_snapshot['retriever_embedder_url']}`",
        f"- reranker.url: `{settings_snapshot['reranker_url']}`",
        "",
        "## Health",
        "",
    ]

    for name, payload in health.items():
        lines.append(
            f"- {name}: ok=`{payload.get('ok')}` status=`{payload.get('status_code')}` "
            f"elapsed_ms=`{payload.get('elapsed_ms')}` url=`{payload.get('url')}`"
        )

    lines.extend(
        [
            "",
            "## TEI Counters",
            "",
            f"- embed_calls: `{tei_counters.get('embed_calls', 0)}`",
            f"- embed_single_calls: `{tei_counters.get('embed_single_calls', 0)}`",
            f"- embed_cached_calls: `{tei_counters.get('embed_cached_calls', 0)}`",
            f"- rerank_calls: `{tei_counters.get('rerank_calls', 0)}`",
            "",
            "## Summary",
            "",
            f"- passed: `{passed_count}/{len(items)}`",
            "",
        ]
    )

    for item in items:
        evaluation = item["evaluation"]
        lines.append(f"## {item['id']} — {item['name']}")
        lines.append("")
        lines.append(f"- theme: {item['theme']}")
        lines.append(f"- passed: `{evaluation['passed']}`")
        lines.append(f"- completed_all_turns: `{evaluation['completed_all_turns']}`")
        lines.append(
            f"- dialog_groups: `{evaluation['dialog_groups']['matched_count']}/{len(evaluation['dialog_groups']['checks'])}`"
        )
        lines.append(
            f"- final_groups: `{evaluation['final_groups']['matched_count']}/{len(evaluation['final_groups']['checks'])}`"
        )
        lines.append(f"- leaked_markers: `{', '.join(evaluation['leaked_markers']) or 'none'}`")
        lines.append(f"- empty_turns: `{evaluation['empty_turns'] or 'none'}`")
        lines.append(f"- short_turns: `{evaluation['short_turns'] or 'none'}`")
        lines.append(f"- dialog total_turn_time_ms: `{item['total_turn_time_ms']}`")
        lines.append("")
        for turn in item["turns"]:
            lines.append(f"U{turn['turn']}: {turn['user']}")
            lines.append(f"B{turn['turn']}: {turn['bot']}")
            lines.append(
                "   "
                f"action=`{turn['action']}` intent=`{turn['intent']}` state=`{turn['state']}` "
                f"elapsed_ms=`{turn['elapsed_ms']}`"
            )
        lines.append("")

    return "\n".join(lines)


def select_scenarios(items: Sequence[Dict[str, object]], only_ids: str | None) -> List[Dict[str, object]]:
    if not only_ids:
        return list(items)
    wanted = {part.strip().upper() for part in only_ids.split(",") if part.strip()}
    return [item for item in items if str(item["id"]).upper() in wanted]


def save_report_files(
    *,
    output_dir: Path,
    stem: str,
    payload: Dict[str, object],
    markdown: str,
) -> Dict[str, Path]:
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"
    latest_json = output_dir / "complex_consultative_e2e_20_latest.json"
    latest_md = output_dir / "complex_consultative_e2e_20_latest.md"

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    latest_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    latest_md.write_text(markdown, encoding="utf-8")
    return {
        "json_path": json_path,
        "md_path": md_path,
        "latest_json": latest_json,
        "latest_md": latest_md,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--embed-url", default=None)
    parser.add_argument("--rerank-url", default=None)
    parser.add_argument("--ids", default=None, help="Comma-separated scenario ids, for example CC01,CC02")
    parser.add_argument("--output-dir", default="results")
    args = parser.parse_args()

    selected_scenarios = select_scenarios(SCENARIOS, args.ids)
    if not selected_scenarios:
        raise SystemExit("No scenarios selected")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = f"complex_consultative_e2e_20_{timestamp}"

    with patched_settings(
        model=args.model,
        base_url=args.base_url,
        embed_url=args.embed_url,
        rerank_url=args.rerank_url,
    ) as settings:
        health = check_live_dependencies(
            settings.llm.base_url,
            settings.retriever.embedder_url,
            settings.reranker.url,
        )
        if not all(item.get("ok") for item in health.values()):
            print(json.dumps(health, ensure_ascii=False, indent=2))
            raise SystemExit("Live dependencies are not healthy")

        from src.bot import SalesBot, setup_autonomous_pipeline
        from src.llm import OllamaLLM

        tei_counters: Dict[str, int] = {}
        reports: List[Dict[str, object]] = []

        with count_tei_calls(tei_counters):
            setup_autonomous_pipeline()
            llm = OllamaLLM(model=settings.llm.model, base_url=settings.llm.base_url)
            bot = SalesBot(llm=llm, flow_name="autonomous", enable_tracing=True)

            for index, scenario in enumerate(selected_scenarios, start=1):
                print(f"[{index}/{len(selected_scenarios)}] {scenario['id']} — {scenario['name']}", flush=True)
                result = run_dialog(bot, scenario)
                evaluation = evaluate_dialog(scenario, result)
                reports.append(
                    {
                        **result,
                        "evaluation": evaluation,
                    }
                )
                print(
                    f"  passed={evaluation['passed']} turns={len(result['turns'])} "
                    f"dialog_groups={evaluation['dialog_groups']['matched_count']}/"
                    f"{len(evaluation['dialog_groups']['checks'])} "
                    f"final_groups={evaluation['final_groups']['matched_count']}/"
                    f"{len(evaluation['final_groups']['checks'])}",
                    flush=True,
                )

                settings_snapshot = {
                    "llm_model": settings.llm.model,
                    "llm_base_url": settings.llm.base_url,
                    "retriever_embedder_url": settings.retriever.embedder_url,
                    "reranker_url": settings.reranker.url,
                }
                payload = {
                    "generated_at": datetime.now().isoformat(),
                    "scenario_count": len(selected_scenarios),
                    "settings_snapshot": settings_snapshot,
                    "health": health,
                    "tei_counters": tei_counters,
                    "reports": reports,
                }
                markdown = render_markdown(
                    settings_snapshot=settings_snapshot,
                    health=health,
                    tei_counters=tei_counters,
                    reports=reports,
                )
                save_report_files(
                    output_dir=output_dir,
                    stem=stem,
                    payload=payload,
                    markdown=markdown,
                )

        settings_snapshot = {
            "llm_model": settings.llm.model,
            "llm_base_url": settings.llm.base_url,
            "retriever_embedder_url": settings.retriever.embedder_url,
            "reranker_url": settings.reranker.url,
        }

    payload = {
        "generated_at": datetime.now().isoformat(),
        "scenario_count": len(selected_scenarios),
        "settings_snapshot": settings_snapshot,
        "health": health,
        "tei_counters": tei_counters,
        "reports": reports,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown = render_markdown(
        settings_snapshot=settings_snapshot,
        health=health,
        tei_counters=tei_counters,
        reports=reports,
    )
    paths = save_report_files(
        output_dir=output_dir,
        stem=stem,
        payload=payload,
        markdown=markdown,
    )

    print(markdown)
    print("")
    print(f"Saved JSON: {paths['json_path']}")
    print(f"Saved MD:   {paths['md_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
