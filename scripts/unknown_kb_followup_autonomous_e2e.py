"""
Focused live E2E for unknown-fallback follow-up questions.

Goal:
- keep the same full autonomous pipeline
- use safer, more coherent dialogs where a follow-up discovery question
  should be more natural after an unknown factual/customization answer

Usage:
    python -m scripts.unknown_kb_followup_autonomous_e2e --execution live
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List

from scripts.unknown_kb_full_autonomous_e2e import (
    check_live_dependencies,
    patched_runtime,
    _make_bot,
    run_dialog,
)


SCENARIOS: List[Dict[str, object]] = [
    {
        "id": "FF01",
        "name": "Security question after broad retail context",
        "messages": [
            "Здравствуйте",
            "Смотрим систему для нескольких магазинов, хотим меньше ручного учета и быстрее видеть остатки",
            "Какие у вас SLA, RPO и RTO по системе?",
        ],
    },
    {
        "id": "FF02",
        "name": "White-label after network management need",
        "messages": [
            "Добрый день",
            "Ищем решение для сети точек, важно централизованно управлять продажами и остатками",
            "Можно ли сделать white-label приложение полностью под нашим брендом?",
        ],
    },
    {
        "id": "FF03",
        "name": "Private hosting after security concern",
        "messages": [
            "Здравствуйте",
            "Нужна автоматизация для сети, при этом для нас критичны вопросы безопасности и контроля данных",
            "Можно ли разместить систему в отдельном дата-центре в Казахстане?",
        ],
    },
    {
        "id": "FF04",
        "name": "Custom approvals after discount-control pain",
        "messages": [
            "Добрый день",
            "Сравниваем варианты для нескольких точек, хотим навести порядок со скидками и ручными согласованиями",
            "Можно ли у вас сделать нестандартный регламент согласования скидок?",
        ],
    },
    {
        "id": "FF05",
        "name": "Custom API after franchise operations need",
        "messages": [
            "Здравствуйте",
            "Смотрим систему для франшизы, хотим из одного кабинета управлять точками и продажами",
            "Есть ли у вас кастомный API под наши внутренние сценарии?",
        ],
    },
]


def _has_followup_question(final_response: str) -> bool:
    text = str(final_response or "").strip()
    return "?" in text


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
        "# Focused Unknown Fallback Follow-up E2E",
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
            f"- old-marker leaks: `{sum(1 for item in items if item['has_old_marker'])}/{len(items)}`",
            f"- final responses with follow-up question: "
            f"`{sum(1 for item in items if item['has_followup_question'])}/{len(items)}`",
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
        lines.append(f"- has follow-up question: `{item['has_followup_question']}`")
        lines.append(f"- dialog total_turn_time_ms: `{item['total_turn_time_ms']}`")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution", choices=["live"], default="live")
    args = parser.parse_args()

    health = check_live_dependencies()
    if not all(item.get("ok") for item in health.values()):
        print(json.dumps(health, ensure_ascii=False, indent=2))
        raise SystemExit("Live dependencies are not healthy")

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
        results = [run_dialog(bot, scenario) for scenario in SCENARIOS]

    for item in results:
        item["has_followup_question"] = _has_followup_question(item.get("final_response", ""))

    output_dir = Path(__file__).parent.parent / "results"
    output_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"unknown_kb_followup_live_{timestamp}.json"
    md_path = output_dir / f"unknown_kb_followup_live_{timestamp}.md"

    payload = {
        "execution": args.execution,
        "generated_at": datetime.now().isoformat(),
        "health": health,
        "settings_snapshot": settings_snapshot,
        "tei_counters": tei_counters,
        "results": results,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown = render_markdown(
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
