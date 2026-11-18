#!/usr/bin/env bash
# Lanzador para Linux: fuerza el backend X11 de Qt y el controlador V4L2.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -x ".venv/bin/python" ]; then
    python3 -m venv .venv
fi

if ! .venv/bin/python -c 'import cv2, numpy, kociemba' >/dev/null 2>&1; then
    .venv/bin/python -m pip install --upgrade pip
    .venv/bin/python -m pip install -r requirements.txt
fi

export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
exec .venv/bin/python -m src.main --backend v4l2 "$@"
