#!/bin/bash
set -e

if [ -f /app/docker-config/settings.yaml ]; then
    python - <<'PY'
from pathlib import Path
import yaml

base_path = Path("/app/src/settings.yaml")
overlay_path = Path("/app/docker-config/settings.yaml")

with open(base_path, "r", encoding="utf-8") as f:
    base = yaml.safe_load(f) or {}

with open(overlay_path, "r", encoding="utf-8") as f:
    overlay = yaml.safe_load(f) or {}

def deep_merge(base, override):
    result = dict(base)
    for key, value in override.items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result

with open(base_path, "w", encoding="utf-8") as f:
    yaml.safe_dump(deep_merge(base, overlay), f, allow_unicode=True, sort_keys=False)
PY
    echo "[entrypoint] settings.yaml overlay applied from /app/docker-config/settings.yaml"
fi

if [ -n "$OLLAMA_BASE_URL" ]; then
    sed -i "s|base_url:.*|base_url: \"${OLLAMA_BASE_URL}\"|" /app/src/settings.yaml
    echo "[entrypoint] Ollama base_url set to: $OLLAMA_BASE_URL"
fi

if [ -n "$OLLAMA_MODEL" ]; then
    sed -i "s|model:.*|model: \"${OLLAMA_MODEL}\"|" /app/src/settings.yaml
    echo "[entrypoint] Ollama model set to: $OLLAMA_MODEL"
fi

if [ -n "$TEI_EMBED_URL" ]; then
    sed -i "s|embedder_url:.*|embedder_url: \"${TEI_EMBED_URL}\"|" /app/src/settings.yaml
    echo "[entrypoint] TEI embed URL set to: $TEI_EMBED_URL"
fi

if [ -n "$TEI_RERANK_URL" ]; then
    sed -i '/^reranker:/,/^[^[:space:]]/ s|^  url:.*|  url: "'"${TEI_RERANK_URL}"'"|' /app/src/settings.yaml
    echo "[entrypoint] TEI rerank URL set to: $TEI_RERANK_URL"
fi

exec "$@"
