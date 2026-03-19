from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from html import unescape
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import xml.etree.ElementTree as ET

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

SITEMAP_URL = "https://dev.epicgames.com/documentation/sitemap.xml"
UE_DOC_ROOT = "https://dev.epicgames.com/documentation/en-us/unreal-engine"
DEFAULT_ROOT_URL = (
    "https://dev.epicgames.com/documentation/en-us/unreal-engine/"
    "unreal-engine-5-7-documentation?application_version=5.7"
)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; UE5DocsDownloader/1.0)",
}
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)
NOT_FOUND_MARKERS = (
    "page not found",
    "404",
    "no document found",
)
BLOCKED_MARKERS = (
    "error: 403",
    "access not allowed",
)


@dataclass(slots=True)
class PageRecord:
    base_url: str
    version: str
    url: str
    current_url: str
    title: str
    raw_title: str
    h1: str
    h2: list[str]
    h3: list[str]
    content_text_length: int
    internal_links: list[str]
    status: str
    fetched_at: str
    path: str


def build_session(timeout_retries: int) -> requests.Session:
    retry = Retry(
        total=timeout_retries,
        connect=timeout_retries,
        read=timeout_retries,
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


def parse_sitemap_xml(xml_text: str) -> tuple[str, list[str]]:
    root = ET.fromstring(xml_text)
    namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    if root.tag.endswith("sitemapindex"):
        items = [
            loc.text.strip()
            for loc in root.findall("sm:sitemap/sm:loc", namespace)
            if loc is not None and loc.text
        ]
        return "index", items
    if root.tag.endswith("urlset"):
        items = [
            loc.text.strip()
            for loc in root.findall("sm:url/sm:loc", namespace)
            if loc is not None and loc.text
        ]
        return "urlset", items
    return "unknown", []


def fetch_text(session: requests.Session, url: str, timeout: int) -> str:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    return response.text


def canonicalize_doc_url(url: str) -> str:
    split = urlsplit(url)
    clean_query = [(k, v) for k, v in parse_qsl(split.query, keep_blank_values=True) if k != "application_version"]
    return urlunsplit((split.scheme, split.netloc, split.path.rstrip("/"), urlencode(clean_query), ""))


def apply_application_version(url: str, version: str) -> str:
    split = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(split.query, keep_blank_values=True) if k != "application_version"]
    query.append(("application_version", version))
    return urlunsplit((split.scheme, split.netloc, split.path.rstrip("/"), urlencode(query), ""))


def extract_application_version(url: str) -> str | None:
    for key, value in parse_qsl(urlsplit(url).query, keep_blank_values=True):
        if key == "application_version":
            return value
    return None


def is_ue_doc_url(url: str) -> bool:
    split = urlsplit(url)
    path = split.path.rstrip("/")
    return path == "/documentation/en-us/unreal-engine" or path.startswith("/documentation/en-us/unreal-engine/")


def is_supported_ue5_version(version: str, min_major: int = 5) -> bool:
    parts = version.split(".")
    if not parts or not parts[0].isdigit():
        return False
    return int(parts[0]) >= min_major


def collect_sitemap_urls(
    session: requests.Session,
    sitemap_url: str,
    renderer: SeleniumRenderer,
    timeout: int,
    delay_seconds: float,
    max_sitemaps: int,
) -> list[str]:
    root_kind, root_items = parse_sitemap_xml(fetch_text(session, sitemap_url, timeout))
    if root_kind == "urlset":
        return dedupe_preserve_order(root_items)

    urls: list[str] = []
    unreal_engine_sitemaps = [item for item in root_items if "/sitemaps/unreal_engine/" in item]
    if max_sitemaps > 0:
        unreal_engine_sitemaps = unreal_engine_sitemaps[:max_sitemaps]
    for index, child_sitemap_url in enumerate(unreal_engine_sitemaps, start=1):
        try:
            child_text = renderer.fetch_text(child_sitemap_url)
            child_kind, child_items = parse_sitemap_xml(child_text)
        except Exception as exc:
            print(
                f"[sitemap {index}/{len(unreal_engine_sitemaps)}] skip {child_sitemap_url}: {exc}",
                file=sys.stderr,
            )
            continue
        if child_kind == "urlset":
            urls.extend(child_items)
        if delay_seconds:
            time.sleep(delay_seconds)
    return dedupe_preserve_order(urls)


def dedupe_preserve_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def filter_ue_doc_urls(urls: Iterable[str]) -> list[str]:
    canonical = [canonicalize_doc_url(url) for url in urls if is_ue_doc_url(url)]
    return dedupe_preserve_order(canonical)


def crawl_base_urls(
    renderer: SeleniumRenderer,
    seed_url: str,
    version: str,
    page_delay: float,
    limit: int,
    seed_rendered: dict[str, object] | None = None,
) -> list[str]:
    seed_base_url = canonicalize_doc_url(seed_url)
    queue = [seed_base_url, canonicalize_doc_url(UE_DOC_ROOT)]
    seen: set[str] = set()
    discovered: list[str] = []

    while queue:
        base_url = queue.pop(0)
        if base_url in seen:
            continue
        seen.add(base_url)
        discovered.append(base_url)
        print(f"[crawl {len(discovered)}] {base_url}")
        if base_url == seed_base_url and seed_rendered is not None:
            rendered = seed_rendered
            seed_rendered = None
        else:
            rendered = renderer.render(apply_application_version(base_url, version))
        for raw_link in rendered.get("internalLinks", []):
            link = canonicalize_doc_url(str(raw_link))
            if not is_ue_doc_url(link) or link in seen:
                continue
            queue.append(link)
        if limit > 0 and len(discovered) >= limit:
            break
        if page_delay:
            time.sleep(page_delay)

    return discovered


def output_rel_path(base_url: str) -> Path:
    split = urlsplit(base_url)
    prefix = "/documentation/en-us/unreal-engine"
    path = split.path.rstrip("/")
    if path == prefix:
        return Path("index")
    relative = path[len(prefix):].lstrip("/")
    if not relative:
        return Path("index")
    segments = [sanitize_segment(segment) for segment in relative.split("/") if segment]
    return Path(*segments)


def sanitize_segment(segment: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", segment) or "index"


def extract_title_from_html(html_text: str) -> str:
    match = TITLE_RE.search(html_text)
    if not match:
        return ""
    return unescape(re.sub(r"\s+", " ", match.group(1))).strip()


def is_blocked_page(payload: dict[str, object]) -> bool:
    title = str(payload.get("title") or "").lower()
    current_url = str(payload.get("currentUrl") or "").lower()
    h1 = str(payload.get("h1") or "").lower()
    h3_values = " ".join(str(item).lower() for item in payload.get("h3", []))
    content = str(payload.get("rootText") or "").lower()
    return (
        current_url.endswith("/documentation/403")
        or "403" == h1
        or any(marker in title for marker in BLOCKED_MARKERS)
        or any(marker in h3_values for marker in BLOCKED_MARKERS)
        or any(marker in content for marker in BLOCKED_MARKERS)
    )


class QuietFirefoxService:
    def __init__(self, executable_path: str):
        from selenium.webdriver.firefox.service import Service

        class _Service(Service):
            def _terminate_process(self) -> None:  # type: ignore[override]
                try:
                    super()._terminate_process()
                except PermissionError:
                    pass

        self._service = _Service(executable_path)

    @property
    def service(self):
        return self._service


class SeleniumRenderer:
    def __init__(
        self,
        firefox_binary: str | None,
        geckodriver_path: str | None,
        wait_seconds: int,
        post_ready_delay: float,
    ) -> None:
        try:
            from selenium import webdriver
            from selenium.webdriver.firefox.options import Options
        except ImportError as exc:
            raise RuntimeError(
                "Selenium is required for rendered UE docs download. "
                "Install it with './.venv/bin/python -m pip install selenium'."
            ) from exc

        binary_location = firefox_binary or detect_firefox_binary()
        service_path = geckodriver_path or detect_geckodriver()
        if not binary_location:
            raise RuntimeError("Firefox binary was not found. Set FIREFOX_BINARY or --firefox-binary.")
        if not service_path:
            raise RuntimeError("geckodriver was not found. Set GECKODRIVER_PATH or --geckodriver-path.")

        options = Options()
        options.binary_location = binary_location
        options.add_argument("--headless")
        options.set_preference("permissions.default.image", 2)
        options.set_preference("dom.webnotifications.enabled", False)
        service = QuietFirefoxService(service_path).service
        self.driver = webdriver.Firefox(service=service, options=options)
        self.wait_seconds = wait_seconds
        self.post_ready_delay = post_ready_delay
        self.last_rendered_url = ""
        self.last_rendered_data: dict[str, object] | None = None

    def close(self) -> None:
        try:
            self.driver.quit()
        except Exception:
            pass

    def discover_versions(self, root_url: str, min_major: int) -> list[str]:
        data = self.render(root_url)
        versions = []
        for href in data["internalLinks"]:
            version = extract_application_version(href)
            if version and is_supported_ue5_version(version, min_major=min_major):
                versions.append(version)
        versions = dedupe_preserve_order(versions)
        return sorted(versions, key=version_sort_key, reverse=True)

    def render(self, url: str) -> dict[str, object]:
        from selenium.webdriver.common.by import By
        from selenium.common.exceptions import TimeoutException
        from selenium.webdriver.support.ui import WebDriverWait

        self.driver.get(url)
        WebDriverWait(self.driver, self.wait_seconds).until(
            lambda driver: driver.execute_script("return document.readyState") == "complete"
        )
        WebDriverWait(self.driver, self.wait_seconds).until(
            lambda driver: len(driver.find_elements(By.CSS_SELECTOR, "article, main, h1")) > 0
        )
        try:
            WebDriverWait(self.driver, min(self.wait_seconds, 6)).until(
                lambda driver: len(driver.find_elements(By.CSS_SELECTOR, "a[href]")) > 0
            )
        except TimeoutException:
            pass
        if self.post_ready_delay:
            time.sleep(self.post_ready_delay)
        script = """
            const root = document.querySelector('article') || document.querySelector('main');
            const toText = (node) => (node && node.innerText ? node.innerText.trim() : '');
            return {
              title: document.title || '',
              currentUrl: window.location.href,
              h1: toText(document.querySelector('h1')),
              h2: [...document.querySelectorAll('h2')].map((node) => toText(node)).filter(Boolean),
              h3: [...document.querySelectorAll('h3')].map((node) => toText(node)).filter(Boolean),
              rootHtml: root ? root.outerHTML : '',
              rootText: root ? toText(root) : toText(document.body),
              bodyText: toText(document.body),
              pageHtml: document.documentElement.outerHTML,
            };
        """
        payload = self.driver.execute_script(script)
        links = [
            href
            for href in (
                element.get_attribute("href")
                for element in self.driver.find_elements(By.CSS_SELECTOR, "a[href]")
            )
            if href and "/documentation/en-us/unreal-engine" in href
        ]
        if not links:
            time.sleep(1)
            links = [
                href
                for href in (
                    element.get_attribute("href")
                    for element in self.driver.find_elements(By.CSS_SELECTOR, "a[href]")
                )
                if href and "/documentation/en-us/unreal-engine" in href
            ]
        payload["internalLinks"] = dedupe_preserve_order(links)
        self.last_rendered_url = url
        self.last_rendered_data = payload
        return payload

    def fetch_text(self, url: str) -> str:
        payload: dict[str, object] | None = None
        for attempt in range(3):
            payload = self.driver.execute_async_script(
                """
                    const url = arguments[0];
                    const done = arguments[arguments.length - 1];
                    fetch(url, {
                        credentials: 'include',
                        cache: 'no-store',
                    }).then(async (response) => {
                        done({
                            status: response.status,
                            ok: response.ok,
                            text: await response.text(),
                        });
                    }).catch((error) => {
                        done({
                            status: -1,
                            ok: false,
                            error: String(error),
                            text: '',
                        });
                    });
                """,
                url,
            )
            if payload.get("ok"):
                return str(payload.get("text") or "")
            self.driver.get(DEFAULT_ROOT_URL)
            time.sleep(2 + attempt)
        raise RuntimeError(
            f"browser fetch failed for {url}: status={payload.get('status')} "
            f"error={payload.get('error', '')}"
        )


def detect_firefox_binary() -> str | None:
    candidates = [
        "/snap/firefox/current/usr/lib/firefox/firefox",
        "/usr/lib/firefox/firefox",
        "/usr/bin/firefox",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return None


def detect_geckodriver() -> str | None:
    candidates = [
        "/snap/bin/geckodriver",
        "/usr/bin/geckodriver",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return None


def version_sort_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split(".") if part.isdigit())


def save_page(
    output_dir: Path,
    record: PageRecord,
    raw_html: str,
    rendered_html: str,
    rendered_text: str,
) -> None:
    page_dir = output_dir / record.version / record.path
    page_dir.mkdir(parents=True, exist_ok=True)
    (page_dir / "raw.html").write_text(raw_html, encoding="utf-8")
    (page_dir / "rendered.html").write_text(rendered_html, encoding="utf-8")
    (page_dir / "content.txt").write_text(rendered_text, encoding="utf-8")
    (page_dir / "meta.json").write_text(
        json.dumps(asdict(record), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def page_already_saved(output_dir: Path, version: str, rel_path: Path) -> bool:
    return (output_dir / version / rel_path / "meta.json").exists()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False))
        handle.write("\n")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download the full Unreal Engine 5 documentation corpus.")
    parser.add_argument("--sitemap-url", default=SITEMAP_URL)
    parser.add_argument("--output-dir", default="downloads/ue5-docs")
    parser.add_argument("--root-url", default=DEFAULT_ROOT_URL)
    parser.add_argument("--versions", default="")
    parser.add_argument("--min-major", type=int, default=5)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--retry-count", type=int, default=3)
    parser.add_argument("--sitemap-delay", type=float, default=0.15)
    parser.add_argument("--page-delay", type=float, default=0.4)
    parser.add_argument("--render-wait", type=int, default=45)
    parser.add_argument("--post-ready-delay", type=float, default=0.5)
    parser.add_argument("--render-retries", type=int, default=4)
    parser.add_argument("--blocked-backoff", type=float, default=15.0)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--max-sitemaps", type=int, default=0)
    parser.add_argument("--skip-existing", action="store_true", default=True)
    parser.add_argument("--no-skip-existing", dest="skip_existing", action="store_false")
    parser.add_argument("--discover-only", action="store_true")
    parser.add_argument("--discovery-source", choices=("auto", "sitemap", "crawl"), default="auto")
    parser.add_argument("--firefox-binary", default="")
    parser.add_argument("--geckodriver-path", default="")
    return parser


def build_versions(args: argparse.Namespace, renderer: SeleniumRenderer | None) -> list[str]:
    if args.versions:
        versions = [value.strip() for value in args.versions.split(",") if value.strip()]
    else:
        if renderer is None:
            raise RuntimeError("Explicit --versions are required when Selenium is not available.")
        versions = renderer.discover_versions(args.root_url, min_major=args.min_major)
    versions = [value for value in versions if is_supported_ue5_version(value, min_major=args.min_major)]
    versions = dedupe_preserve_order(versions)
    return sorted(versions, key=version_sort_key, reverse=True)


def create_renderer(args: argparse.Namespace) -> SeleniumRenderer:
    return SeleniumRenderer(
        firefox_binary=args.firefox_binary or None,
        geckodriver_path=args.geckodriver_path or None,
        wait_seconds=args.render_wait,
        post_ready_delay=args.post_ready_delay,
    )


def fetch_page_assets(
    session: requests.Session,
    renderer: SeleniumRenderer,
    page_url: str,
    timeout: int,
    render_retries: int,
    blocked_backoff: float,
) -> tuple[str, dict[str, object]]:
    raw_response = session.get(page_url, timeout=timeout)
    raw_response.raise_for_status()
    last_rendered: dict[str, object] | None = None
    for attempt in range(render_retries):
        rendered = renderer.render(page_url)
        last_rendered = rendered
        if not is_blocked_page(rendered):
            return raw_response.text, rendered
        sleep_seconds = blocked_backoff * (attempt + 1)
        print(
            f"  blocked by Epic on {page_url}; retry {attempt + 1}/{render_retries} "
            f"after {sleep_seconds:.1f}s",
            file=sys.stderr,
        )
        time.sleep(sleep_seconds)
        renderer.render(DEFAULT_ROOT_URL)
        time.sleep(3)
    raise RuntimeError(
        f"Epic returned a 403 block page for {page_url}. "
        f"Last title={last_rendered.get('title') if last_rendered else ''}"
    )


def main() -> int:
    args = build_arg_parser().parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    session = build_session(args.retry_count)
    renderer: SeleniumRenderer | None = None
    try:
        renderer = create_renderer(args)
        versions = build_versions(args, renderer)
        print(f"Versions: {', '.join(versions)}")

        base_urls: list[str] = []
        if args.discovery_source in {"auto", "sitemap"}:
            sitemap_urls = collect_sitemap_urls(
                session=session,
                sitemap_url=args.sitemap_url,
                renderer=renderer,
                timeout=args.timeout,
                delay_seconds=args.sitemap_delay,
                max_sitemaps=args.max_sitemaps,
            )
            base_urls = filter_ue_doc_urls(sitemap_urls)
        if not base_urls and args.discovery_source in {"auto", "crawl"}:
            latest_version = versions[0]
            base_urls = crawl_base_urls(
                renderer=renderer,
                seed_url=args.root_url,
                version=latest_version,
                page_delay=args.page_delay,
                limit=args.limit,
                seed_rendered=renderer.last_rendered_data,
            )
        if args.limit > 0:
            base_urls = base_urls[: args.limit]

        write_json(output_dir / "versions.json", versions)
        write_json(output_dir / "base_urls.json", base_urls)
        print(f"Collected {len(base_urls)} UE documentation base URLs")

        if args.discover_only:
            return 0

        renderer.close()
        renderer = None

        manifest_path = output_dir / "manifest.jsonl"
        summary = {
            "started_at": datetime.now(UTC).isoformat(),
            "versions": versions,
            "base_url_count": len(base_urls),
            "planned_pages": len(base_urls) * len(versions),
            "saved_pages": 0,
            "skipped_existing": 0,
            "failed_pages": 0,
        }
        write_json(output_dir / "summary.json", summary)

        total = len(base_urls) * len(versions)
        counter = 0
        for version in versions:
            for base_url in base_urls:
                counter += 1
                rel_path = output_rel_path(base_url)
                page_url = apply_application_version(base_url, version)
                if args.skip_existing and page_already_saved(output_dir, version, rel_path):
                    summary["skipped_existing"] += 1
                    print(f"[{counter}/{total}] skip {version} {base_url}")
                    continue

                print(f"[{counter}/{total}] fetch {page_url}")
                renderer = create_renderer(args)
                try:
                    raw_html, rendered = fetch_page_assets(
                        session=session,
                        renderer=renderer,
                        page_url=page_url,
                        timeout=args.timeout,
                        render_retries=args.render_retries,
                        blocked_backoff=args.blocked_backoff,
                    )
                    title = str(rendered.get("title") or "")
                    raw_title = extract_title_from_html(raw_html)
                    content_text = str(rendered.get("rootText") or "")
                    if not content_text.strip():
                        content_text = str(rendered.get("bodyText") or "")
                    h1 = str(rendered.get("h1") or "")
                    status = "ok"
                    lower_title = title.lower()
                    lower_text = content_text[:1000].lower()
                    if any(marker in lower_title or marker in lower_text for marker in NOT_FOUND_MARKERS):
                        status = "not_found"

                    record = PageRecord(
                        base_url=base_url,
                        version=version,
                        url=page_url,
                        current_url=str(rendered.get("currentUrl") or page_url),
                        title=title,
                        raw_title=raw_title,
                        h1=h1,
                        h2=[str(item) for item in rendered.get("h2", [])],
                        h3=[str(item) for item in rendered.get("h3", [])],
                        content_text_length=len(content_text),
                        internal_links=[
                            canonicalize_doc_url(str(link))
                            for link in rendered.get("internalLinks", [])
                            if is_ue_doc_url(str(link))
                        ],
                        status=status,
                        fetched_at=datetime.now(UTC).isoformat(),
                        path=rel_path.as_posix(),
                    )
                    save_page(
                        output_dir=output_dir,
                        record=record,
                        raw_html=raw_html,
                        rendered_html=str(rendered.get("pageHtml") or ""),
                        rendered_text=content_text,
                    )
                    append_jsonl(manifest_path, asdict(record))
                    summary["saved_pages"] += 1
                except Exception as exc:
                    summary["failed_pages"] += 1
                    append_jsonl(
                        manifest_path,
                        {
                            "base_url": base_url,
                            "version": version,
                            "url": page_url,
                            "status": "error",
                            "error": str(exc),
                            "fetched_at": datetime.now(UTC).isoformat(),
                        },
                    )
                    print(f"  error: {exc}", file=sys.stderr)
                finally:
                    renderer.close()
                    renderer = None
                    write_json(output_dir / "summary.json", summary)
                    if args.page_delay:
                        time.sleep(args.page_delay)

        summary["finished_at"] = datetime.now(UTC).isoformat()
        write_json(output_dir / "summary.json", summary)
        return 0
    finally:
        if renderer is not None:
            renderer.close()


if __name__ == "__main__":
    raise SystemExit(main())
