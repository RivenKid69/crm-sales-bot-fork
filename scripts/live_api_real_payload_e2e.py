#!/usr/bin/env python3
"""
Боевой E2E-прогон через реальный HTTP API с payload, максимально близким к продовому.

Что делает:
- проверяет `/health` и `/ready` у живого сервера;
- валидирует, что сервер поднят на ожидаемой модели;
- отправляет диалог как последовательность реальных POST-запросов;
- на каждый ход шлёт payload ровно в Sula-формате:
  [
    {
      "id": "...",
      "timestamp": 1773139858523,
      "session": "BOT_6921_test",
      "client_text": "Здравствуйте, я из Астаны.",
      "cleint_phone": "77710107606"
    }
  ]
- сохраняет сырой trace request/response для последующего аудита.

Рекомендуемый запуск внутри docker-сети:
  docker run --rm --network crm-sales-bot-fork_default \
    -e API_KEY=change-me-in-production \
    -v "$PWD":/app -w /app crm-sales-bot-fork-bot \
    python3 -u scripts/live_api_real_payload_e2e.py

Если бот-контейнер уже собран в той же сети и использует:
  OLLAMA_BASE_URL=http://ollama:11434
  TEI_EMBED_URL=http://tei-embed:80
  TEI_RERANK_URL=http://tei-rerank:80
то этот скрипт будет бить в тот же runtime, что и реальные входящие запросы.

Позже сюда можно либо вставить реальный диалог в DEFAULT_DIALOGUE_EVENTS,
либо передать файл через --events-file.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests


def _parse_timeout(value: Any) -> float | None:
    if value in (None, "", 0, "0", "none", "None", "null", "Null"):
        return None
    return float(value)


DEFAULT_PROCESS_URL = os.environ.get("BOT_PROCESS_URL", "http://bot:8000/api/v1/process")
DEFAULT_EXPECTED_MODEL = os.environ.get("EXPECTED_MODEL", "qwen3.5:27b")
DEFAULT_API_KEY = os.environ.get("API_KEY", "change-me-in-production")
DEFAULT_TIMEOUT_SECONDS_RAW = os.environ.get("E2E_HTTP_TIMEOUT_SECONDS", "180")
DEFAULT_TIMEOUT_SECONDS = _parse_timeout(DEFAULT_TIMEOUT_SECONDS_RAW)
DEFAULT_INTER_TURN_DELAY_MS = int(os.environ.get("E2E_INTER_TURN_DELAY_MS", "0"))
DEFAULT_OUTPUT_ROOT = Path(os.environ.get("E2E_OUTPUT_DIR", "results/live_api_real_payload"))


# Сюда можно вставить конкретный диалог, если не использовать --events-file.
DEFAULT_DIALOGUE_EVENTS: list[dict[str, Any]] = [
    {
        "id": "evt_live_round_001",
        "timestamp": 1773139858523,
        "session": "BOT_6921_test",
        "client_text": "Здравствуйте выставите счет вечером оплачу\n\nМоноблок принтер и этикеток, чеков и сканер",
        "cleint_phone": "87772933632",
    },
    {
        "id": "evt_live_round_002",
        "timestamp": 1773139859523,
        "session": "BOT_6921_test",
        "client_text": "Мне ящик для денег не нужен",
        "cleint_phone": "87772933632",
    },
    {
        "id": "evt_live_round_003",
        "timestamp": 1773139860523,
        "session": "BOT_6921_test",
        "client_text": "87772933632 . Иин 980709450787",
        "cleint_phone": "87772933632",
    },
    {
        "id": "evt_live_round_004",
        "timestamp": 1773139861523,
        "session": "BOT_6921_test",
        "client_text": "У вас же в программе есть бонусная система ? Там какой то определены или я могу сама решить сколько процентов",
        "cleint_phone": "87772933632",
    }
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Боевой E2E через реальный CRM Sales Bot API в продовом Sula-формате."
    )
    parser.add_argument(
        "--process-url",
        default=DEFAULT_PROCESS_URL,
        help="Полный URL process endpoint. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--api-key",
        default=DEFAULT_API_KEY,
        help="Bearer API key. По умолчанию берётся из API_KEY.",
    )
    parser.add_argument(
        "--events-file",
        default="",
        help="JSON-файл с диалогом. Поддерживается top-level list или {'events': [...]}",
    )
    parser.add_argument(
        "--session",
        default="",
        help="Если задан, принудительно подменяет session во всех событиях.",
    )
    parser.add_argument(
        "--phone",
        default="",
        help="Если задан, принудительно подменяет cleint_phone/client_phone во всех событиях.",
    )
    parser.add_argument(
        "--timestamp-start-ms",
        type=int,
        default=0,
        help="Стартовый timestamp для автогенерации, если в событиях он отсутствует.",
    )
    parser.add_argument(
        "--timestamp-step-ms",
        type=int,
        default=1000,
        help="Шаг между auto-generated timestamp'ами.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=_parse_timeout,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="HTTP timeout на один запрос; 0/none = без timeout.",
    )
    parser.add_argument(
        "--inter-turn-delay-ms",
        type=int,
        default=DEFAULT_INTER_TURN_DELAY_MS,
        help="Пауза между запросами. По умолчанию 0.",
    )
    parser.add_argument(
        "--heartbeat-seconds",
        type=float,
        default=30.0,
        help="Как часто печатать heartbeat во время ожидания ответа на один ход.",
    )
    parser.add_argument(
        "--respect-input-gaps",
        action="store_true",
        help="Если включено, между ходами спит на разницу timestamp'ов из payload.",
    )
    parser.add_argument(
        "--max-gap-sleep-ms",
        type=int,
        default=5000,
        help="Потолок sleep при --respect-input-gaps.",
    )
    parser.add_argument(
        "--expected-model",
        default=DEFAULT_EXPECTED_MODEL,
        help="Ожидаемая модель в /health. Пустая строка отключает проверку.",
    )
    parser.add_argument(
        "--allow-not-ready",
        action="store_true",
        help="Не падать, если /ready вернул не 200. По умолчанию прогон блокируется.",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Куда сохранить trace. По умолчанию results/live_api_real_payload/<timestamp>",
    )
    return parser.parse_args()


def derive_service_root(process_url: str) -> str:
    parsed = urlsplit(process_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Некорректный process URL: {process_url}")
    return f"{parsed.scheme}://{parsed.netloc}"


def load_events(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.events_file:
        raw = json.loads(Path(args.events_file).read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            raw = raw.get("events", [])
        if not isinstance(raw, list):
            raise ValueError("events-file должен содержать list или {'events': list}")
        events = raw
    else:
        events = list(DEFAULT_DIALOGUE_EVENTS)

    if not events:
        raise ValueError("Список событий пуст")
    return normalize_events(
        events,
        session_override=args.session,
        phone_override=args.phone,
        timestamp_start_ms=args.timestamp_start_ms,
        timestamp_step_ms=args.timestamp_step_ms,
    )


def normalize_events(
    events: list[dict[str, Any]],
    *,
    session_override: str,
    phone_override: str,
    timestamp_start_ms: int,
    timestamp_step_ms: int,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    next_auto_ts = timestamp_start_ms or int(time.time() * 1000)

    for index, item in enumerate(events, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Событие #{index} должно быть object, получено: {type(item).__name__}")

        session = str(session_override or item.get("session") or "").strip()
        phone = str(phone_override or item.get("cleint_phone") or item.get("client_phone") or "").strip()
        client_text = str(item.get("client_text") or item.get("text") or "").strip()
        event_id = str(item.get("id") or f"evt_auto_{index:03d}_{uuid.uuid4().hex[:12]}")

        if not session:
            raise ValueError(f"Событие #{index}: отсутствует session")
        if not phone:
            raise ValueError(f"Событие #{index}: отсутствует cleint_phone/client_phone")
        if not client_text:
            raise ValueError(f"Событие #{index}: отсутствует client_text/text")

        raw_timestamp = item.get("timestamp")
        if raw_timestamp in (None, ""):
            timestamp = next_auto_ts
        else:
            try:
                timestamp = int(raw_timestamp)
            except (TypeError, ValueError) as err:
                raise ValueError(f"Событие #{index}: timestamp должен быть integer") from err

        next_auto_ts = timestamp + max(1, int(timestamp_step_ms))

        normalized.append(
            {
                "id": event_id,
                "timestamp": timestamp,
                "session": session,
                "client_text": client_text,
                "cleint_phone": phone,
            }
        )

    return normalized


def fetch_json_or_text(response: requests.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return response.text


def ensure_output_dir(path_arg: str) -> Path:
    if path_arg:
        out_dir = Path(path_arg)
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = DEFAULT_OUTPUT_ROOT / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def preflight(
    session: requests.Session,
    *,
    process_url: str,
    api_key: str,
    expected_model: str,
    timeout_seconds: float | None,
    allow_not_ready: bool,
) -> dict[str, Any]:
    del api_key  # health/ready are public in current API
    root = derive_service_root(process_url)
    health_url = f"{root}/health"
    ready_url = f"{root}/ready"

    health_response = session.get(health_url, timeout=timeout_seconds)
    health_payload = fetch_json_or_text(health_response)
    if health_response.status_code != 200:
        raise RuntimeError(f"/health вернул {health_response.status_code}: {health_payload}")

    if expected_model:
        actual_model = ""
        if isinstance(health_payload, dict):
            actual_model = str(health_payload.get("model") or "")
        if actual_model != expected_model:
            raise RuntimeError(
                f"Модель сервера не совпадает: expected='{expected_model}', actual='{actual_model}'"
            )

    ready_response = session.get(ready_url, timeout=timeout_seconds)
    ready_payload = fetch_json_or_text(ready_response)
    if ready_response.status_code != 200 and not allow_not_ready:
        raise RuntimeError(f"/ready вернул {ready_response.status_code}: {ready_payload}")

    if isinstance(ready_payload, dict) and not allow_not_ready:
        dependencies = ready_payload.get("dependencies") or {}
        failed_dependencies = [
            name for name, value in dependencies.items() if not bool(value)
        ]
        warmup_status = str((ready_payload.get("warmup") or {}).get("status") or "")
        if failed_dependencies:
            raise RuntimeError(
                f"/ready dependencies not ready: {', '.join(failed_dependencies)}"
            )
        if warmup_status and warmup_status != "ready":
            raise RuntimeError(f"/ready warmup status is '{warmup_status}', expected 'ready'")

    return {
        "health_url": health_url,
        "ready_url": ready_url,
        "health_status": health_response.status_code,
        "health_payload": health_payload,
        "ready_status": ready_response.status_code,
        "ready_payload": ready_payload,
    }


def extract_ai_text(response_payload: Any) -> str:
    if isinstance(response_payload, list) and response_payload:
        item = response_payload[-1]
        if isinstance(item, dict):
            return str(item.get("ai_text") or "")
    if isinstance(response_payload, dict):
        return str(response_payload.get("ai_text") or response_payload.get("answer") or "")
    return ""


def post_with_heartbeat(
    session: requests.Session,
    *,
    url: str,
    headers: dict[str, str],
    payload: Any,
    timeout_seconds: float | None,
    heartbeat_seconds: float,
    turn_number: int,
) -> tuple[requests.Response, int]:
    started = time.perf_counter()
    heartbeat_seconds = max(1.0, float(heartbeat_seconds))

    def _do_post() -> requests.Response:
        return session.post(
            url,
            headers=headers,
            json=payload,
            timeout=timeout_seconds,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_do_post)
        while True:
            try:
                response = future.result(timeout=heartbeat_seconds)
                latency_ms = int((time.perf_counter() - started) * 1000)
                return response, latency_ms
            except concurrent.futures.TimeoutError:
                elapsed = int(time.perf_counter() - started)
                print(f"[turn {turn_number:02d}] waiting... elapsed={elapsed}s")


def render_markdown(
    *,
    process_url: str,
    preflight_data: dict[str, Any],
    events: list[dict[str, Any]],
    trace: list[dict[str, Any]],
) -> str:
    lines: list[str] = [
        "# Live API Real-Payload E2E",
        "",
        f"- Process URL: `{process_url}`",
        f"- Total turns: `{len(events)}`",
        f"- Generated at: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`",
        "",
        "## Preflight",
        "",
        f"- /health status: `{preflight_data['health_status']}`",
        f"- /ready status: `{preflight_data['ready_status']}`",
        f"- /health payload: `{json.dumps(preflight_data['health_payload'], ensure_ascii=False)}`",
        f"- /ready payload: `{json.dumps(preflight_data['ready_payload'], ensure_ascii=False)}`",
        "",
        "## Transcript",
        "",
    ]

    for item in trace:
        lines.extend(
            [
                f"### Turn {item['turn']}",
                "",
                f"- Request event id: `{item['request_event']['id']}`",
                f"- Session: `{item['request_event']['session']}`",
                f"- Phone: `{item['request_event']['cleint_phone']}`",
                f"- Timestamp: `{item['request_event']['timestamp']}`",
                f"- HTTP status: `{item['status_code']}`",
                f"- Latency ms: `{item['latency_ms']}`",
                "",
                f"Client: {item['request_event']['client_text']}",
                "",
                f"Bot: {item['ai_text'] or '<empty>'}",
                "",
            ]
        )

    return "\n".join(lines).strip() + "\n"


def main() -> int:
    args = parse_args()
    output_dir = ensure_output_dir(args.output_dir)
    events = load_events(args)

    headers = {
        "Authorization": f"Bearer {args.api_key}",
        "Content-Type": "application/json",
    }

    trace: list[dict[str, Any]] = []
    session = requests.Session()

    try:
        preflight_data = preflight(
            session,
            process_url=args.process_url,
            api_key=args.api_key,
            expected_model=args.expected_model.strip(),
            timeout_seconds=args.timeout_seconds,
            allow_not_ready=args.allow_not_ready,
        )

        print(f"[preflight] health={preflight_data['health_status']} ready={preflight_data['ready_status']}")

        previous_timestamp = None
        for turn_number, event in enumerate(events, start=1):
            if previous_timestamp is not None and args.respect_input_gaps:
                raw_gap = max(0, int(event["timestamp"]) - int(previous_timestamp))
                sleep_ms = min(raw_gap, max(0, args.max_gap_sleep_ms))
                if sleep_ms > 0:
                    time.sleep(sleep_ms / 1000.0)
            elif args.inter_turn_delay_ms > 0 and turn_number > 1:
                time.sleep(args.inter_turn_delay_ms / 1000.0)

            payload = [event]
            response, latency_ms = post_with_heartbeat(
                session,
                url=args.process_url,
                headers=headers,
                payload=payload,
                timeout_seconds=args.timeout_seconds,
                heartbeat_seconds=args.heartbeat_seconds,
                turn_number=turn_number,
            )
            response_payload = fetch_json_or_text(response)
            ai_text = extract_ai_text(response_payload)

            trace_item = {
                "turn": turn_number,
                "request_event": event,
                "request_payload": payload,
                "status_code": response.status_code,
                "latency_ms": latency_ms,
                "response_payload": response_payload,
                "ai_text": ai_text,
            }
            trace.append(trace_item)

            print(f"[turn {turn_number:02d}] status={response.status_code} latency_ms={latency_ms}")
            print(f"  client: {event['client_text']}")
            print(f"  bot   : {ai_text or '<empty>'}")

            if response.status_code != 200:
                raise RuntimeError(
                    f"Ход {turn_number} упал: HTTP {response.status_code}, payload={response_payload}"
                )

            previous_timestamp = event["timestamp"]

        summary = {
            "process_url": args.process_url,
            "expected_model": args.expected_model,
            "output_dir": str(output_dir),
            "turns_sent": len(events),
            "session_ids": sorted({event["session"] for event in events}),
            "phones": sorted({event["cleint_phone"] for event in events}),
        }

        (output_dir / "events.normalized.json").write_text(
            json.dumps(events, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (output_dir / "preflight.json").write_text(
            json.dumps(preflight_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (output_dir / "trace.json").write_text(
            json.dumps(trace, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (output_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (output_dir / "transcript.md").write_text(
            render_markdown(
                process_url=args.process_url,
                preflight_data=preflight_data,
                events=events,
                trace=trace,
            ),
            encoding="utf-8",
        )

        print(f"[done] trace saved to {output_dir}")
        return 0

    except Exception as exc:
        failure_payload = {
            "error": str(exc),
            "process_url": args.process_url,
            "trace_so_far": trace,
        }
        (output_dir / "failure.json").write_text(
            json.dumps(failure_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[error] {exc}", file=sys.stderr)
        print(f"[error] partial trace saved to {output_dir}", file=sys.stderr)
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
