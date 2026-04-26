#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f ".venv/bin/python" ]]; then
  echo "未找到 .venv/bin/python，请先创建并安装虚拟环境。" >&2
  exit 1
fi

.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install -r requirements-build.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python build_release.py onedir
