from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .app_config import AppConfig, DEFAULT_SETTINGS_PATH
from .config import SiteConfig
from .runtime import ensure_default_site_config
from .service import BatchDownloadService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Configurable browser automation downloader prototype."
    )
    parser.add_argument(
        "--query",
        action="append",
        help="Search keyword. Can be repeated to download multiple songs sequentially.",
    )
    parser.add_argument(
        "--config",
        default=str(ensure_default_site_config()),
        help="Path to JSON site config.",
    )
    parser.add_argument(
        "--download-dir",
        default=None,
        help="Directory where downloaded files will be stored.",
    )
    parser.add_argument(
        "--headless",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Run browser in headless mode.",
    )
    parser.add_argument(
        "--user-data-dir",
        default=None,
        help="Persistent browser profile directory used to keep login state.",
    )
    parser.add_argument(
        "--browser-channel",
        default=None,
        choices=["chromium", "chrome", "msedge"],
        help="Browser channel to launch. Use chrome or msedge to reuse the local browser engine.",
    )
    parser.add_argument(
        "--settings",
        default=str(DEFAULT_SETTINGS_PATH),
        help="Path to GUI/app settings JSON file.",
    )
    parser.add_argument(
        "--gui",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Launch the desktop GUI. Defaults to true when no query is provided.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    queries = args.query or []
    should_launch_gui = args.gui if args.gui is not None else not queries
    app_defaults = AppConfig.load(args.settings)

    if should_launch_gui:
        try:
            from .gui import launch_gui
        except ModuleNotFoundError as exc:
            if exc.name in {"tkinter", "_tkinter"}:
                print(
                    "当前 Python 缺少 tkinter，无法启动 GUI。\n"
                    "请安装 tkinter 支持后重试，或使用 --no-gui 走命令行模式。",
                    file=sys.stderr,
                )
                return 2
            raise
        launch_gui(args.settings)
        return 0

    config = SiteConfig.from_file(args.config)
    service = BatchDownloadService(
        config=config,
        download_dir=Path(args.download_dir or app_defaults.download_dir).resolve(),
        headless=args.headless,
        user_data_dir=Path(args.user_data_dir or app_defaults.user_data_dir).resolve(),
        browser_channel=args.browser_channel or app_defaults.browser_channel,
    )
    service.run(queries)
    return 0
