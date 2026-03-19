from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


def load_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "ue_docs_jina_downloader.py"
    spec = importlib.util.spec_from_file_location("ue_docs_jina_downloader", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_is_blocked_jina_payload_detects_captcha_warning():
    module = load_module()
    raw = """Title: Textures in Unreal Engine | Unreal Engine 5.4 Documentation | Epic Developer Community

Warning: This page maybe requiring CAPTCHA, please make sure you are authorized to access this page.

Markdown Content:
Error: 403 | Epic Developer Community
===============
"""

    assert module.is_blocked_jina_payload(
        "Textures in Unreal Engine | Unreal Engine 5.4 Documentation | Epic Developer Community",
        "Error: 403 | Epic Developer Community\n===============\n",
        raw,
    )


def test_page_exists_rejects_generic_or_blocked_saved_page(tmp_path):
    module = load_module()
    page_dir = tmp_path / "5.4" / "foo"
    page_dir.mkdir(parents=True)
    (page_dir / "meta.json").write_text(
        json.dumps(
            {
                "version": "5.4",
                "title": "Documentation | Epic Developer Community",
                "content_length": 76,
            }
        ),
        encoding="utf-8",
    )
    (page_dir / "raw.txt").write_text(
        "Warning: This page maybe requiring CAPTCHA\nMarkdown Content:\nError: 403 | Epic Developer Community",
        encoding="utf-8",
    )
    (page_dir / "content.md").write_text("Error: 403 | Epic Developer Community", encoding="utf-8")

    assert not module.page_exists(tmp_path, "5.4", Path("foo"))


def test_page_exists_accepts_valid_saved_page(tmp_path):
    module = load_module()
    page_dir = tmp_path / "5.4" / "bar"
    page_dir.mkdir(parents=True)
    (page_dir / "meta.json").write_text(
        json.dumps(
            {
                "version": "5.4",
                "title": "Valid Title | Unreal Engine 5.4 Documentation | Epic Developer Community",
                "content_length": 1024,
            }
        ),
        encoding="utf-8",
    )
    (page_dir / "raw.txt").write_text(
        "Title: Valid Title\nURL Source: https://example.invalid\nMarkdown Content:\n# Valid",
        encoding="utf-8",
    )
    (page_dir / "content.md").write_text("# Valid", encoding="utf-8")

    assert module.page_exists(tmp_path, "5.4", Path("bar"))
