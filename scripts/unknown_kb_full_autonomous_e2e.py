"""
Full autonomous-pipeline E2E for unknown / KB-empty fallbacks.

Modes:
    live:    real SalesBot(flow_name="autonomous") + Ollama + TEI embed/rerank
    offline: mock-LLM fallback path for quick local checks

Usage:
    python -m scripts.unknown_kb_full_autonomous_e2e --label pre --execution live
    python -m scripts.unknown_kb_full_autonomous_e2e --label post --execution live
"""

from __future__ import annotations

import argparse
import copy
import json
import random
import re
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple
from unittest.mock import MagicMock

import requests

from src.feature_flags import flags
from src.unknown_kb_fallbacks import UNKNOWN_KB_FALLBACK_VARIANTS


SCENARIOS: List[Dict[str, object]] = [
    {
        "id": "FU01",
        "name": "SLA and RPO/RTO",
        "messages": [
            "Здравствуйте",
            "Смотрим систему для сети магазинов",
            "Какие у вас SLA, RPO и RTO по системе?",
        ],
    },
    {
        "id": "FU02",
        "name": "Rare ERP integration",
        "messages": [
            "Добрый день",
            "У нас розничная сеть и нестандартный контур учета",
            "Есть ли интеграция с SAP S/4HANA?",
        ],
    },
    {
        "id": "FU03",
        "name": "Data hosting specifics",
        "messages": [
            "Здравствуйте",
            "Нам важны требования безопасности",
            "На каких именно серверах и в каком дата-центре хранятся данные?",
        ],
    },
    {
        "id": "FU04",
        "name": "Non-standard discount details",
        "messages": [
            "Здравствуйте",
            "Сравниваем несколько вариантов автоматизации",
            "Какая у вас скидка при оплате сразу за 3 года?",
        ],
    },
    {
        "id": "FU05",
        "name": "Unsupported white-label question",
        "messages": [
            "Добрый день",
            "Ищем решение под свою сеть",
            "Можно ли сделать white-label приложение полностью под нашим брендом?",
        ],
    },
]

PRE_VARIANTS: Tuple[str, ...] = (
    "В текущем фрагменте БД нет подтвержденного факта по этому пункту. Уточните, пожалуйста, какой тариф или интеграцию сравниваем.",
    "По доступным фактам БД ответа на этот параметр нет. Назовите продукт или сценарий — отвечу строго по базе.",
    "В предоставленных фактах БД не хватает данных для прямого ответа. Уточните вопрос, и я отвечу только по базе.",
)

OLD_MARKERS: Tuple[str, ...] = (
    "база знаний",
    "в базе",
    "в базе данных",
    "бд",
    "по базе",
    "фактах бд",
    "в предоставленных данных",
    "в доступных данных",
    "в подтвержденных данных",
    "в предоставленной информации",
    "информация отсутствует",
    "в фактах нет",
    "уточню у коллег",
    "у коллег",
    "не удалось найти",
    "не могу найти",
    "не найден",
)

PRE_FALLBACK_RE = re.compile(
    r"(?:уточню\s+у\s+коллег|вернусь\s+с\s+ответом|коллега\s+позвонит|передам\s+вопрос\s+коллег)",
    re.IGNORECASE,
)

PRE_TEXT_REPLACEMENTS: Tuple[Tuple[str, str], ...] = (
    (
        'Фразы "в базе знаний нет", "по базе не найдено" и "уточню у коллег" — ЗАПРЕЩЕНЫ.\n'
        '   Если точного ответа нет в БАЗЕ ЗНАНИЙ, скажи нейтрально и по-человечески, например:\n'
        '   "Я уточню этот вопрос и чуть позже отпишу вам."',
        'Фраза "уточню у коллег" по стандартным тарифам — ЗАПРЕЩЕНА.\n'
        '   "Уточню у коллег" — ТОЛЬКО для нестандартных условий (скидки от объёма, долгосрочный договор)\n'
        '   и технических деталей (SLA, API, интеграции), которых нет в БАЗЕ ЗНАНИЙ.',
    ),
    (
        'На технические вопросы без ответа в базе отвечай нейтрально: "Я уточню этот вопрос и чуть позже отпишу вам."',
        'На технические вопросы без ответа в базе: "уточню у коллег".',
    ),
    (
        'Нет в базе → "Я уточню этот вопрос и чуть позже отпишу вам."',
        'Нет в базе → "уточню у коллег".',
    ),
    (
        "«Актуальные условия скидок уточню и чуть позже отпишу вам».",
        "«Актуальные условия скидок уточню у коллег».",
    ),
    (
        "уточнить детали и чуть позже вернуться с ответом в чате.",
        "уточнить детали у коллеги.",
    ),
    (
        'Если точного ответа нет — скажи нейтрально: "Я уточню этот вопрос и чуть позже отпишу вам." Не упоминай базу знаний, коллег или внутренние ограничения.',
        'Если нет в БАЗЕ ЗНАНИЙ — скажи "уточню у коллег".',
    ),
    (
        "Если точного ответа в БАЗЕ ЗНАНИЙ не хватает — мягко скажи, что уточнишь вопрос и чуть позже отпишешь в чате.",
        "После ответа — мягко обозначь, что для детального разговора потребуется время или уточнение с командой.",
    ),
)

OFFLINE_FLAG_OVERRIDES = {
    "autonomous_flow": True,
    "tone_analysis": False,
    "tone_semantic_tier2": False,
    "tone_llm_tier3": False,
    "llm_classifier": False,
    "classification_refinement": False,
    "semantic_intent_arbitration": False,
    "semantic_frame": False,
    "response_factual_verifier": False,
    "response_boundary_validator": False,
    "response_boundary_llm_judge": False,
    "response_boundary_retry": False,
    "response_boundary_fallback": False,
    "response_diversity": False,
    "response_deduplication": False,
    "question_deduplication": False,
    "response_variations": False,
    "apology_system": False,
}

LIVE_ENDPOINTS = {
    "ollama": "http://ollama:11434/api/tags",
    "tei_embed": "http://tei-embed:80/health",
    "tei_rerank": "http://tei-rerank:80/health",
}


class _FakeRetriever:
    def __init__(self):
        self.kb = type(
            "KB",
            (),
            {
                "company_name": "Wipon",
                "company_description": "POS система",
                "sections": [],
            },
        )()

    def get_company_info(self):
        return "Wipon: POS система"


def _pick_pre_fallback() -> str:
    return random.choice(PRE_VARIANTS)


def _with_pre_fallback(prefix: str | None = None) -> str:
    prefix_text = str(prefix or "").strip()
    fallback = _pick_pre_fallback()
    if not prefix_text:
        return fallback
    if prefix_text[-1] not in ".!?":
        prefix_text += "."
    return f"{prefix_text} {fallback}"


def _replace_text(value: str, replacements: Iterable[Tuple[str, str]]) -> str:
    result = str(value)
    for old, new in replacements:
        result = result.replace(old, new)
    return result


def _deep_replace(data: Any, replacements: Iterable[Tuple[str, str]]) -> Any:
    if isinstance(data, str):
        return _replace_text(data, replacements)
    if isinstance(data, list):
        return [_deep_replace(item, replacements) for item in data]
    if isinstance(data, tuple):
        return tuple(_deep_replace(item, replacements) for item in data)
    if isinstance(data, dict):
        return {key: _deep_replace(value, replacements) for key, value in data.items()}
    return data


def check_live_dependencies() -> Dict[str, Dict[str, object]]:
    health: Dict[str, Dict[str, object]] = {}
    for name, url in LIVE_ENDPOINTS.items():
        try:
            started = time.time()
            response = requests.get(url, timeout=5)
            payload: object
            try:
                payload = response.json()
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
def patched_runtime(label: str, execution: str, tei_counters: Dict[str, int]):
    import src.config as config_module
    import src.config_loader as config_loader_module
    import src.factual_verifier as verifier_module
    import src.generator as generator_module
    import src.generator_autonomous as autonomous_module
    import src.knowledge.reranker as reranker_module
    import src.knowledge.tei_client as tei_client_module
    import src.response_boundary_validator as boundary_module
    from src.generator import ResponseGenerator

    original_get_retriever = generator_module.get_retriever
    original_known = list(ResponseGenerator._KB_EMPTY_CONTACT_KNOWN)
    original_unknown = list(ResponseGenerator._KB_EMPTY_CONTACT_UNKNOWN)
    original_generator_pick = getattr(generator_module, "pick_unknown_kb_fallback", None)
    original_verifier_pick = getattr(verifier_module, "pick_unknown_kb_fallback", None)
    original_boundary_pick = getattr(boundary_module, "pick_unknown_kb_fallback", None)
    original_boundary_with = getattr(boundary_module, "with_unknown_kb_fallback", None)
    original_generator_regex = ResponseGenerator._COLLEAGUE_FALLBACK_RE
    original_verifier_regex = verifier_module.FactualVerifier._FORBIDDEN_FALLBACK_RE
    original_safety_rules = autonomous_module.SAFETY_RULES_V2
    original_system_prompt = config_module.SYSTEM_PROMPT
    original_load_yaml = config_loader_module.ConfigLoader._load_yaml
    original_embed_texts = tei_client_module.embed_texts
    original_embed_single = tei_client_module.embed_single
    original_embed_cached = tei_client_module.embed_texts_cached
    original_rerank = reranker_module.Reranker.rerank

    def counted_embed_texts(*args, **kwargs):
        tei_counters["embed_calls"] = tei_counters.get("embed_calls", 0) + 1
        return original_embed_texts(*args, **kwargs)

    def counted_embed_single(*args, **kwargs):
        tei_counters["embed_single_calls"] = tei_counters.get("embed_single_calls", 0) + 1
        return original_embed_single(*args, **kwargs)

    def counted_embed_cached(*args, **kwargs):
        tei_counters["embed_cached_calls"] = tei_counters.get("embed_cached_calls", 0) + 1
        return original_embed_cached(*args, **kwargs)

    def counted_rerank(self, *args, **kwargs):
        tei_counters["rerank_calls"] = tei_counters.get("rerank_calls", 0) + 1
        return original_rerank(self, *args, **kwargs)

    def patched_load_yaml(self, relative_path: str, required: bool = True):
        data = original_load_yaml(self, relative_path, required)
        if label != "pre":
            return data
        if relative_path == "templates/autonomous/prompts.yaml":
            return _deep_replace(copy.deepcopy(data), PRE_TEXT_REPLACEMENTS)
        return data

    tei_client_module.embed_texts = counted_embed_texts
    tei_client_module.embed_single = counted_embed_single
    tei_client_module.embed_texts_cached = counted_embed_cached
    reranker_module.Reranker.rerank = counted_rerank

    if execution == "offline":
        generator_module.get_retriever = lambda: _FakeRetriever()
        flags.clear_all_overrides()
        for name, value in OFFLINE_FLAG_OVERRIDES.items():
            flags.set_override(name, value)
    else:
        flags.clear_all_overrides()
        from src.bot import setup_autonomous_pipeline

        setup_autonomous_pipeline()

    if label == "pre":
        ResponseGenerator._KB_EMPTY_CONTACT_KNOWN = list(PRE_VARIANTS)
        ResponseGenerator._KB_EMPTY_CONTACT_UNKNOWN = list(PRE_VARIANTS)
        ResponseGenerator._COLLEAGUE_FALLBACK_RE = PRE_FALLBACK_RE
        verifier_module.FactualVerifier._FORBIDDEN_FALLBACK_RE = PRE_FALLBACK_RE

        if original_generator_pick is not None:
            generator_module.pick_unknown_kb_fallback = _pick_pre_fallback
        if original_verifier_pick is not None:
            verifier_module.pick_unknown_kb_fallback = _pick_pre_fallback
        if original_boundary_pick is not None:
            boundary_module.pick_unknown_kb_fallback = _pick_pre_fallback
        if original_boundary_with is not None:
            boundary_module.with_unknown_kb_fallback = _with_pre_fallback

        autonomous_module.SAFETY_RULES_V2 = _replace_text(original_safety_rules, PRE_TEXT_REPLACEMENTS)
        config_module.SYSTEM_PROMPT = _replace_text(original_system_prompt, PRE_TEXT_REPLACEMENTS)
        config_loader_module.ConfigLoader._load_yaml = patched_load_yaml

    try:
        yield
    finally:
        generator_module.get_retriever = original_get_retriever
        ResponseGenerator._KB_EMPTY_CONTACT_KNOWN = original_known
        ResponseGenerator._KB_EMPTY_CONTACT_UNKNOWN = original_unknown
        ResponseGenerator._COLLEAGUE_FALLBACK_RE = original_generator_regex
        verifier_module.FactualVerifier._FORBIDDEN_FALLBACK_RE = original_verifier_regex
        autonomous_module.SAFETY_RULES_V2 = original_safety_rules
        config_module.SYSTEM_PROMPT = original_system_prompt
        config_loader_module.ConfigLoader._load_yaml = original_load_yaml
        tei_client_module.embed_texts = original_embed_texts
        tei_client_module.embed_single = original_embed_single
        tei_client_module.embed_texts_cached = original_embed_cached
        reranker_module.Reranker.rerank = original_rerank

        if original_generator_pick is not None:
            generator_module.pick_unknown_kb_fallback = original_generator_pick
        if original_verifier_pick is not None:
            verifier_module.pick_unknown_kb_fallback = original_verifier_pick
        if original_boundary_pick is not None:
            boundary_module.pick_unknown_kb_fallback = original_boundary_pick
        if original_boundary_with is not None:
            boundary_module.with_unknown_kb_fallback = original_boundary_with

        flags.clear_all_overrides()


def _make_bot(execution: str):
    from src.bot import SalesBot

    if execution == "offline":
        llm = MagicMock()
        llm.generate.return_value = "stub"
        llm.generate_structured.return_value = None
        bot = SalesBot(llm=llm, flow_name="autonomous", enable_tracing=True)
        pipeline = MagicMock()
        pipeline.retrieve.return_value = ("", [], [])
        bot.generator._enhanced_pipeline = pipeline
        return bot, llm

    from src.llm import OllamaLLM

    llm = OllamaLLM()
    bot = SalesBot(llm=llm, flow_name="autonomous", enable_tracing=True)
    return bot, llm


def _extract_verifier_meta(result: Dict[str, Any]) -> Dict[str, Any]:
    meta = result.get("_factual_verifier_meta") or result.get("metadata") or {}
    return {
        "factual_verifier_used": result.get("factual_verifier_used", meta.get("factual_verifier_used")),
        "factual_verifier_changed": result.get("factual_verifier_changed", meta.get("factual_verifier_changed")),
        "factual_verifier_verdict": result.get("factual_verifier_verdict", meta.get("factual_verifier_verdict")),
        "factual_verifier_reason_codes": result.get("factual_verifier_reason_codes", meta.get("factual_verifier_reason_codes")),
    }


def run_dialog(bot, scenario: Dict[str, object]) -> Dict[str, object]:
    bot.reset()
    turns: List[Dict[str, object]] = []

    for index, message in enumerate(scenario["messages"], start=1):
        started = time.time()
        result = bot.process(message)
        elapsed_ms = round((time.time() - started) * 1000, 1)
        verifier_meta = _extract_verifier_meta(result)
        turns.append(
            {
                "turn": index,
                "user": message,
                "bot": str(result.get("response", "") or ""),
                "intent": str(result.get("intent", "") or ""),
                "state": str(result.get("state", "") or ""),
                "action": str(result.get("action", "") or ""),
                "elapsed_ms": elapsed_ms,
                "factual_verifier_used": verifier_meta["factual_verifier_used"],
                "factual_verifier_changed": verifier_meta["factual_verifier_changed"],
                "factual_verifier_verdict": verifier_meta["factual_verifier_verdict"],
            }
        )
        if result.get("is_final"):
            break

    final_response = turns[-1]["bot"] if turns else ""
    final_lower = str(final_response).lower()
    leaked_old_markers = [marker for marker in OLD_MARKERS if marker in final_lower]

    return {
        "id": scenario["id"],
        "name": scenario["name"],
        "turns": turns,
        "final_response": final_response,
        "has_old_marker": bool(leaked_old_markers),
        "old_markers": leaked_old_markers,
        "total_turn_time_ms": round(sum(float(turn["elapsed_ms"]) for turn in turns), 1),
    }


def render_markdown(
    *,
    label: str,
    execution: str,
    health: Dict[str, Dict[str, object]],
    settings_snapshot: Dict[str, object],
    tei_counters: Dict[str, int],
    results: Iterable[Dict[str, object]],
) -> str:
    items = list(results)
    lines = [
        f"# Full Autonomous Unknown KB E2E — {label.upper()}",
        "",
        f"Execution: {execution}",
        f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Stack",
        "",
        f"- llm.model: `{settings_snapshot['llm_model']}`",
        f"- llm.base_url: `{settings_snapshot['llm_base_url']}`",
        f"- retriever.use_embeddings: `{settings_snapshot['retriever_use_embeddings']}`",
        f"- retriever.embedder_url: `{settings_snapshot['retriever_embedder_url']}`",
        f"- reranker.enabled: `{settings_snapshot['reranker_enabled']}`",
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
            f"## Summary",
            "",
            f"- old-marker leaks: `{sum(1 for item in items if item['has_old_marker'])}/{len(items)}`",
            "",
        ]
    )

    for item in items:
        lines.append(f"## {item['id']} — {item['name']}")
        lines.append("")
        for turn in item["turns"]:
            lines.append(f"U{turn['turn']}: {turn['user']}")
            lines.append(f"B{turn['turn']}: {turn['bot']}")
            lines.append(
                "   "
                f"action=`{turn['action']}` intent=`{turn['intent']}` state=`{turn['state']}` "
                f"elapsed_ms=`{turn['elapsed_ms']}` "
                f"verifier=`{turn['factual_verifier_verdict']}`"
            )
        lines.append("")
        lines.append(f"- final old_markers: `{', '.join(item['old_markers']) or 'none'}`")
        lines.append(f"- dialog total_turn_time_ms: `{item['total_turn_time_ms']}`")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", choices=["pre", "post"], default="post")
    parser.add_argument("--execution", choices=["live", "offline"], default="live")
    args = parser.parse_args()

    health = check_live_dependencies() if args.execution == "live" else {}
    if args.execution == "live" and not all(item.get("ok") for item in health.values()):
        print(json.dumps(health, ensure_ascii=False, indent=2))
        raise SystemExit("Live dependencies are not healthy")

    tei_counters: Dict[str, int] = {}
    with patched_runtime(args.label, args.execution, tei_counters):
        bot, _llm = _make_bot(args.execution)
        from src.settings import settings

        settings_snapshot = {
            "llm_model": settings.llm.model,
            "llm_base_url": settings.llm.base_url,
            "retriever_use_embeddings": settings.retriever.use_embeddings,
            "retriever_embedder_url": settings.retriever.embedder_url,
            "reranker_enabled": settings.reranker.enabled,
            "reranker_url": settings.reranker.url,
        }
        results = [run_dialog(bot, scenario) for scenario in SCENARIOS]

    output_dir = Path(__file__).parent.parent / "results"
    output_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"unknown_kb_full_autonomous_{args.execution}_{args.label}_{timestamp}.json"
    md_path = output_dir / f"unknown_kb_full_autonomous_{args.execution}_{args.label}_{timestamp}.md"

    payload = {
        "label": args.label,
        "execution": args.execution,
        "generated_at": datetime.now().isoformat(),
        "health": health,
        "settings_snapshot": settings_snapshot,
        "tei_counters": tei_counters,
        "results": results,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown = render_markdown(
        label=args.label,
        execution=args.execution,
        health=health,
        settings_snapshot=settings_snapshot,
        tei_counters=tei_counters,
        results=results,
    )
    md_path.write_text(markdown, encoding="utf-8")

    print(markdown)
    print("")
    print(f"Saved JSON: {json_path}")
    print(f"Saved MD:   {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
