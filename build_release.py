from __future__ import annotations

import shutil
import sys
from pathlib import Path

import PyInstaller.__main__
from PyInstaller.utils.hooks import collect_data_files, collect_submodules


APP_NAME = "MusicDownloader"
ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"


def main() -> int:
    mode = "onedir"
    if len(sys.argv) > 1:
        mode = sys.argv[1].strip().lower()
    if mode not in {"onedir", "onefile"}:
        raise SystemExit("Usage: python build_release.py [onedir|onefile]")

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
