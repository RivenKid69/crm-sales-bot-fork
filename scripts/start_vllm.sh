#!/bin/bash
# Запуск vLLM сервера с Qwen3-8B-AWQ
# Требует: pip install vllm outlines

echo "Запуск vLLM сервера с Qwen3-8B-AWQ..."
echo "Требуется ~5-6 GB VRAM"

vllm serve Qwen/Qwen3-8B-AWQ \
    --host 0.0.0.0 \
    --port 8000 \
    --guided-decoding-backend outlines \
    --max-model-len 4096 \
    --gpu-memory-utilization 0.9

# Для запуска в фоне:
# nohup vllm serve Qwen/Qwen3-8B-AWQ \
#     --host 0.0.0.0 \
#     --port 8000 \
#     --guided-decoding-backend outlines \
#     --max-model-len 4096 \
#     --gpu-memory-utilization 0.9 \
#     > vllm.log 2>&1 &
