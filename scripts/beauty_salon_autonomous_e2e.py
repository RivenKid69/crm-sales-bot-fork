"""
Focused full autonomous E2E for beauty-salon style lead dialogs.

Goal:
- run the real autonomous pipeline with Ollama + TEI services
- verify positive-first answers for generic salon-fit questions
- verify honest limitation handling when the client asks directly

Recommended launch pattern inside Docker network:
    python -m scripts.beauty_salon_autonomous_e2e --execution live --output-dir /workspace/results
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

from scripts.unknown_kb_full_autonomous_e2e import (
    _make_bot,
    check_live_dependencies,
    patched_runtime,
    run_dialog,
)


GENERAL_POSITIVE_MARKERS: Sequence[str] = (
    "услуг",
    "товар",
    "продаж",
    "учет",
    "учёт",
    "касс",
    "аналит",
)

SALON_USE_CASE_MARKERS: Sequence[str] = (
    "салон",
    "студи",
    "барбершоп",
    "бьюти",
    "услуг",
    "товар",
)

UNASKED_LIMITATION_MARKERS: Sequence[str] = (
    "расписан",
    "мастер",
    "нет встроенного",
    "не включает встроенное",
    "недоработ",
    "минус",
)

DIRECT_LIMITATION_MARKERS: Sequence[str] = (
    "расписан",
    "мастер",
    "нет встроенного",
    "не включает",
    "огранич",
)

NEGATIVE_OPENERS: Sequence[str] = (
    "но",
    "однако",
)

SCENARIOS: List[Dict[str, object]] = [
    {
        "id": "BS01",
        "name": "Generic salon consultation stays positive-first",
        "messages": [
            "Добрый день. Нужна консультация по внедрению в салон красоты.",
            "У нас услуги и немного косметики на продажу. В целом Wipon для такого салона подходит?",
        ],
        "checks": [
            {
                "turn": 1,
                "must_not_contain_any": list(UNASKED_LIMITATION_MARKERS),
            },
            {
                "turn": 2,
                "must_contain_any": list(SALON_USE_CASE_MARKERS),
                "must_not_contain_any": list(UNASKED_LIMITATION_MARKERS),
                "must_not_start_with_any": list(NEGATIVE_OPENERS),
            }
        ],
    },
    {
        "id": "BS02",
        "name": "Client explicitly asks not to start with negatives",
        "messages": [
            "Здравствуйте",
            "Подбираем решение для студии красоты.",
            "Только коротко и без минусов в начале: для салона в целом подходит?",
        ],
        "checks": [
            {
                "turn": 3,
                "must_contain_any": list(SALON_USE_CASE_MARKERS),
                "must_not_contain_any": list(UNASKED_LIMITATION_MARKERS),
                "must_not_start_with_any": list(NEGATIVE_OPENERS),
            }
        ],
    },
    {
        "id": "BS03",
        "name": "Barbershop with retail gets value-first answer",
        "messages": [
            "Добрый день",
            "У нас барбершоп: услуги плюс продажа косметики, хотим навести порядок в оплатах.",
            "Что Wipon закрывает в таком формате?",
        ],
        "checks": [
            {
                "turn": 3,
                "must_contain_any": list(SALON_USE_CASE_MARKERS),
                "must_not_contain_any": list(UNASKED_LIMITATION_MARKERS),
                "must_not_start_with_any": list(NEGATIVE_OPENERS),
            }
        ],
    },
    {
        "id": "BS04",
        "name": "Direct schedule question gets direct limitation answer",
        "messages": [
            "Здравствуйте",
            "Смотрим систему для салона красоты.",
            "Есть ли у вас встроенное расписание мастеров?",
        ],
        "checks": [
            {
                "turn": 3,
                "must_contain_any": list(DIRECT_LIMITATION_MARKERS),
            }
        ],
    },
    {
        "id": "BS05",
        "name": "Direct limitation request may surface salon caveat",
        "messages": [
            "Добрый день",
            "Рассматриваем Wipon для beauty-студии.",
            "Если честно, какие для салона есть ограничения?",
        ],
        "checks": [
            {
                "turn": 3,
                "must_contain_any": list(DIRECT_LIMITATION_MARKERS),
            }
        ],
    },
    {
        "id": "BS06",
        "name": "Beauty chain implementation question stays product-first",
        "messages": [
            "Здравствуйте",
            "Нужна консультация по внедрению в сеть студий красоты.",
            "У нас услуги, абонементы и продажа косметики. Какой контур вы закрываете?",
        ],
        "checks": [
            {
                "turn": 3,
                "must_contain_any": list(SALON_USE_CASE_MARKERS),
                "must_not_contain_any": list(UNASKED_LIMITATION_MARKERS),
                "must_not_start_with_any": list(NEGATIVE_OPENERS),
            }
        ],
    },
]


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def evaluate_turn_check(turn_text: str, check: Dict[str, object]) -> Dict[str, object]:
    normalized = normalize_text(turn_text)
    must_contain_any = [normalize_text(item) for item in check.get("must_contain_any", [])]
    must_not_contain_any = [normalize_text(item) for item in check.get("must_not_contain_any", [])]
    must_not_start_with_any = [normalize_text(item) for item in check.get("must_not_start_with_any", [])]

    missing_any_group = bool(must_contain_any) and not any(marker in normalized for marker in must_contain_any)
    forbidden_markers = [marker for marker in must_not_contain_any if marker in normalized]
    forbidden_openers = [prefix for prefix in must_not_start_with_any if normalized.startswith(prefix)]

    return {
        "passed": not missing_any_group and not forbidden_markers and not forbidden_openers,
        "normalized_text": normalized,
        "missing_any_group": missing_any_group,
        "must_contain_any": must_contain_any,
        "forbidden_markers": forbidden_markers,
        "forbidden_openers": forbidden_openers,
    }


def evaluate_scenario(result: Dict[str, object], scenario: Dict[str, object]) -> Dict[str, object]:
    turns = list(result.get("turns") or [])
    evaluations: List[Dict[str, object]] = []

    for check in scenario.get("checks", []):
        turn_number = int(check["turn"])
        if turn_number > len(turns):
            evaluations.append(
                {
                    "turn": turn_number,
                    "passed": False,
                    "error": "missing_turn",
                    "bot": "",
                }
            )
            continue

        bot_text = str(turns[turn_number - 1].get("bot", "") or "")
        evaluation = evaluate_turn_check(bot_text, check)
        evaluation.update(
            {
                "turn": turn_number,
                "bot": bot_text,
            }
        )
        evaluations.append(evaluation)

    passed = all(item.get("passed") for item in evaluations)
    return {
        "checks": evaluations,
        "passed": passed,
    }


def render_markdown(
    *,
    execution: str,
    health: Dict[str, Dict[str, object]],
    settings_snapshot: Dict[str, object],
    tei_counters: Dict[str, int],
    results: Iterable[Dict[str, object]],
) -> str:
    items = list(results)
    lines = [
        "# Beauty Salon Autonomous E2E",
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
            "## Summary",
            "",
            f"- passed scenarios: `{sum(1 for item in items if item['evaluation']['passed'])}/{len(items)}`",
            f"- failed scenarios: `{sum(1 for item in items if not item['evaluation']['passed'])}/{len(items)}`",
            "",
        ]
    )

    for item in items:
        lines.append(f"## {item['id']} — {item['name']}")
        lines.append("")
        lines.append(f"- scenario passed: `{item['evaluation']['passed']}`")
        lines.append(f"- old markers: `{', '.join(item['old_markers']) or 'none'}`")
        lines.append(f"- dialog total_turn_time_ms: `{item['total_turn_time_ms']}`")
        lines.append("")
        for turn in item["turns"]:
            lines.append(f"U{turn['turn']}: {turn['user']}")
            lines.append(f"B{turn['turn']}: {turn['bot']}")
            lines.append(
                "   "
                f"action=`{turn['action']}` intent=`{turn['intent']}` state=`{turn['state']}` "
                f"elapsed_ms=`{turn['elapsed_ms']}` verifier=`{turn['factual_verifier_verdict']}`"
            )
        lines.append("")

        for check in item["evaluation"]["checks"]:
            if check.get("error") == "missing_turn":
                lines.append(f"- check turn {check['turn']}: FAIL missing turn")
                continue
            lines.append(
                f"- check turn {check['turn']}: "
                f"{'PASS' if check['passed'] else 'FAIL'} "
                f"forbidden_markers=`{', '.join(check.get('forbidden_markers') or []) or 'none'}` "
                f"forbidden_openers=`{', '.join(check.get('forbidden_openers') or []) or 'none'}` "
                f"missing_any_group=`{check.get('missing_any_group')}`"
            )
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution", choices=["live"], default="live")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--scenario-id", action="append", default=[])
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    health = check_live_dependencies()
    if not all(item.get("ok") for item in health.values()):
        print(json.dumps(health, ensure_ascii=False, indent=2))
        raise SystemExit("Live dependencies are not healthy")

    selected_scenarios = list(SCENARIOS)
    if args.scenario_id:
        requested_ids = {item.strip().upper() for item in args.scenario_id if str(item).strip()}
        selected_scenarios = [item for item in selected_scenarios if str(item["id"]).upper() in requested_ids]
        if not selected_scenarios:
            raise SystemExit(f"No scenarios matched: {sorted(requested_ids)}")
    if args.limit and args.limit > 0:
        selected_scenarios = selected_scenarios[: args.limit]

    tei_counters: Dict[str, int] = {}
    with patched_runtime("post", args.execution, tei_counters):
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
        results = [run_dialog(bot, scenario) for scenario in selected_scenarios]

    enriched_results: List[Dict[str, object]] = []
    for scenario, result in zip(selected_scenarios, results):
        item = dict(result)
        item["evaluation"] = evaluate_scenario(result, scenario)
        enriched_results.append(item)

    output_dir = Path(args.output_dir) if args.output_dir else (Path(__file__).parent.parent / "results")
    output_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"beauty_salon_autonomous_live_{timestamp}.json"
    md_path = output_dir / f"beauty_salon_autonomous_live_{timestamp}.md"

    payload = {
        "execution": args.execution,
        "generated_at": datetime.now().isoformat(),
        "health": health,
        "settings_snapshot": settings_snapshot,
        "tei_counters": tei_counters,
        "selected_scenarios": [item["id"] for item in selected_scenarios],
        "results": enriched_results,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown = render_markdown(
        execution=args.execution,
        health=health,
        settings_snapshot=settings_snapshot,
        tei_counters=tei_counters,
        results=enriched_results,
    )
    md_path.write_text(markdown, encoding="utf-8")

    print(markdown)
    print("")
    print(f"Saved JSON: {json_path}")
    print(f"Saved MD:   {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
