from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .runtime import (
    default_browser_profile_dir,
    default_download_dir,
    default_settings_path,
    ensure_default_site_config,
)

DEFAULT_SETTINGS_PATH = default_settings_path()


@dataclass
class AppConfig:
    queries: list[str] = field(default_factory=list)
    site_config_path: str = str(ensure_default_site_config())
    download_dir: str = str(default_download_dir())
    user_data_dir: str = str(default_browser_profile_dir())
    browser_channel: str = "chrome"
    headless: bool = False
    auto_save_on_start: bool = True

    @classmethod
    def default(cls) -> "AppConfig":
        return cls()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppConfig":
        base = cls.default()
        merged = asdict(base)
        merged.update(data)
        merged["queries"] = [str(item).strip() for item in merged.get("queries", []) if str(item).strip()]
        return cls(**merged)

    @classmethod
    def load(cls, path: str | Path = DEFAULT_SETTINGS_PATH) -> "AppConfig":
        settings_path = Path(path)
        if not settings_path.exists():
            return cls.default()
        try:
            raw = settings_path.read_text(encoding="utf-8").strip()
            if not raw:
                return cls.default()
            data = json.loads(raw)
        except (OSError, json.JSONDecodeError):
            return cls.default()
        if not isinstance(data, dict):
            return cls.default()
        return cls.from_dict(data)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def save(self, path: str | Path = DEFAULT_SETTINGS_PATH) -> None:
        Path(path).write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
