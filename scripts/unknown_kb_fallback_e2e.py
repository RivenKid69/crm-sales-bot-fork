"""
Special E2E for unknown / KB-empty fallbacks.

Runs 5 realistic dialogue snippets through the real ResponseGenerator
with an empty KB retrieval result, so we can compare the shipped fallback
text before and after prompt/text changes.

Usage:
    python -m scripts.unknown_kb_fallback_e2e --label pre
    python -m scripts.unknown_kb_fallback_e2e --label post
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List
from unittest.mock import MagicMock


SCENARIOS: List[Dict[str, object]] = [
    {
        "id": "U01",
        "name": "SLA and RPO/RTO",
        "intent": "question_security",
        "state": "autonomous_qualification",
        "messages": [
            "Здравствуйте",
            "Смотрим систему для сети магазинов",
            "Какие у вас SLA, RPO и RTO по системе?",
        ],
    },
    {
        "id": "U02",
        "name": "Rare ERP integration",
        "intent": "question_integrations",
        "state": "autonomous_discovery",
        "messages": [
            "Добрый день",
            "У нас розничная сеть и нестандартный контур учета",
            "Есть ли интеграция с SAP S/4HANA?",
        ],
    },
    {
        "id": "U03",
        "name": "Data hosting specifics",
        "intent": "question_security",
        "state": "autonomous_discovery",
        "messages": [
            "Здравствуйте",
            "Нам важны требования безопасности",
            "На каких именно серверах и в каком дата-центре хранятся данные?",
        ],
    },
    {
        "id": "U04",
        "name": "Non-standard discount details",
        "intent": "question_pricing",
        "state": "autonomous_negotiation",
        "messages": [
            "Здравствуйте",
            "Сравниваем несколько вариантов автоматизации",
            "Какая у вас скидка при оплате сразу за 3 года?",
        ],
    },
    {
        "id": "U05",
        "name": "Unsupported white-label question",
        "intent": "question_features",
        "state": "autonomous_presentation",
        "messages": [
            "Добрый день",
            "Ищем решение под свою сеть",
            "Можно ли сделать white-label приложение полностью под нашим брендом?",
        ],
    },
]

OLD_MARKERS = (
    "база знаний",
    "в базе",
    "бд",
    "по базе",
    "фактах бд",
    "уточню у коллег",
    "у коллег",
    "не удалось найти",
    "не могу найти",
    "не нашла",
    "не найден",
)


def _make_generator():
    from src.generator import ResponseGenerator

    llm = MagicMock()
    flow = MagicMock()
    flow.name = "autonomous"
    flow.get_template.return_value = None

    generator = ResponseGenerator(llm=llm, flow=flow)

    pipeline = MagicMock()
    pipeline.retrieve.return_value = ("", [], [])
    generator._enhanced_pipeline = pipeline

    return generator, llm


def _build_context(scenario: Dict[str, object]) -> Dict[str, object]:
    messages = list(scenario["messages"])
    history = []
    for msg in messages[:-1]:
        history.append({"user": msg, "bot": ""})
    return {
        "intent": str(scenario["intent"]),
        "state": str(scenario["state"]),
        "user_message": str(messages[-1]),
        "history": history,
        "spin_phase": "situation",
        "collected_data": {},
        "recent_fact_keys": [],
    }


def run_scenario(generator, llm, scenario: Dict[str, object]) -> Dict[str, object]:
    context = _build_context(scenario)
    response = generator.generate(action="autonomous_respond", context=context)
    response_text = str(response or "")
    lower = response_text.lower()
    leaked_old_markers = [marker for marker in OLD_MARKERS if marker in lower]

    return {
        "id": scenario["id"],
        "name": scenario["name"],
        "intent": scenario["intent"],
        "state": scenario["state"],
        "messages": scenario["messages"],
        "response": response_text,
        "llm_called": bool(llm.generate.called),
        "selected_template_key": generator._last_generation_meta.get("selected_template_key"),
        "leaked_old_markers": leaked_old_markers,
        "has_old_marker": bool(leaked_old_markers),
    }


def render_markdown(label: str, results: List[Dict[str, object]]) -> str:
    lines = [
        f"# Unknown KB Fallback E2E — {label.upper()}",
        "",
        f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]

    total_with_old_markers = sum(1 for item in results if item["has_old_marker"])
    lines.append(f"Old-marker leaks: {total_with_old_markers}/{len(results)}")
    lines.append("")

    for item in results:
        lines.append(f"## {item['id']} — {item['name']}")
        lines.append("")
        for i, msg in enumerate(item["messages"], start=1):
            prefix = "Client"
            lines.append(f"{prefix} {i}: {msg}")
        lines.append("")
        lines.append(f"Bot: {item['response']}")
        lines.append("")
        lines.append(f"- intent: `{item['intent']}`")
        lines.append(f"- state: `{item['state']}`")
        lines.append(f"- template: `{item['selected_template_key']}`")
        lines.append(f"- llm_called: `{item['llm_called']}`")
        lines.append(f"- old_markers: `{', '.join(item['leaked_old_markers']) or 'none'}`")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", choices=["pre", "post"], default="pre")
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).parent.parent))

    generator, llm = _make_generator()
    results = [run_scenario(generator, llm, scenario) for scenario in SCENARIOS]

    output_dir = Path(__file__).parent.parent / "results"
    output_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"unknown_kb_fallback_{args.label}_{timestamp}.json"
    md_path = output_dir / f"unknown_kb_fallback_{args.label}_{timestamp}.md"

    payload = {
        "label": args.label,
        "generated_at": datetime.now().isoformat(),
        "results": results,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown = render_markdown(args.label, results)
    md_path.write_text(markdown, encoding="utf-8")

    print(markdown)
    print("")
    print(f"Saved JSON: {json_path}")
    print(f"Saved MD:   {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
