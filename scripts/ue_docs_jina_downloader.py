from __future__ import annotations

import argparse
import json
import re
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; UE5JinaDownloader/1.0)"}
JINA_PREFIX = "https://r.jina.ai/http://"
UE_ROOT = "https://dev.epicgames.com/documentation/en-us/unreal-engine"
DEFAULT_VERSIONS = ["5.7", "5.6", "5.5", "5.4", "5.3", "5.2", "5.1", "5.0"]
SEED_PATHS = [
    "",
    "/whats-new",
    "/get-started",
    "/understanding-the-basics-of-unreal-engine",
    "/working-with-content-in-unreal-engine",
    "/building-virtual-worlds-in-unreal-engine",
    "/designing-visuals-rendering-and-graphics-with-unreal-engine",
    "/creating-visual-effects-in-niagara-for-unreal-engine",
    "/gameplay-tutorials-for-unreal-engine",
    "/blueprints-visual-scripting-in-unreal-engine",
    "/programming-with-cplusplus-in-unreal-engine",
    "/gameplay-systems-in-unreal-engine",
    "/API",
    "/BlueprintAPI",
    "/PythonAPI",
    "/WebAPI",
    "/node-reference",
]
URL_RE = re.compile(
    r"\((https://dev\.epicgames\.com/documentation/en-us/unreal-engine[^\s)]+)"
    r'(?:\s+(?:"[^"]*"|\'[^\']*\'))?\)'
)
GENERIC_DOC_TITLE = "Documentation | Epic Developer Community"
BLOCKED_MARKERS = (
    "Warning: This page maybe requiring CAPTCHA",
    "Error: 403 | Epic Developer Community",
    "### Access not allowed",
    "**Error loading document**",
)


@dataclass(slots=True)
class PageRecord:
    version: str
    source_url: str
    request_url: str
    title: str
    fetched_at: str
    link_count: int
    content_length: int
    path: str


def build_session() -> requests.Session:
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.headers.update(HEADERS)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def canonicalize_url(url: str) -> str:
    split = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(split.query, keep_blank_values=True) if k != "application_version"]
    return urlunsplit((split.scheme, split.netloc, split.path.rstrip("/"), urlencode(query), ""))


def apply_version(url: str, version: str) -> str:
    split = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(split.query, keep_blank_values=True) if k != "application_version"]
    query.append(("application_version", version))
    return urlunsplit((split.scheme, split.netloc, split.path.rstrip("/"), urlencode(query), ""))


def output_rel_path(source_url: str) -> Path:
    split = urlsplit(canonicalize_url(source_url))
    prefix = "/documentation/en-us/unreal-engine"
    path = split.path.rstrip("/")
    if path == prefix:
        return Path("index")
    relative = path[len(prefix):].lstrip("/")
    return Path(relative or "index")


def jina_url(source_url: str) -> str:
    return f"{JINA_PREFIX}{source_url}"


def parse_jina_markdown(text: str) -> tuple[str, str, str]:
    title = ""
    source_url = ""
    markdown = text
    if text.startswith("Title: "):
        title_end = text.find("\n")
        title = text[len("Title: "):title_end].strip()
    source_marker = "\nURL Source: "
    source_idx = text.find(source_marker)
    if source_idx != -1:
        source_line_end = text.find("\n", source_idx + len(source_marker))
        source_url = text[source_idx + len(source_marker):source_line_end].strip()
    content_marker = "\nMarkdown Content:\n"
    content_idx = text.find(content_marker)
    if content_idx != -1:
        markdown = text[content_idx + len(content_marker):]
    return title, source_url, markdown


def is_blocked_jina_payload(title: str, markdown: str, raw_response: str) -> bool:
    if title == GENERIC_DOC_TITLE:
        return True
    payload = "\n".join((raw_response, markdown))
    return any(marker in payload for marker in BLOCKED_MARKERS)


def extract_links(markdown: str, version: str) -> list[str]:
    urls = []
    for raw in URL_RE.findall(markdown):
        if not raw.startswith(UE_ROOT):
            continue
        urls.append(apply_version(canonicalize_url(raw), version))
    deduped = []
    seen = set()
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        deduped.append(url)
    return deduped


def save_page(output_dir: Path, record: PageRecord, markdown: str, raw_response: str) -> None:
    page_dir = output_dir / record.version / record.path
    page_dir.mkdir(parents=True, exist_ok=True)
    (page_dir / "content.md").write_text(markdown, encoding="utf-8")
    (page_dir / "raw.txt").write_text(raw_response, encoding="utf-8")
    (page_dir / "meta.json").write_text(json.dumps(asdict(record), ensure_ascii=False, indent=2), encoding="utf-8")


def page_is_valid(page_dir: Path) -> bool:
    meta_path = page_dir / "meta.json"
    if not meta_path.exists():
        return False
    try:
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False

    title = str(payload.get("title", "")).strip()
    if title == GENERIC_DOC_TITLE:
        return False

    raw_path = page_dir / "raw.txt"
    content_path = page_dir / "content.md"
    try:
        raw_response = raw_path.read_text(encoding="utf-8") if raw_path.exists() else ""
        markdown = content_path.read_text(encoding="utf-8") if content_path.exists() else ""
    except OSError:
        return False
    return not is_blocked_jina_payload(title, markdown, raw_response)


def page_exists(output_dir: Path, version: str, rel_path: Path) -> bool:
    return page_is_valid(output_dir / version / rel_path)


def append_jsonl(path: Path, payload: object) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False))
        handle.write("\n")


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def crawl_version(
    session: requests.Session,
    output_dir: Path,
    version: str,
    page_delay: float,
    max_pages: int,
    manifest_path: Path,
    summary: dict[str, int | str | list[str]],
) -> None:
    queue = deque(apply_version(f"{UE_ROOT}{path}", version) for path in SEED_PATHS)
    seen = set()
    count = 0

    while queue:
        request_url = queue.popleft()
        canonical_request = apply_version(canonicalize_url(request_url), version)
        if canonical_request in seen:
            continue
        seen.add(canonical_request)

        rel_path = output_rel_path(canonical_request)
        if page_exists(output_dir, version, rel_path):
            summary["skipped_existing"] += 1
            continue

        count += 1
        if max_pages > 0 and count > max_pages:
            break

        print(f"[{version}] fetch {canonical_request}", flush=True)
        try:
            response = session.get(jina_url(canonical_request), timeout=120)
            response.raise_for_status()
            title, source_url, markdown = parse_jina_markdown(response.text)
            if is_blocked_jina_payload(title, markdown, response.text):
                raise RuntimeError("blocked or incomplete Jina payload")
            source_url = source_url or canonical_request
            links = extract_links(markdown, version)
            for link in links:
                if link not in seen:
                    queue.append(link)

            record = PageRecord(
                version=version,
                source_url=source_url,
                request_url=canonical_request,
                title=title,
                fetched_at=datetime.now(UTC).isoformat(),
                link_count=len(links),
                content_length=len(markdown),
                path=rel_path.as_posix(),
            )
            save_page(output_dir, record, markdown, response.text)
            append_jsonl(manifest_path, asdict(record))
            summary["saved_pages"] += 1
        except Exception as exc:
            append_jsonl(
                manifest_path,
                {
                    "version": version,
                    "request_url": canonical_request,
                    "error": str(exc),
                    "fetched_at": datetime.now(UTC).isoformat(),
                },
            )
            summary["failed_pages"] += 1
        finally:
            write_json(output_dir / "summary.json", summary)
            if page_delay:
                time.sleep(page_delay)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download UE5 documentation via r.jina.ai reader.")
    parser.add_argument("--output-dir", default="downloads/ue5-docs-jina")
    parser.add_argument("--versions", default=",".join(DEFAULT_VERSIONS))
    parser.add_argument("--page-delay", type=float, default=0.2)
    parser.add_argument("--max-pages-per-version", type=int, default=0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.jsonl"
    versions = [item.strip() for item in args.versions.split(",") if item.strip()]
    summary: dict[str, int | str | list[str]] = {
        "started_at": datetime.now(UTC).isoformat(),
        "versions": versions,
        "saved_pages": 0,
        "failed_pages": 0,
        "skipped_existing": 0,
    }
    write_json(output_dir / "summary.json", summary)

    session = build_session()
    for version in versions:
        crawl_version(
            session=session,
            output_dir=output_dir,
            version=version,
            page_delay=args.page_delay,
            max_pages=args.max_pages_per_version,
            manifest_path=manifest_path,
            summary=summary,
        )

    summary["finished_at"] = datetime.now(UTC).isoformat()
    write_json(output_dir / "summary.json", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
