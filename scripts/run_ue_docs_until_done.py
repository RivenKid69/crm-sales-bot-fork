from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Repeat UE docs downloader passes until all pages are saved.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-passes", type=int, default=20)
    parser.add_argument("--sleep-between", type=int, default=120)
    parser.add_argument("--page-delay", type=float, default=0.5)
    parser.add_argument("--blocked-backoff", type=float, default=10.0)
    parser.add_argument("--render-retries", type=int, default=2)
    parser.add_argument("--discovery-source", default="crawl", choices=("crawl", "sitemap", "auto"))
    return parser


def run_pass(args: argparse.Namespace, log_path: Path) -> int:
    cmd = [
        sys.executable,
        "-u",
        "scripts/ue_docs_downloader.py",
        "--output-dir",
        args.output_dir,
        "--discovery-source",
        args.discovery_source,
        "--page-delay",
        str(args.page_delay),
        "--blocked-backoff",
        str(args.blocked_backoff),
        "--render-retries",
        str(args.render_retries),
    ]
    with log_path.open("a", encoding="utf-8") as log_handle:
        log_handle.write(f"\n=== PASS START {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        log_handle.flush()
        process = subprocess.run(cmd, stdout=log_handle, stderr=log_handle)
        log_handle.write(f"=== PASS END rc={process.returncode} ===\n")
        return process.returncode


def main() -> int:
    args = build_parser().parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "orchestrator.log"

    for current_pass in range(1, args.max_passes + 1):
        print(f"pass {current_pass}/{args.max_passes}")
        rc = run_pass(args, log_path)

        summary_path = output_dir / "summary.json"
        if not summary_path.exists():
            print("summary.json not found after pass", file=sys.stderr)
            if rc != 0:
                time.sleep(args.sleep_between)
                continue
            return 1

        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        planned_pages = int(summary.get("planned_pages", 0))
        saved_pages = int(summary.get("saved_pages", 0))
        failed_pages = int(summary.get("failed_pages", 0))
        print(
            f"planned={planned_pages} saved={saved_pages} failed={failed_pages} "
            f"missing={planned_pages - saved_pages}"
        )
        if planned_pages > 0 and saved_pages >= planned_pages:
            print("all pages saved")
            return 0

        if current_pass < args.max_passes:
            time.sleep(args.sleep_between)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
