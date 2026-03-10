"""Preload TEI models into the shared Hugging Face cache."""

import os

from huggingface_hub import snapshot_download


MODELS = [
    (
        os.environ.get("TEI_EMBED_MODEL_ID", "Qwen/Qwen3-Embedding-4B"),
        os.environ.get("TEI_EMBED_REVISION", "5cf2132abc99cad020ac570b19d031efec650f2b"),
    ),
    (
        os.environ.get("TEI_RERANK_MODEL_ID", "Qwen/Qwen3-Reranker-4B"),
        os.environ.get("TEI_RERANK_REVISION", "f16fc5d5d2b9b1d0db8280929242745d79794ef5"),
    ),
]


def main() -> None:
    for model_id, revision in MODELS:
        print(f"[preload] Downloading {model_id}@{revision} ...", flush=True)
        path = snapshot_download(repo_id=model_id, revision=revision)
        print(f"[preload] Ready: {model_id}@{revision} -> {path}", flush=True)


if __name__ == "__main__":
    main()
