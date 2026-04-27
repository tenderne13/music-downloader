from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


APP_NAME = "MusicDownloader"
ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
DEFAULT_ICONS = {
    "darwin": ROOT / "assets" / "icons" / "app_icon.icns",
    "win32": ROOT / "assets" / "icons" / "app_icon.ico",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the desktop application with PyInstaller.")
    parser.add_argument(
        "mode",
        nargs="?",
        default="onedir",
        choices=["onedir", "onefile"],
        help="PyInstaller output mode.",
    )
    parser.add_argument(
        "--icon",
        default=None,
        help="Path to the application icon. Use .ico on Windows and .icns on macOS.",
    )
    return parser.parse_args()


def resolve_icon_path(icon_arg: str | None) -> Path | None:
    if not icon_arg:
        return None

    candidate = Path(icon_arg)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    candidate = candidate.resolve()
    if not candidate.exists():
        raise SystemExit(f"Icon file not found: {candidate}")
    return candidate


def find_default_icon() -> Path | None:
    platform_icon = DEFAULT_ICONS.get(sys.platform)
    if platform_icon and platform_icon.exists():
        return platform_icon.resolve()

    linux_fallback = ROOT / "assets" / "icons" / "app_icon.png"
    if linux_fallback.exists():
        return linux_fallback.resolve()
    return None


def ensure_tkinter_available() -> None:
    try:
        import _tkinter  # noqa: F401
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "当前 Python 缺少 tkinter（_tkinter），GUI 打包产物将无法启动。\n"
            "请先安装 tkinter 支持后再重新打包。"
        ) from exc


def main() -> int:
    parsed = parse_args()
    mode = parsed.mode
    icon_path = resolve_icon_path(parsed.icon)
    if icon_path is None:
        icon_path = find_default_icon()
    ensure_tkinter_available()

    import PyInstaller.__main__
    from PyInstaller.utils.hooks import collect_data_files, collect_submodules

    if BUILD.exists():
        shutil.rmtree(BUILD)

    target_dist = DIST / sys.platform
    if target_dist.exists():
        shutil.rmtree(target_dist)
    target_dist.mkdir(parents=True, exist_ok=True)

    data_files = collect_data_files("playwright")
    data_files.append((str(ROOT / "site_config.example.json"), "."))

    hidden_imports = collect_submodules("playwright")

    args = [
        str(ROOT / "app.py"),
        "--name",
        APP_NAME,
        "--noconfirm",
        "--clean",
        "--windowed",
        "--distpath",
        str(target_dist),
        "--workpath",
        str(BUILD / sys.platform),
        "--specpath",
        str(BUILD / "spec"),
    ]

    if icon_path is not None:
        args.extend(["--icon", str(icon_path)])
        data_files.append((str(icon_path), f"resources/app-icon{icon_path.suffix.lower()}"))

    if mode == "onefile":
        args.append("--onefile")
    else:
        args.append("--onedir")

    for source, dest in data_files:
        args.extend(["--add-data", f"{source}{';' if sys.platform == 'win32' else ':'}{dest}"])

    for item in hidden_imports:
        args.extend(["--hidden-import", item])

    PyInstaller.__main__.run(args)
    print(f"Build completed: {target_dist}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
