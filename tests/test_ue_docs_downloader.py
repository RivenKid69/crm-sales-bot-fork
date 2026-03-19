from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def load_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "ue_docs_downloader.py"
    spec = importlib.util.spec_from_file_location("ue_docs_downloader", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parse_sitemap_index_and_urlset():
    module = load_module()
    index_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <sitemap><loc>https://example.com/a.xml</loc></sitemap>
      <sitemap><loc>https://example.com/b.xml</loc></sitemap>
    </sitemapindex>
    """
    urlset_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://example.com/doc-a</loc></url>
      <url><loc>https://example.com/doc-b</loc></url>
    </urlset>
    """

    assert module.parse_sitemap_xml(index_xml) == (
        "index",
        ["https://example.com/a.xml", "https://example.com/b.xml"],
    )
    assert module.parse_sitemap_xml(urlset_xml) == (
        "urlset",
        ["https://example.com/doc-a", "https://example.com/doc-b"],
    )


def test_version_helpers_and_url_canonicalization():
    module = load_module()
    base = "https://dev.epicgames.com/documentation/en-us/unreal-engine/whats-new"
    versioned = module.apply_application_version(base, "5.7")

    assert versioned.endswith("application_version=5.7")
    assert module.extract_application_version(versioned) == "5.7"
    assert module.canonicalize_doc_url(versioned) == base
    assert module.is_supported_ue5_version("5.0")
    assert module.is_supported_ue5_version("5.7")
    assert not module.is_supported_ue5_version("4.27")


def test_filter_ue_urls_and_output_path():
    module = load_module()
    urls = [
        "https://dev.epicgames.com/documentation/en-us/unreal-engine/whats-new?application_version=5.7",
        "https://dev.epicgames.com/documentation/en-us/unreal-engine/whats-new?application_version=5.6",
        "https://dev.epicgames.com/documentation/en-us/fortnite/foo",
        "https://dev.epicgames.com/documentation/en-us/unreal-engine/API",
    ]

    assert module.filter_ue_doc_urls(urls) == [
        "https://dev.epicgames.com/documentation/en-us/unreal-engine/whats-new",
        "https://dev.epicgames.com/documentation/en-us/unreal-engine/API",
    ]
    assert module.output_rel_path("https://dev.epicgames.com/documentation/en-us/unreal-engine") == Path(
        "index"
    )
    assert module.output_rel_path(
        "https://dev.epicgames.com/documentation/en-us/unreal-engine/whats-new"
    ) == Path("whats-new")
    assert module.output_rel_path(
        "https://dev.epicgames.com/documentation/en-us/unreal-engine/API"
    ) == Path("API")


def test_extract_title_from_html():
    module = load_module()
    html = "<html><head><title>What&#39;s New | Unreal Engine 5.7 Documentation</title></head></html>"
    assert module.extract_title_from_html(html) == "What's New | Unreal Engine 5.7 Documentation"


def test_is_blocked_page():
    module = load_module()
    assert module.is_blocked_page(
        {
            "title": "Error: 403 | Epic Developer Community",
            "currentUrl": "https://dev.epicgames.com/documentation/403",
            "h1": "403",
            "h3": ["ACCESS NOT ALLOWED"],
            "rootText": "403 ACCESS NOT ALLOWED",
        }
    )
