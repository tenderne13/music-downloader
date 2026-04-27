#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-onedir}"
ICON_PATH="${2:-}"

if [[ ! -f ".venv/bin/python" ]]; then
  echo "未找到 .venv/bin/python，请先创建并安装虚拟环境。" >&2
  exit 1
fi

if ! .venv/bin/python -c "import _tkinter" >/dev/null 2>&1; then
  cat >&2 <<'EOF'
当前 .venv 对应的 Python 缺少 tkinter（_tkinter）。
这会导致打包后的 GUI 应用无法打开。

可选修复方案（Homebrew Python）：
  brew install python-tk@3.13

然后建议重建虚拟环境：
  rm -rf .venv
  python3 -m venv .venv

再执行本脚本重新打包。
EOF
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
