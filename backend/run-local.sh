#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

.venv/bin/pip install -r requirements.txt

if [ ! -f "config.yaml" ]; then
  cp config.example.yaml config.yaml
fi

CONFIG_PATH="${CONFIG_PATH:-$(pwd)/config.yaml}" \
  .venv/bin/uvicorn src.main:app --host 0.0.0.0 --port "${PORT:-8000}"
