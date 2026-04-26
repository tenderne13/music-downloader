from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


APP_NAME = "MusicDownloader"
SITE_CONFIG_BASENAME = "site_config.json"
SETTINGS_BASENAME = "app_settings.json"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> Path:
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent.parent


def user_data_root() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    return Path.home() / f".{APP_NAME.lower()}"


def ensure_user_data_dirs() -> Path:
    root = user_data_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def bundled_site_config_template() -> Path:
    return bundle_root() / "site_config.example.json"


def default_settings_path() -> Path:
    return ensure_user_data_dirs() / SETTINGS_BASENAME


def default_site_config_path() -> Path:
    return ensure_user_data_dirs() / SITE_CONFIG_BASENAME


def default_download_dir() -> Path:
    return ensure_user_data_dirs() / "downloads"


def default_browser_profile_dir() -> Path:
    return ensure_user_data_dirs() / ".browser-profile"


def ensure_default_site_config() -> Path:
    target = default_site_config_path()
    if target.exists():
        return target

    template = bundled_site_config_template()
    if template.exists():
        shutil.copyfile(template, target)
    else:
        target.write_text("{}", encoding="utf-8")
    return target
