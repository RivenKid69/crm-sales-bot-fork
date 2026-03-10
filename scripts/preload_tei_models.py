"""Preload TEI models into the shared Hugging Face cache."""

from huggingface_hub import snapshot_download


MODELS = [
    "Qwen/Qwen3-Embedding-4B",
    "Qwen/Qwen3-Reranker-4B",
]


def main() -> None:
    for model_id in MODELS:
        print(f"[preload] Downloading {model_id} ...", flush=True)
        path = snapshot_download(repo_id=model_id)
        print(f"[preload] Ready: {model_id} -> {path}", flush=True)


if __name__ == "__main__":
    main()
