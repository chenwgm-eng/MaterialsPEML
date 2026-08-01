#!/bin/bash

LOGOS_MODEL_PATH="${LOGOS_MODEL_PATH:-/data/models/logos-1b}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8080}"

echo "Starting LOGOS vLLM server..."
echo "Model path: $LOGOS_MODEL_PATH"
echo "API base: http://$HOST:$PORT"

python -m vllm.entrypoints.openai.api_server \
  --model "$LOGOS_MODEL_PATH" \
  --host "$HOST" \
  --port "$PORT" \
  --served-model-name logos-1b \
  --max-model-len 4096 \
  --trust-remote-code \
  --gpu-memory-utilization 0.85
