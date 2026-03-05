#!/bin/bash
set -e

# Override Ollama base_url in settings.yaml if OLLAMA_BASE_URL is set
if [ -n "$OLLAMA_BASE_URL" ]; then
    sed -i "s|base_url:.*|base_url: \"${OLLAMA_BASE_URL}\"|" /app/src/settings.yaml
    echo "[entrypoint] Ollama base_url set to: $OLLAMA_BASE_URL"
fi

# Override embedder_device if set (cpu/cuda)
if [ -n "$EMBEDDER_DEVICE" ]; then
    sed -i "s|embedder_device:.*|embedder_device: \"${EMBEDDER_DEVICE}\"|" /app/src/settings.yaml
    echo "[entrypoint] embedder_device set to: $EMBEDDER_DEVICE"
fi

exec "$@"
