#!/usr/bin/env bash
set -euo pipefail

export DASHSCOPE_API_KEY="your_api_key_here"
export DASHSCOPE_MODEL="qwen-vl-max"
export LOG_DIR="logs"

mkdir -p "${LOG_DIR}"

exec gunicorn \
  -w 4 \
  -k gevent \
  --worker-connections 1000 \
  --bind 0.0.0.0:6000 \
  --timeout 180 \
  --access-logfile "${LOG_DIR}/access.log" \
  --error-logfile "${LOG_DIR}/error.log" \
  app:app
