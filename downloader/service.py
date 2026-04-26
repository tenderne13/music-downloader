from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import SiteConfig
from .runner import DownloadRunner


LogCallback = Callable[[str, str], None]
ProgressCallback = Callable[[dict[str, object]], None]


@dataclass(slots=True)
class DownloadTask:
    query: str


class BatchDownloadService:
    def __init__(
        self,
        *,
        config: SiteConfig,
        download_dir: Path,
        headless: bool,
        user_data_dir: Path,
        browser_channel: str,
        log_callback: LogCallback | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        self.config = config
        self.download_dir = download_dir
        self.headless = headless
        self.user_data_dir = user_data_dir
        self.browser_channel = browser_channel
        self.log_callback = log_callback
        self.progress_callback = progress_callback
        self._stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True

    def run(self, queries: list[str]) -> str:
        tasks = [DownloadTask(query=item.strip()) for item in queries if item.strip()]
        if not tasks:
            raise ValueError("至少需要提供一个歌曲关键字。")

        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.user_data_dir.mkdir(parents=True, exist_ok=True)

        total = len(tasks)
        self._emit_progress(event="batch_started", total=total, completed=0)

        for index, task in enumerate(tasks, start=1):
            if self._stop_requested:
                self._log("批量", "收到停止请求，批量下载已中止。")
                self._emit_progress(event="batch_stopped", total=total, completed=index - 1)
                return "stopped"

            self._log("批量", f"开始任务 {index}/{total}: {task.query}")
            self._emit_progress(
                event="task_started",
                total=total,
                completed=index - 1,
                current=index,
                query=task.query,
                task_progress=0,
            )

            runner = DownloadRunner(
                config=self.config,
                query=task.query,
                download_dir=self.download_dir,
                headless=self.headless,
                user_data_dir=self.user_data_dir,
                browser_channel=self.browser_channel,
                log_callback=self._handle_runner_log(index=index, total=total, query=task.query),
            )
            runner.run()

            self._emit_progress(
                event="task_completed",
                total=total,
                completed=index,
                current=index,
                query=task.query,
                task_progress=100,
            )
            self._log("批量", f"任务完成 {index}/{total}: {task.query}")

        self._emit_progress(event="batch_completed", total=total, completed=total)
        return "completed"

    def _handle_runner_log(self, *, index: int, total: int, query: str) -> LogCallback:
        def callback(stage: str, message: str) -> None:
            self._log(stage, message)
            self._emit_progress(
                event="task_log",
                total=total,
                completed=index - 1,
                current=index,
                query=query,
                stage=stage,
                message=message,
                task_progress=self._progress_from_stage(stage),
            )

        return callback

    def _progress_from_stage(self, stage: str) -> int:
        step_map = {
            "步骤 1/5": 20,
            "步骤 2/5": 40,
            "步骤 3/5": 60,
            "步骤 4/5": 80,
            "步骤 5/5": 100,
        }
        return step_map.get(stage, 0)

    def _log(self, stage: str, message: str) -> None:
        if self.log_callback is not None:
            self.log_callback(stage, message)

    def _emit_progress(self, **payload: object) -> None:
        if self.progress_callback is not None:
            self.progress_callback(payload)
