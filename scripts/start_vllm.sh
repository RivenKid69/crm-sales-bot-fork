#!/bin/bash
# Запуск vLLM сервера с Qwen3-8B-AWQ
# Требует: pip install vllm
# vLLM 0.12+ использует xgrammar по умолчанию для structured outputs

echo "Запуск vLLM сервера с Qwen3-8B-AWQ..."
echo "Требуется ~5-6 GB VRAM"

# vLLM 0.12+ - xgrammar используется по умолчанию
vllm serve Qwen/Qwen3-8B-AWQ \
    --host 0.0.0.0 \
    --port 8000 \
    --max-model-len 4096 \
    --gpu-memory-utilization 0.9

# Для запуска в фоне:
# nohup vllm serve Qwen/Qwen3-8B-AWQ \
#     --host 0.0.0.0 \
#     --port 8000 \
#     --max-model-len 4096 \
#     --gpu-memory-utilization 0.9 \
#     > vllm.log 2>&1 &
