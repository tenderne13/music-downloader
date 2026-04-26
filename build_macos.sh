#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-onedir}"
ICON_PATH="${2:-}"

if [[ ! -f ".venv/bin/python" ]]; then
  echo "未找到 .venv/bin/python，请先创建并安装虚拟环境。" >&2
  exit 1
fi

.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install -r requirements-build.txt
.venv/bin/python -m playwright install chromium
BUILD_ARGS=("build_release.py" "$MODE")
if [[ -n "$ICON_PATH" ]]; then
  BUILD_ARGS+=("--icon" "$ICON_PATH")
fi
.venv/bin/python "${BUILD_ARGS[@]}"
