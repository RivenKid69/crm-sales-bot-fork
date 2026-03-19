"""
E2E audit for 4 non-sales misroute intents through the full autonomous pipeline.

Runs real SalesBot(flow_name="autonomous") against all available Ollama chat models
and validates:
1. True positives for each new intent (3 scenarios each)
2. False-positive resistance (1 negative control per intent)
3. Final response routing/phone numbers/template constraints

Suggested docker usage:
  docker run --rm --network crm-sales-bot-fork_default \
    -e OLLAMA_BASE_URL=http://ollama:11434 \
    -e TEI_EMBED_URL=http://tei-embed:80 \
    -e TEI_RERANK_URL=http://tei-rerank:80 \
    -v "$PWD":/app -w /app crm-sales-bot-fork-bot \
    python3 -u scripts/misroute_intents_full_e2e.py
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import requests


POSITIVE_SCENARIOS: List[Dict[str, Any]] = [
    {
        "id": "WO1",
        "kind": "positive",
        "expected_intent": "misroute_wipon_outage",
        "messages": [
            "Здравствуйте, мы уже работаем на Wipon второй месяц.",
            "С утра Wipon упал, касса висит и чеки не пробиваются. Куда срочно писать?",
        ],
        "must_contain": ["+77070202019", "технические работы"],
        "must_not_contain": ["личного менеджера"],
    },
    {
        "id": "WO2",
        "kind": "positive",
        "expected_intent": "misroute_wipon_outage",
        "messages": [
            "Это не вопрос по покупке, мы уже ваши клиенты.",
            "Сегодня система легла, вообще не заходит Wipon, нужен контакт куда обратиться.",
        ],
        "must_contain": ["+77070202019", "технические работы"],
        "must_not_contain": ["личного менеджера"],
    },
    {
        "id": "WO3",
        "kind": "positive",
        "expected_intent": "misroute_wipon_outage",
        "messages": [
            "Мы действующие клиенты, продажа не интересует.",
            "После открытия смены у нас сбой по Wipon, ничего не работает.",
        ],
        "must_contain": ["+77070202019", "технические работы"],
        "must_not_contain": ["личного менеджера"],
    },
    {
        "id": "PD1",
        "kind": "positive",
        "expected_intent": "misroute_pending_delivery",
        "messages": [
            "Мы уже оплатили у вас комплект оборудования.",
            "Товар до сих пор не доехал до Астаны, куда писать по доставке?",
        ],
        "must_contain": ["+77087010744", "менеджером по оборудованию"],
        "must_not_contain": ["личного менеджера", "+77070202019"],
    },
    {
        "id": "PD2",
        "kind": "positive",
        "expected_intent": "misroute_pending_delivery",
        "messages": [
            "Покупать больше ничего не хотим, вопрос по уже купленному.",
            "Заказали у вас принтер и сканер, но доставка задержалась. Где наш заказ?",
        ],
        "must_contain": ["+77087010744", "менеджером по оборудованию"],
        "must_not_contain": ["личного менеджера", "+77070202019"],
    },
    {
        "id": "PD3",
        "kind": "positive",
        "expected_intent": "misroute_pending_delivery",
        "messages": [
            "Оборудование у вас уже купили на прошлой неделе.",
            "Когда привезут терминал? Он еще не доехал до клиента.",
        ],
        "must_contain": ["+77087010744", "менеджером по оборудованию"],
        "must_not_contain": ["личного менеджера", "+77070202019"],
    },
    {
        "id": "TR1",
        "kind": "positive",
        "expected_intent": "misroute_training_support",
        "messages": [
            "Мы уже подключены и работаем на Wipon.",
            "Обучение обещали, но так и не провели. Когда оно будет?",
        ],
        "must_contain": ["+77070202019", "технические работы", "обучения"],
        "must_not_contain": ["личного менеджера"],
    },
    {
        "id": "TR2",
        "kind": "positive",
        "expected_intent": "misroute_training_support",
        "messages": [
            "Работаем на Wipon, это не про покупку.",
            "Нужно повторное обучение для новых кассиров, куда обращаться?",
        ],
        "must_contain": ["+77070202019", "технические работы", "обучения"],
        "must_not_contain": ["личного менеджера"],
    },
    {
        "id": "TR3",
        "kind": "positive",
        "expected_intent": "misroute_training_support",
        "messages": [
            "Мы уже ваши клиенты.",
            "Будет ли повторное обучение по продукту? Первичное сорвалось.",
        ],
        "must_contain": ["+77070202019", "технические работы", "обучения"],
        "must_not_contain": ["личного менеджера"],
    },
    {
        "id": "TS1",
        "kind": "positive",
        "expected_intent": "misroute_technical_support",
        "messages": [
            "Мы уже пользуемся системой.",
            "Дайте номер техподдержки, у нас проблема по действующей кассе.",
        ],
        "must_contain": ["+77070202019", "технической поддержкой"],
        "must_not_contain": ["личного менеджера", "технические работы", "+77087010744"],
    },
    {
        "id": "TS2",
        "kind": "positive",
        "expected_intent": "misroute_technical_support",
        "messages": [
            "Мы ваши клиенты.",
            "Куда написать в техподдержку по зависанию принтера?",
        ],
        "must_contain": ["+77070202019", "технической поддержкой"],
        "must_not_contain": ["личного менеджера", "технические работы", "+77087010744"],
    },
    {
        "id": "TS3",
        "kind": "positive",
        "expected_intent": "misroute_technical_support",
        "messages": [
            "По продаже вопросов нет, все уже купили.",
            "Нужна техподдержка по текущей точке, подскажите контакт.",
        ],
        "must_contain": ["+77070202019", "технической поддержкой"],
        "must_not_contain": ["личного менеджера", "технические работы", "+77087010744"],
    },
]

NEGATIVE_SCENARIOS: List[Dict[str, Any]] = [
    {
        "id": "NW1",
        "kind": "negative",
        "forbidden_intent": "misroute_wipon_outage",
        "messages": [
            "Здравствуйте, рассматриваем Wipon для сети магазинов.",
            "Если Wipon вдруг упадет в час пик, какая у вас поддержка и SLA?",
        ],
        "must_not_contain": ["Сейчас ведутся технические работы", "+77070202019"],
    },
    {
        "id": "NP1",
        "kind": "negative",
        "forbidden_intent": "misroute_pending_delivery",
        "messages": [
            "Здравствуйте, выбираем оборудование.",
            "Если закажем терминал, сколько обычно занимает доставка до Шымкента?",
        ],
        "must_not_contain": ["+77087010744", "менеджером по оборудованию"],
    },
    {
        "id": "NT1",
        "kind": "negative",
        "forbidden_intent": "misroute_training_support",
        "messages": [
            "Ищем систему для сети аптек.",
            "А обучение сотрудников у вас вообще входит и как оно проходит?",
        ],
        "must_not_contain": ["Сейчас ведутся технические работы", "+77070202019"],
    },
    {
        "id": "NS1",
        "kind": "negative",
        "forbidden_intent": "misroute_technical_support",
        "messages": [
            "Смотрим вашу систему для покупки.",
            "Как связаться с техподдержкой и какое время ответа у вас по тарифам?",
        ],
        "must_not_contain": ["Пожалуйста, свяжитесь с технической поддержкой: +77070202019."],
    },
]

SCENARIOS: List[Dict[str, Any]] = POSITIVE_SCENARIOS + NEGATIVE_SCENARIOS


def get_models(base_url: str) -> List[str]:
    payload = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=20).json()
    models = [m["name"] for m in payload.get("models", [])]
    blocked = ("embed", "embedding", "rerank")
    return [m for m in models if not any(token in m.lower() for token in blocked)]


def contains_all(text: str, parts: List[str]) -> List[str]:
    lowered = text.lower()
    return [part for part in parts if part.lower() not in lowered]


def contains_any(text: str, parts: List[str]) -> List[str]:
    lowered = text.lower()
    return [part for part in parts if part.lower() in lowered]


def run_scenario(bot, scenario: Dict[str, Any]) -> Dict[str, Any]:
    bot.reset()
    turns: List[Dict[str, Any]] = []

    for idx, message in enumerate(scenario["messages"], start=1):
        started = time.time()
        result = bot.process(message)
        elapsed_ms = round((time.time() - started) * 1000, 1)
        turns.append(
            {
                "turn": idx,
                "user": message,
                "intent": str(result.get("intent", "") or ""),
                "state": str(result.get("state", "") or ""),
                "action": str(result.get("action", "") or ""),
                "response": str(result.get("response", "") or ""),
                "elapsed_ms": elapsed_ms,
            }
        )

    last = turns[-1]
    final_intent = last["intent"]
    final_response = last["response"]
    missing_required = contains_all(final_response, scenario.get("must_contain", []))
    forbidden_found = contains_any(final_response, scenario.get("must_not_contain", []))

    if scenario["kind"] == "positive":
        intent_ok = final_intent == scenario["expected_intent"]
    else:
        intent_ok = final_intent != scenario["forbidden_intent"]

    passed = intent_ok and not missing_required and not forbidden_found

    return {
        "id": scenario["id"],
        "kind": scenario["kind"],
        "messages": scenario["messages"],
        "expected_intent": scenario.get("expected_intent"),
        "forbidden_intent": scenario.get("forbidden_intent"),
        "final_intent": final_intent,
        "final_state": last["state"],
        "final_action": last["action"],
        "final_response": final_response,
        "turns": turns,
        "intent_ok": intent_ok,
        "missing_required": missing_required,
        "forbidden_found": forbidden_found,
        "passed": passed,
    }


def render_markdown(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Misroute intents full E2E")
    lines.append("")
    lines.append(f"- Timestamp: {report['timestamp']}")
    lines.append(f"- Models: {', '.join(report['models'])}")
    lines.append(f"- Total scenarios per model: {report['scenario_count']}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Model | Passed | Total | Pass rate |")
    lines.append("| --- | ---: | ---: | ---: |")
    for summary in report["summaries"]:
        lines.append(
            f"| {summary['model']} | {summary['passed']} | {summary['total']} | {summary['pass_rate']}% |"
        )
    for model_run in report["runs"]:
        lines.append("")
        lines.append(f"## {model_run['model']}")
        lines.append("")
        for item in model_run["results"]:
            status = "PASS" if item["passed"] else "FAIL"
            lines.append(f"### {item['id']} [{status}]")
            lines.append("")
            lines.append(f"- Kind: {item['kind']}")
            lines.append(f"- Final intent: `{item['final_intent']}`")
            lines.append(f"- Final action: `{item['final_action']}`")
            lines.append(f"- Final state: `{item['final_state']}`")
            if item["expected_intent"]:
                lines.append(f"- Expected intent: `{item['expected_intent']}`")
            if item["forbidden_intent"]:
                lines.append(f"- Forbidden intent: `{item['forbidden_intent']}`")
            if item["missing_required"]:
                lines.append(f"- Missing required markers: {item['missing_required']}")
            if item["forbidden_found"]:
                lines.append(f"- Forbidden markers found: {item['forbidden_found']}")
            lines.append(f"- Final response: {item['final_response']}")
            lines.append("")
    return "\n".join(lines) + "\n"


def save_report_checkpoint(output_dir: Path, report: Dict[str, Any], stamp: str) -> None:
    json_path = output_dir / f"misroute_intents_full_e2e_{stamp}.json"
    md_path = output_dir / f"misroute_intents_full_e2e_{stamp}.md"
    latest_json = output_dir / "misroute_intents_full_e2e_latest.json"
    latest_md = output_dir / "misroute_intents_full_e2e_latest.md"

    payload = json.dumps(report, ensure_ascii=False, indent=2)
    markdown = render_markdown(report)

    json_path.write_text(payload, encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    latest_json.write_text(payload, encoding="utf-8")
    latest_md.write_text(markdown, encoding="utf-8")


def main() -> int:
    from src.bot import SalesBot, setup_autonomous_pipeline
    from src.llm import OllamaLLM

    base_url = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
    output_dir = Path(os.getenv("OUTPUT_DIR", "results"))
    output_dir.mkdir(parents=True, exist_ok=True)

    env_models = [m.strip() for m in os.getenv("MODELS", "").split(",") if m.strip()]
    models = env_models or get_models(base_url)
    if not models:
        raise RuntimeError(f"No models found at {base_url}")

    setup_autonomous_pipeline()

    runs: List[Dict[str, Any]] = []
    summaries: List[Dict[str, Any]] = []
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    print(f"Found {len(models)} models")
    print(f"Running {len(SCENARIOS)} scenarios per model")

    for model in models:
        print(f"\n=== MODEL: {model} ===")
        llm = OllamaLLM(model=model, base_url=base_url, timeout=180)
        bot = SalesBot(llm=llm, flow_name="autonomous", enable_tracing=True)
        results: List[Dict[str, Any]] = []
        passed = 0

        for scenario in SCENARIOS:
            print(f"[{model}] {scenario['id']} ...", flush=True)
            item = run_scenario(bot, scenario)
            results.append(item)
            for turn in item["turns"]:
                print(f"  U{turn['turn']}: {turn['user']}", flush=True)
                print(f"  B{turn['turn']}: {turn['response']}", flush=True)
                print(
                    f"     [intent={turn['intent']} state={turn['state']} action={turn['action']} {turn['elapsed_ms']}ms]",
                    flush=True,
                )
            if item["passed"]:
                passed += 1
                print(
                    f"  PASS intent={item['final_intent']} action={item['final_action']}",
                    flush=True,
                )
            else:
                print(
                    f"  FAIL intent={item['final_intent']} action={item['final_action']}",
                    flush=True,
                )

            current_total = len(results)
            report = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "models": models,
                "scenario_count": len(SCENARIOS),
                "summaries": summaries + [{
                    "model": model,
                    "passed": passed,
                    "total": current_total,
                    "pass_rate": round((passed / current_total) * 100, 1),
                }],
                "runs": runs + [{"model": model, "results": results}],
            }
            save_report_checkpoint(output_dir, report, stamp)

        total = len(results)
        summaries.append(
            {
                "model": model,
                "passed": passed,
                "total": total,
                "pass_rate": round((passed / total) * 100, 1),
            }
        )
        runs.append({"model": model, "results": results})

    report = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "models": models,
        "scenario_count": len(SCENARIOS),
        "summaries": summaries,
        "runs": runs,
    }

    save_report_checkpoint(output_dir, report, stamp)
    json_path = output_dir / f"misroute_intents_full_e2e_{stamp}.json"
    md_path = output_dir / f"misroute_intents_full_e2e_{stamp}.md"

    print(f"\nSaved JSON: {json_path}")
    print(f"Saved MD:   {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
