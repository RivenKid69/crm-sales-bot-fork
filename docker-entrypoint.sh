#!/bin/bash
set -e

# Override Ollama base_url in settings.yaml if OLLAMA_BASE_URL is set
if [ -n "$OLLAMA_BASE_URL" ]; then
    sed -i "s|base_url:.*|base_url: \"${OLLAMA_BASE_URL}\"|" /app/src/settings.yaml
    echo "[entrypoint] Ollama base_url set to: $OLLAMA_BASE_URL"
fi

if [ -n "$OLLAMA_MODEL" ]; then
    sed -i "s|model:.*|model: \"${OLLAMA_MODEL}\"|" /app/src/settings.yaml
    echo "[entrypoint] Ollama model set to: $OLLAMA_MODEL"
fi

# Override TEI embed URL
if [ -n "$TEI_EMBED_URL" ]; then
    sed -i "s|embedder_url:.*|embedder_url: \"${TEI_EMBED_URL}\"|" /app/src/settings.yaml
    echo "[entrypoint] TEI embed URL set to: $TEI_EMBED_URL"
fi

# Override TEI rerank URL
if [ -n "$TEI_RERANK_URL" ]; then
    sed -i '/^reranker:/,/^[^[:space:]]/ s|^  url:.*|  url: "'"${TEI_RERANK_URL}"'"|' /app/src/settings.yaml
    echo "[entrypoint] TEI rerank URL set to: $TEI_RERANK_URL"
fi

echo "[entrypoint] Effective TEI rerank config: $(grep -E '^  url:' /app/src/settings.yaml | head -n 1 | xargs)"

exec "$@"
