"""Shared TEI (text-embeddings-inference) HTTP client for embeddings."""

import hashlib
import os
import threading
from pathlib import Path
from typing import List, Optional

import requests

from src.settings import settings

# Default cache directory (overridable via EMBEDDING_CACHE_DIR env var)
_CACHE_DIR = Path(os.environ.get("EMBEDDING_CACHE_DIR", ".cache/embeddings"))


def _get_tei_url() -> str:
    """Get TEI embed URL from settings."""
    return getattr(
        getattr(settings, 'retriever', None),
        'embedder_url',
        'http://tei-embed:80'
    ).rstrip('/')


def embed_texts(texts: List[str], *, tei_url: str = None, timeout: float = 30.0) -> Optional[List[List[float]]]:
    """
    Encode a list of texts via TEI /embed endpoint.

    Args:
        texts: List of strings to embed
        tei_url: TEI endpoint URL (default from settings)
        timeout: HTTP timeout in seconds

    Returns:
        List of embedding vectors, or None on error
    """
    if not texts:
        return []

    url = tei_url or _get_tei_url()

    try:
        resp = requests.post(
            f"{url}/embed",
            json={"inputs": texts},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def embed_single(text: str, *, tei_url: str = None, timeout: float = 10.0) -> Optional[List[float]]:
    """
    Encode a single text via TEI /embed endpoint.

    Returns:
        Embedding vector, or None on error
    """
    result = embed_texts([text], tei_url=tei_url, timeout=timeout)
    if result and len(result) > 0:
        return result[0]
    return None


# ---------------------------------------------------------------------------
# Disk cache for batch embeddings (avoids re-encoding on every startup)
# ---------------------------------------------------------------------------

def _texts_hash(texts: List[str]) -> str:
    """Compute a stable SHA-256 hash over the ordered list of texts."""
    h = hashlib.sha256()
    for t in texts:
        h.update(t.encode("utf-8"))
        h.update(b"\x00")  # separator
    return h.hexdigest()[:16]


def embed_texts_cached(
    texts: List[str],
    cache_name: str,
    *,
    tei_url: str = None,
    timeout: float = 120.0,
    batch_size: int = 64,
    cache_dir: Path = None,
):
    """
    Like embed_texts(), but caches results as .npy on disk.

    Cache invalidation: if the hash of input texts changes (KB updated,
    examples changed), the cache is re-built automatically.

    Args:
        texts: Texts to embed
        cache_name: Logical name for the cache file (e.g. "kb_sections")
        tei_url: TEI endpoint URL
        timeout: Per-batch HTTP timeout
        batch_size: Texts per TEI request
        cache_dir: Override cache directory

    Returns:
        numpy ndarray of shape (len(texts), dim), or None on error
    """
    import numpy as np

    if not texts:
        return np.empty((0, 0))

    cdir = cache_dir or _CACHE_DIR
    cdir.mkdir(parents=True, exist_ok=True)

    content_hash = _texts_hash(texts)
    npy_path = cdir / f"{cache_name}_{content_hash}.npy"

    # Try loading from disk
    if npy_path.exists():
        try:
            arr = np.load(npy_path)
            if arr.shape[0] == len(texts):
                print(f"[tei_client] Loaded cached embeddings: {cache_name} ({len(texts)} items)")
                return arr
        except Exception:
            pass  # corrupt file — re-encode

    # Encode via TEI in batches
    url = tei_url or _get_tei_url()
    all_embeddings = []

    try:
        for start in range(0, len(texts), batch_size):
            batch = texts[start:start + batch_size]
            resp = requests.post(
                f"{url}/embed",
                json={"inputs": batch},
                timeout=timeout,
            )
            resp.raise_for_status()
            all_embeddings.extend(resp.json())
            done = min(start + batch_size, len(texts))
            print(f"[tei_client] {cache_name}: encoded {done}/{len(texts)}")
    except Exception as e:
        print(f"[tei_client] TEI embed failed for {cache_name}: {e}")
        return None

    arr = np.array(all_embeddings)

    # Save to disk (remove old cache files for this name)
    try:
        for old in cdir.glob(f"{cache_name}_*.npy"):
            old.unlink()
        np.save(npy_path, arr)
        print(f"[tei_client] Saved cache: {npy_path}")
    except Exception as e:
        print(f"[tei_client] Warning: couldn't save cache: {e}")

    return arr
