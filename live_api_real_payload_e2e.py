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
    python3 -u live_api_real_payload_e2e.py

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
DEFAULT_EXPECTED_MODEL = os.environ.get("EXPECTED_MODEL", "gemma4:31b")
DEFAULT_API_KEY = os.environ.get("API_KEY", "change-me-in-production")
DEFAULT_TIMEOUT_SECONDS_RAW = os.environ.get("E2E_HTTP_TIMEOUT_SECONDS", "180")
DEFAULT_TIMEOUT_SECONDS = _parse_timeout(DEFAULT_TIMEOUT_SECONDS_RAW)
DEFAULT_INTER_TURN_DELAY_MS = int(os.environ.get("E2E_INTER_TURN_DELAY_MS", "0"))
DEFAULT_WAIT_READY_TIMEOUT_SECONDS = float(
    os.environ.get("E2E_WAIT_READY_TIMEOUT_SECONDS", "180")
)
DEFAULT_WAIT_READY_POLL_SECONDS = float(
    os.environ.get("E2E_WAIT_READY_POLL_SECONDS", "5")
)
DEFAULT_OUTPUT_ROOT = Path(os.environ.get("E2E_OUTPUT_DIR", "results/live_api_real_payload"))
TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"
DEFAULT_USER_AGENT = os.environ.get(
    "E2E_USER_AGENT",
    "CRM-Sales-Bot-Live-E2E/1.0 (+real-payload-sula)",
)
DEFAULT_CLIENT_IP = os.environ.get("E2E_CLIENT_IP", "203.0.113.77")
DEFAULT_REQUEST_MODE = os.environ.get("E2E_REQUEST_MODE", "auto")
DEFAULT_FLOW_NAME = os.environ.get("E2E_FLOW_NAME", "")
DEBUG_TRACE_HEADER = "X-E2E-Debug-Trace"
DEBUG_TRACE_ENABLED_VALUE = "1"


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
        "--request-mode",
        choices=("auto", "sula", "default"),
        default=DEFAULT_REQUEST_MODE,
        help=(
            "Какой формат тела запроса использовать. "
            "`sula` — legacy Sula payload, `default` — каноничный ProcessRequest, "
            "`auto` переключается на `default`, если задан flow_name или outbound-start."
        ),
    )
    parser.add_argument(
        "--prod-like",
        action="store_true",
        help="Включить режим, максимально похожий на реальный внешний Sula-клиент.",
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
        "--flow-name",
        default=DEFAULT_FLOW_NAME,
        help="Явный flow_name для каноничного ProcessRequest. Например: pilot_survey.",
    )
    parser.add_argument(
        "--outbound-start",
        action="store_true",
        help=(
            "Перед первым пользовательским ходом отправить отдельный ProcessRequest со start=true. "
            "Используется для flow вроде pilot_survey."
        ),
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
        "--wait-ready-timeout-seconds",
        type=float,
        default=DEFAULT_WAIT_READY_TIMEOUT_SECONDS,
        help="Сколько максимум ждать readiness перед падением. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--wait-ready-poll-seconds",
        type=float,
        default=DEFAULT_WAIT_READY_POLL_SECONDS,
        help="Интервал опроса /ready во время ожидания. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help=(
            "Базовое имя/путь для trace. Timestamp `YYYYMMDD_HHMMSS` добавляется всегда: "
            "по умолчанию как имя каталога, при `--output-dir` как suffix последнего сегмента пути."
        ),
    )
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Не делать /health и /ready перед прогоном.",
    )
    parser.add_argument(
        "--rebase-timestamps-to-now",
        action="store_true",
        help="Пересчитать timestamps на текущее время, сохраняя относительные gaps.",
    )
    parser.add_argument(
        "--append-run-id-to-session",
        action="store_true",
        help="Добавить уникальный suffix к session, чтобы не смешивать прогон с предыдущими.",
    )
    parser.add_argument(
        "--randomize-event-ids",
        action="store_true",
        help="Сгенерировать новые event id под этот запуск.",
    )
    parser.add_argument(
        "--user-agent",
        default=DEFAULT_USER_AGENT,
        help="User-Agent для HTTP-запросов. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--client-ip",
        default=DEFAULT_CLIENT_IP,
        help="Какой IP прокинуть в X-Forwarded-For/X-Real-IP. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--header",
        action="append",
        default=[],
        help="Дополнительный HTTP header в формате 'Name: value'. Можно передавать несколько раз.",
    )
    return parser.parse_args()


def derive_service_root(process_url: str) -> str:
    parsed = urlsplit(process_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Некорректный process URL: {process_url}")
    return f"{parsed.scheme}://{parsed.netloc}"


def default_sula_process_url(process_url: str) -> str:
    parsed = urlsplit(process_url)
    path = parsed.path or ""
    if path.endswith("/api/v1/process"):
        return parsed._replace(path="/api/v1/process/sula").geturl()
    return process_url


def make_run_id() -> str:
    stamp = datetime.now().strftime(TIMESTAMP_FORMAT)
    return f"{stamp}_{uuid.uuid4().hex[:8]}"


def apply_prod_like_defaults(args: argparse.Namespace) -> None:
    if not args.prod_like:
        return

    args.process_url = default_sula_process_url(args.process_url)
    args.rebase_timestamps_to_now = True
    args.append_run_id_to_session = True
    args.randomize_event_ids = True
    args.respect_input_gaps = True
    args.max_gap_sleep_ms = max(args.max_gap_sleep_ms, 30_000)
    if args.expected_model == DEFAULT_EXPECTED_MODEL and "EXPECTED_MODEL" not in os.environ:
        args.expected_model = ""


def resolve_request_mode(args: argparse.Namespace) -> str:
    mode = str(args.request_mode or "auto").strip().lower()
    if mode in {"sula", "default"}:
        return mode
    if str(args.flow_name or "").strip() or bool(args.outbound_start):
        return "default"
    return "sula"


def parse_extra_headers(raw_headers: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for raw in raw_headers:
        name, sep, value = raw.partition(":")
        if not sep:
            raise ValueError(f"Некорректный --header '{raw}', ожидается 'Name: value'")
        header_name = name.strip()
        if not header_name:
            raise ValueError(f"Некорректный --header '{raw}', имя header пустое")
        parsed[header_name] = value.strip()
    return parsed


def rebase_timestamps(events: list[dict[str, Any]], *, base_timestamp_ms: int) -> None:
    if not events:
        return

    source_base = int(events[0]["timestamp"])
    for event in events:
        gap_ms = max(0, int(event["timestamp"]) - source_base)
        event["timestamp"] = base_timestamp_ms + gap_ms


def apply_run_identity(
    events: list[dict[str, Any]],
    *,
    run_id: str,
    append_run_id_to_session: bool,
    randomize_event_ids: bool,
    rebase_timestamps_to_now: bool,
) -> list[dict[str, Any]]:
    prepared = [dict(item) for item in events]

    if rebase_timestamps_to_now:
        rebase_timestamps(prepared, base_timestamp_ms=int(time.time() * 1000))

    if append_run_id_to_session:
        for event in prepared:
            base_session = str(event["session"]).strip()
            event["session"] = f"{base_session}_{run_id}"

    if randomize_event_ids:
        for index, event in enumerate(prepared, start=1):
            event["id"] = f"{event['id']}_{run_id}_{index:02d}_{uuid.uuid4().hex[:6]}"

    return prepared


def build_base_headers(args: argparse.Namespace) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {args.api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": args.user_agent,
        DEBUG_TRACE_HEADER: DEBUG_TRACE_ENABLED_VALUE,
    }
    client_ip = str(args.client_ip or "").strip()
    if client_ip:
        headers["X-Forwarded-For"] = client_ip
        headers["X-Real-IP"] = client_ip
    headers.update(parse_extra_headers(args.header))
    return headers


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


def build_default_process_payload(
    event: dict[str, Any],
    *,
    flow_name: str,
    start: bool,
) -> dict[str, Any]:
    return {
        "session_id": event["session"],
        "user_id": event["cleint_phone"],
        "flow_name": str(flow_name or ""),
        "start": bool(start),
        "message": {
            "text": "" if start else event["client_text"],
            "timestamp_ms": int(event["timestamp"]),
        },
    }


def build_turn_requests(
    events: list[dict[str, Any]],
    *,
    flow_name: str,
    request_mode: str,
    outbound_start: bool,
) -> list[dict[str, Any]]:
    if not events:
        return []

    requests_to_send: list[dict[str, Any]] = []
    if outbound_start:
        if request_mode != "default":
            raise ValueError("outbound-start поддерживается только в request-mode=default")
        first = events[0]
        start_event = {
            "id": f"{first['id']}_start",
            "timestamp": max(0, int(first["timestamp"]) - 1),
            "session": first["session"],
            "client_text": "",
            "cleint_phone": first["cleint_phone"],
            "kind": "outbound_start",
        }
        requests_to_send.append(
            {
                "kind": "outbound_start",
                "event": start_event,
                "payload": build_default_process_payload(
                    start_event,
                    flow_name=flow_name,
                    start=True,
                ),
            }
        )

    for event in events:
        kind = "user_turn"
        if request_mode == "default":
            payload = build_default_process_payload(
                event,
                flow_name=flow_name,
                start=False,
            )
        else:
            payload = [event]
        requests_to_send.append(
            {
                "kind": kind,
                "event": event,
                "payload": payload,
            }
        )
    return requests_to_send


def ensure_output_dir(path_arg: str) -> Path:
    stamp = datetime.now().strftime(TIMESTAMP_FORMAT)
    if path_arg:
        requested = Path(path_arg)
        out_dir = requested.with_name(f"{requested.name}_{stamp}")
    else:
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
    wait_ready_timeout_seconds: float,
    wait_ready_poll_seconds: float,
) -> dict[str, Any]:
    del api_key  # health/ready are public in current API
    root = derive_service_root(process_url)
    health_url = f"{root}/health"
    ready_url = f"{root}/ready"

    try:
        health_response = session.get(health_url, timeout=timeout_seconds)
    except requests.RequestException as err:
        raise RuntimeError(
            "Не удалось достучаться до API health endpoint. "
            f"health_url='{health_url}', error='{err}'. "
            "Проверьте, что e2e запущен в той же docker-сети, где доступен alias `bot`, "
            "и что сам bot-container уже поднят."
        ) from err
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

    ready_response: requests.Response | None = None
    ready_payload: Any = None
    deadline = time.monotonic() + max(0.0, float(wait_ready_timeout_seconds))
    poll_seconds = max(0.5, float(wait_ready_poll_seconds))

    while True:
        try:
            ready_response = session.get(ready_url, timeout=timeout_seconds)
        except requests.RequestException as err:
            if allow_not_ready or time.monotonic() >= deadline:
                raise RuntimeError(
                    "Не удалось достучаться до API ready endpoint. "
                    f"ready_url='{ready_url}', error='{err}'."
                ) from err
            print(f"[preflight] /ready temporary error: {err}; retrying in {poll_seconds:.1f}s")
            time.sleep(poll_seconds)
            continue

        ready_payload = fetch_json_or_text(ready_response)
        if allow_not_ready or ready_response.status_code == 200:
            break

        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"/ready не стал ready за {wait_ready_timeout_seconds:.1f}s: "
                f"status={ready_response.status_code}, payload={ready_payload}"
            )

        warmup_status = ""
        failed_dependencies: list[str] = []
        if isinstance(ready_payload, dict):
            dependencies = ready_payload.get("dependencies") or {}
            failed_dependencies = [
                name for name, value in dependencies.items() if not bool(value)
            ]
            warmup_status = str((ready_payload.get("warmup") or {}).get("status") or "")

        hint_parts: list[str] = []
        if failed_dependencies:
            hint_parts.append(f"deps={','.join(failed_dependencies)}")
        if warmup_status:
            hint_parts.append(f"warmup={warmup_status}")
        hint_suffix = f" ({'; '.join(hint_parts)})" if hint_parts else ""
        print(
            f"[preflight] /ready={ready_response.status_code}{hint_suffix}; "
            f"retrying in {poll_seconds:.1f}s"
        )
        time.sleep(poll_seconds)

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


def extract_debug_payload(response_payload: Any) -> dict[str, Any]:
    candidate = None
    if isinstance(response_payload, list) and response_payload:
        item = response_payload[-1]
        if isinstance(item, dict):
            candidate = item.get("_debug")
    elif isinstance(response_payload, dict):
        candidate = response_payload.get("_debug")
    return candidate if isinstance(candidate, dict) else {}


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
    run_id: str,
    events: list[dict[str, Any]],
    request_mode: str,
    flow_name: str,
    outbound_start: bool,
    trace: list[dict[str, Any]],
) -> str:
    preflight_skipped = bool(preflight_data.get("skipped"))
    health_status = preflight_data.get("health_status", "skipped")
    ready_status = preflight_data.get("ready_status", "skipped")
    health_payload = preflight_data.get("health_payload", {"skipped": True})
    ready_payload = preflight_data.get("ready_payload", {"skipped": True})

    lines: list[str] = [
        "# Live API Real-Payload E2E",
        "",
        f"- Process URL: `{process_url}`",
        f"- Run ID: `{run_id}`",
        f"- Total turns: `{len(events)}`",
        f"- Request mode: `{request_mode}`",
        f"- Flow name: `{flow_name or '<default>'}`",
        f"- Outbound start: `{bool(outbound_start)}`",
        f"- Generated at: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`",
        "",
        "## Preflight",
        "",
        f"- skipped: `{preflight_skipped}`",
        f"- /health status: `{health_status}`",
        f"- /ready status: `{ready_status}`",
        f"- /health payload: `{json.dumps(health_payload, ensure_ascii=False)}`",
        f"- /ready payload: `{json.dumps(ready_payload, ensure_ascii=False)}`",
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
                f"- Request kind: `{item.get('request_kind', 'user_turn')}`",
                f"- HTTP status: `{item['status_code']}`",
                f"- Latency ms: `{item['latency_ms']}`",
                "",
                f"Client: {item['request_event']['client_text'] or '<outbound_start>'}",
                "",
                f"Bot: {item['ai_text'] or '<empty>'}",
                "",
            ]
        )

    return "\n".join(lines).strip() + "\n"


def main() -> int:
    args = parse_args()
    apply_prod_like_defaults(args)
    request_mode = resolve_request_mode(args)
    output_dir = ensure_output_dir(args.output_dir)
    run_id = make_run_id()
    events = apply_run_identity(
        load_events(args),
        run_id=run_id,
        append_run_id_to_session=args.append_run_id_to_session,
        randomize_event_ids=args.randomize_event_ids,
        rebase_timestamps_to_now=args.rebase_timestamps_to_now,
    )
    turn_requests = build_turn_requests(
        events,
        flow_name=str(args.flow_name or "").strip(),
        request_mode=request_mode,
        outbound_start=bool(args.outbound_start),
    )
    base_headers = build_base_headers(args)

    trace: list[dict[str, Any]] = []
    session = requests.Session()

    try:
        if args.skip_preflight:
            preflight_data = {"skipped": True}
            print("[preflight] skipped")
        else:
            preflight_data = preflight(
                session,
                process_url=args.process_url,
                api_key=args.api_key,
                expected_model=args.expected_model.strip(),
                timeout_seconds=args.timeout_seconds,
                allow_not_ready=args.allow_not_ready,
                wait_ready_timeout_seconds=args.wait_ready_timeout_seconds,
                wait_ready_poll_seconds=args.wait_ready_poll_seconds,
            )
            print(f"[preflight] health={preflight_data['health_status']} ready={preflight_data['ready_status']}")

        previous_timestamp = None
        for turn_number, turn in enumerate(turn_requests, start=1):
            event = turn["event"]
            if previous_timestamp is not None and args.respect_input_gaps:
                raw_gap = max(0, int(event["timestamp"]) - int(previous_timestamp))
                sleep_ms = min(raw_gap, max(0, args.max_gap_sleep_ms))
                if sleep_ms > 0:
                    time.sleep(sleep_ms / 1000.0)
            elif args.inter_turn_delay_ms > 0 and turn_number > 1:
                time.sleep(args.inter_turn_delay_ms / 1000.0)

            payload = [event]
            if request_mode == "default":
                payload = turn["payload"]
            else:
                payload = turn["payload"]
            request_headers = dict(base_headers)
            request_headers["X-Request-ID"] = f"live-e2e-{run_id}-turn-{turn_number:02d}"
            sent_at = datetime.now().isoformat(timespec="seconds")
            response, latency_ms = post_with_heartbeat(
                session,
                url=args.process_url,
                headers=request_headers,
                payload=payload,
                timeout_seconds=args.timeout_seconds,
                heartbeat_seconds=args.heartbeat_seconds,
                turn_number=turn_number,
            )
            response_payload = fetch_json_or_text(response)
            ai_text = extract_ai_text(response_payload)
            debug_payload = extract_debug_payload(response_payload)
            decision_trace = debug_payload.get("decision_trace")
            factual_pipeline = {}
            if isinstance(decision_trace, dict):
                response_trace = decision_trace.get("response")
                if isinstance(response_trace, dict):
                    factual_pipeline = response_trace.get("factual_pipeline") or {}
            received_at = datetime.now().isoformat(timespec="seconds")

            trace_item = {
                "turn": turn_number,
                "request_headers": request_headers,
                "request_kind": turn["kind"],
                "request_event": event,
                "request_payload": payload,
                "sent_at": sent_at,
                "received_at": received_at,
                "status_code": response.status_code,
                "latency_ms": latency_ms,
                "response_payload": response_payload,
                "ai_text": ai_text,
            }
            if debug_payload:
                trace_item["debug_payload"] = debug_payload
            if isinstance(decision_trace, dict):
                trace_item["decision_trace"] = decision_trace
            if isinstance(factual_pipeline, dict) and factual_pipeline:
                trace_item["factual_pipeline"] = factual_pipeline
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
            "run_id": run_id,
            "prod_like": bool(args.prod_like),
            "process_url": args.process_url,
            "request_mode": request_mode,
            "flow_name": str(args.flow_name or ""),
            "outbound_start": bool(args.outbound_start),
            "expected_model": args.expected_model,
            "output_dir": str(output_dir),
            "turns_sent": len(turn_requests),
            "session_ids": sorted({event["session"] for event in events}),
            "phones": sorted({event["cleint_phone"] for event in events}),
            "user_agent": args.user_agent,
            "client_ip": args.client_ip,
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
                run_id=run_id,
                events=events,
                request_mode=request_mode,
                flow_name=str(args.flow_name or ""),
                outbound_start=bool(args.outbound_start),
                trace=trace,
            ),
            encoding="utf-8",
        )

        print(f"[done] trace saved to {output_dir}")
        return 0

    except Exception as exc:
        failure_payload = {
            "error": str(exc),
            "run_id": run_id,
            "prod_like": bool(args.prod_like),
            "process_url": args.process_url,
            "events": events,
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
