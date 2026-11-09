#!/usr/bin/env bash
# Linux/macOS: inicia a API local servindo o frontend compilado (frontend/dist).
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"; [ -x .venv/bin/python ] && PY=.venv/bin/python
"$PY" -c "import fastapi, uvicorn, deepmodel_inspector" 2>/dev/null || { echo "Missing packages: pip install -e '.[app]'"; exit 1; }
[ -f frontend/dist/index.html ] || { echo "Build the frontend first: (cd frontend && npm ci && npm run build)"; exit 1; }
echo "DeepModel Inspector: http://127.0.0.1:${1:-8765}"
exec "$PY" -m backend.api.main --port "${1:-8765}"
