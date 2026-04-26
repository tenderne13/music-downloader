from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class SiteConfig:
    search_url_template: str
    search_result_links: list[str]
    detail_download_buttons: list[str]
    quality_download_buttons: list[str]
    storage_row_selectors: list[str]
    row_name_selectors: list[str]
    row_size_selectors: list[str]
    row_download_selectors: list[str]
    pre_download_confirm_buttons: list[str] = field(default_factory=list)
    post_download_confirm_buttons: list[str] = field(default_factory=list)
    post_quality_close_buttons: list[str] = field(default_factory=list)
    directory_name_pattern: str = r"^\d+$"
    max_depth: int = 2
    expect_new_page_after_result_click: bool = False
    expect_new_page_after_quality_click: bool = True
    timeout_ms: int = 15000

    @classmethod
    def from_file(cls, path: str | Path) -> "SiteConfig":
        config_path = Path(path)
        raw = config_path.read_text(encoding="utf-8").strip()
        if not raw:
            raise ValueError(f"Site config is empty: {config_path}")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Site config is not valid JSON: {config_path}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"Site config root must be a JSON object: {config_path}")
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SiteConfig":
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def save_to_file(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
