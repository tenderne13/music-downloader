from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from .app_config import AppConfig, DEFAULT_SETTINGS_PATH
from .config import SiteConfig
from .runtime import app_icon_path
from .service import BatchDownloadService


class MusicDownloaderGUI:
    def __init__(self, settings_path: str | Path = DEFAULT_SETTINGS_PATH) -> None:
        self.root = tk.Tk()
        self.root.title("Music Downloader")
        self.root.geometry("1120x760")
        self.root.minsize(980, 680)
        self._window_icon_image: tk.PhotoImage | None = None
        self._apply_window_icon()

        self.settings_path = Path(settings_path)
        self.event_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.current_service: BatchDownloadService | None = None

        self.app_config = AppConfig.load(self.settings_path)
        self.site_config_path = Path(self.app_config.site_config_path)
        self.site_config = self._load_site_config(self.site_config_path)

        self.status_var = tk.StringVar(value="就绪")
        self.current_song_var = tk.StringVar(value="当前任务: 无")
        self.overall_var = tk.StringVar(value="批量进度: 0/0")
        self.task_progress_var = tk.IntVar(value=0)
        self.batch_progress_var = tk.IntVar(value=0)

        self._build_ui()
        self._load_values_into_form()
        self.root.after(200, self._drain_events)

    def run(self) -> None:
        self.root.mainloop()

    def _apply_window_icon(self) -> None:
        icon_path = app_icon_path()
        if icon_path is None:
            return

        try:
            if icon_path.suffix.lower() == ".ico":
                self.root.iconbitmap(default=str(icon_path))
                return
            if icon_path.suffix.lower() == ".png":
                self._window_icon_image = tk.PhotoImage(file=str(icon_path))
                self.root.iconphoto(True, self._window_icon_image)
        except Exception:
            self._window_icon_image = None

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        notebook = ttk.Notebook(self.root)
        notebook.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)

        task_tab = ttk.Frame(notebook, padding=12)
        site_tab = ttk.Frame(notebook, padding=12)
        log_tab = ttk.Frame(notebook, padding=12)
        notebook.add(task_tab, text="任务配置")
        notebook.add(site_tab, text="站点配置")
        notebook.add(log_tab, text="运行日志")

        self._build_task_tab(task_tab)
        self._build_site_tab(site_tab)
        self._build_log_tab(log_tab)

    def _build_task_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)

        app_frame = ttk.LabelFrame(parent, text="应用参数", padding=12)
        app_frame.grid(row=0, column=0, sticky="ew")
        app_frame.columnconfigure(1, weight=1)

        self.site_config_var = tk.StringVar()
        self.download_dir_var = tk.StringVar()
        self.user_data_dir_var = tk.StringVar()
        self.browser_channel_var = tk.StringVar()
        self.show_browser_var = tk.BooleanVar(value=True)

        self._labeled_entry(
            app_frame,
            row=0,
            label="站点配置文件",
            variable=self.site_config_var,
            button_text="选择文件",
            button_command=self._choose_site_config,
        )
        self._labeled_entry(
            app_frame,
            row=1,
            label="下载目录",
            variable=self.download_dir_var,
            button_text="选择目录",
            button_command=lambda: self._choose_directory(self.download_dir_var),
        )
        self._labeled_entry(
            app_frame,
            row=2,
            label="浏览器用户目录",
            variable=self.user_data_dir_var,
            button_text="选择目录",
            button_command=lambda: self._choose_directory(self.user_data_dir_var),
        )

        ttk.Label(app_frame, text="浏览器通道").grid(row=3, column=0, sticky="w", pady=6)
        channel_box = ttk.Combobox(
            app_frame,
            textvariable=self.browser_channel_var,
            values=("chromium", "chrome", "msedge"),
            state="readonly",
        )
        channel_box.grid(row=3, column=1, sticky="ew", pady=6, padx=(0, 8))
        ttk.Checkbutton(
            app_frame,
            text="显示浏览器操作（首次登录建议开启）",
            variable=self.show_browser_var,
        ).grid(row=3, column=2, sticky="w", pady=6)
        ttk.Label(
            app_frame,
            text="首次需要网盘登录时建议显示浏览器；后续复用同一用户目录时可关闭，程序会在后台静默执行。",
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(0, 4))

        queue_frame = ttk.LabelFrame(parent, text="歌曲队列", padding=12)
        queue_frame.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        queue_frame.columnconfigure(0, weight=1)
        queue_frame.rowconfigure(1, weight=1)

        ttk.Label(queue_frame, text="每行一个歌曲关键字，程序会按顺序逐个下载。").grid(
            row=0,
            column=0,
            sticky="w",
            pady=(0, 8),
        )
        self.query_text = tk.Text(queue_frame, height=10, wrap="word")
        self.query_text.grid(row=1, column=0, sticky="nsew")

        action_frame = ttk.Frame(parent)
        action_frame.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        action_frame.columnconfigure(4, weight=1)

        ttk.Button(action_frame, text="加载配置", command=self._reload_all_configs).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(action_frame, text="保存配置", command=self._save_all_configs).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(action_frame, text="开始下载", command=self._start_download).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(action_frame, text="停止队列", command=self._request_stop).grid(row=0, column=3)
        ttk.Label(action_frame, textvariable=self.status_var).grid(row=0, column=4, sticky="e")

        progress_frame = ttk.LabelFrame(parent, text="运行进度", padding=12)
        progress_frame.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        progress_frame.columnconfigure(0, weight=1)

        ttk.Label(progress_frame, textvariable=self.current_song_var).grid(row=0, column=0, sticky="w")
        ttk.Progressbar(progress_frame, variable=self.task_progress_var, maximum=100).grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(8, 12),
        )
        ttk.Label(progress_frame, textvariable=self.overall_var).grid(row=2, column=0, sticky="w")
        ttk.Progressbar(progress_frame, variable=self.batch_progress_var, maximum=100).grid(
            row=3,
            column=0,
            sticky="ew",
            pady=(8, 0),
        )

    def _build_site_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)
        for row in range(7):
            parent.rowconfigure(row, weight=1 if row >= 2 else 0)

        self.search_url_var = tk.StringVar()
        self.directory_pattern_var = tk.StringVar()
        self.max_depth_var = tk.StringVar()
        self.timeout_var = tk.StringVar()
        self.expect_result_page_var = tk.BooleanVar()
        self.expect_quality_page_var = tk.BooleanVar()

        base_frame = ttk.LabelFrame(parent, text="基础规则", padding=12)
        base_frame.grid(row=0, column=0, columnspan=2, sticky="ew")
        base_frame.columnconfigure(1, weight=1)

        ttk.Label(base_frame, text="搜索 URL 模板").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Entry(base_frame, textvariable=self.search_url_var).grid(row=0, column=1, sticky="ew", pady=6)
        ttk.Label(base_frame, text="目录名正则").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Entry(base_frame, textvariable=self.directory_pattern_var).grid(row=1, column=1, sticky="ew", pady=6)
        ttk.Label(base_frame, text="最大目录深度").grid(row=2, column=0, sticky="w", pady=6)
        ttk.Entry(base_frame, textvariable=self.max_depth_var).grid(row=2, column=1, sticky="ew", pady=6)
        ttk.Label(base_frame, text="超时毫秒").grid(row=3, column=0, sticky="w", pady=6)
        ttk.Entry(base_frame, textvariable=self.timeout_var).grid(row=3, column=1, sticky="ew", pady=6)
        ttk.Checkbutton(
            base_frame,
            text="搜索结果点击后打开新页面",
            variable=self.expect_result_page_var,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=6)
        ttk.Checkbutton(
            base_frame,
            text="音质按钮点击后打开新页面",
            variable=self.expect_quality_page_var,
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=6)

        self.selector_widgets: dict[str, tk.Text] = {}
        selector_specs = [
            ("search_result_links", "搜索结果选择器", 1, 0),
            ("detail_download_buttons", "详情下载按钮", 1, 1),
            ("quality_download_buttons", "音质下载按钮", 2, 0),
            ("storage_row_selectors", "文件行选择器", 2, 1),
            ("row_name_selectors", "文件名选择器", 3, 0),
            ("row_size_selectors", "文件大小选择器", 3, 1),
            ("row_download_selectors", "最终下载按钮", 4, 0),
            ("pre_download_confirm_buttons", "下载前确认弹窗", 4, 1),
            ("post_download_confirm_buttons", "下载后确认弹窗", 5, 0),
            ("post_quality_close_buttons", "音质页遮挡关闭按钮", 5, 1),
        ]
        for field_name, title, row, column in selector_specs:
            frame = ttk.LabelFrame(parent, text=title, padding=8)
            frame.grid(row=row, column=column, sticky="nsew", padx=(0, 8) if column == 0 else 0, pady=(12, 0))
            frame.columnconfigure(0, weight=1)
            frame.rowconfigure(0, weight=1)
            text = tk.Text(frame, height=6, wrap="word")
            text.grid(row=0, column=0, sticky="nsew")
            self.selector_widgets[field_name] = text

    def _build_log_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        self.log_text = tk.Text(parent, wrap="word", state="disabled")
        self.log_text.grid(row=0, column=0, sticky="nsew")

    def _labeled_entry(
        self,
        parent: ttk.Frame,
        *,
        row: int,
        label: str,
        variable: tk.StringVar,
        button_text: str,
        button_command: Callable[[], None],
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=6)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=6, padx=(0, 8))
        ttk.Button(parent, text=button_text, command=button_command).grid(row=row, column=2, sticky="ew", pady=6)

    def _choose_directory(self, variable: tk.StringVar) -> None:
        selected = filedialog.askdirectory(initialdir=variable.get() or ".")
        if selected:
            variable.set(selected)

    def _choose_site_config(self) -> None:
        selected = filedialog.askopenfilename(
            title="选择站点配置文件",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
            initialdir=str(Path(self.site_config_var.get()).resolve().parent) if self.site_config_var.get() else ".",
        )
        if not selected:
            return

        self.site_config_var.set(selected)
        self.site_config_path = Path(selected)
        self.site_config = self._load_site_config(self.site_config_path)
        self._load_site_config_into_form()
        self._append_log("config", f"已加载站点配置: {self.site_config_path}")

    def _reload_all_configs(self) -> None:
        self.app_config = AppConfig.load(self.settings_path)
        self.site_config_path = Path(self.app_config.site_config_path)
        self.site_config = self._load_site_config(self.site_config_path)
        self._load_values_into_form()
        self._append_log("config", f"已从 {self.settings_path} 重新加载配置")

    def _load_values_into_form(self) -> None:
        self.site_config_var.set(self.app_config.site_config_path)
        self.download_dir_var.set(self.app_config.download_dir)
        self.user_data_dir_var.set(self.app_config.user_data_dir)
        self.browser_channel_var.set(self.app_config.browser_channel)
        self.show_browser_var.set(not self.app_config.headless)

        self.query_text.delete("1.0", tk.END)
        if self.app_config.queries:
            self.query_text.insert("1.0", "\n".join(self.app_config.queries))

        self._load_site_config_into_form()

    def _load_site_config_into_form(self) -> None:
        self.search_url_var.set(self.site_config.search_url_template)
        self.directory_pattern_var.set(self.site_config.directory_name_pattern)
        self.max_depth_var.set(str(self.site_config.max_depth))
        self.timeout_var.set(str(self.site_config.timeout_ms))
        self.expect_result_page_var.set(self.site_config.expect_new_page_after_result_click)
        self.expect_quality_page_var.set(self.site_config.expect_new_page_after_quality_click)

        for field_name, widget in self.selector_widgets.items():
            widget.delete("1.0", tk.END)
            values = getattr(self.site_config, field_name)
            widget.insert("1.0", "\n".join(values))

    def _collect_queries(self) -> list[str]:
        raw = self.query_text.get("1.0", tk.END)
        return [line.strip() for line in raw.splitlines() if line.strip()]

    def _collect_site_config(self) -> SiteConfig:
        data = {
            "search_url_template": self.search_url_var.get().strip(),
            "search_result_links": self._text_lines(self.selector_widgets["search_result_links"]),
            "detail_download_buttons": self._text_lines(self.selector_widgets["detail_download_buttons"]),
            "quality_download_buttons": self._text_lines(self.selector_widgets["quality_download_buttons"]),
            "storage_row_selectors": self._text_lines(self.selector_widgets["storage_row_selectors"]),
            "row_name_selectors": self._text_lines(self.selector_widgets["row_name_selectors"]),
            "row_size_selectors": self._text_lines(self.selector_widgets["row_size_selectors"]),
            "row_download_selectors": self._text_lines(self.selector_widgets["row_download_selectors"]),
            "pre_download_confirm_buttons": self._text_lines(self.selector_widgets["pre_download_confirm_buttons"]),
            "post_download_confirm_buttons": self._text_lines(self.selector_widgets["post_download_confirm_buttons"]),
            "post_quality_close_buttons": self._text_lines(self.selector_widgets["post_quality_close_buttons"]),
            "directory_name_pattern": self.directory_pattern_var.get().strip() or r"^\d+$",
            "max_depth": int(self.max_depth_var.get().strip() or "2"),
            "expect_new_page_after_result_click": self.expect_result_page_var.get(),
            "expect_new_page_after_quality_click": self.expect_quality_page_var.get(),
            "timeout_ms": int(self.timeout_var.get().strip() or "15000"),
        }
        return SiteConfig.from_dict(data)

    def _collect_app_config(self) -> AppConfig:
        return AppConfig(
            queries=self._collect_queries(),
            site_config_path=self.site_config_var.get().strip() or "site_config.example.json",
            download_dir=self.download_dir_var.get().strip() or "downloads",
            user_data_dir=self.user_data_dir_var.get().strip() or ".browser-profile",
            browser_channel=self.browser_channel_var.get().strip() or "chromium",
            headless=not self.show_browser_var.get(),
        )

    def _save_all_configs(self) -> bool:
        try:
            app_config = self._collect_app_config()
            site_config = self._collect_site_config()
        except Exception as exc:
            messagebox.showerror("保存失败", f"配置格式有误: {exc}")
            return False

        site_path = Path(app_config.site_config_path)
        site_path.parent.mkdir(parents=True, exist_ok=True)
        site_config.save_to_file(site_path)
        app_config.save(self.settings_path)

        self.app_config = app_config
        self.site_config = site_config
        self.site_config_path = site_path
        self._append_log("config", f"应用配置已保存: {self.settings_path}")
        self._append_log("config", f"站点配置已保存: {site_path}")
        self.status_var.set("配置已保存")
        return True

    def _start_download(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            messagebox.showinfo("任务进行中", "当前已有下载任务在运行，请等待完成或先停止队列。")
            return

        if not self._save_all_configs():
            return

        queries = self._collect_queries()
        if not queries:
            messagebox.showwarning("缺少歌曲", "请至少填写一个歌曲关键字。")
            return

        self.task_progress_var.set(0)
        self.batch_progress_var.set(0)
        self.current_song_var.set("当前任务: 准备启动")
        self.overall_var.set(f"批量进度: 0/{len(queries)}")
        self.status_var.set("下载中")

        app_config = self._collect_app_config()
        site_config = self._collect_site_config()

        self._append_log(
            "config",
            "浏览器显示模式: 显示操作界面" if not app_config.headless else "浏览器显示模式: 后台静默运行",
        )

        self.current_service = BatchDownloadService(
            config=site_config,
            download_dir=Path(app_config.download_dir).resolve(),
            headless=app_config.headless,
            user_data_dir=Path(app_config.user_data_dir).resolve(),
            browser_channel=app_config.browser_channel,
            log_callback=self._queue_log_event,
            progress_callback=self._queue_progress_event,
        )

        self.worker = threading.Thread(
            target=self._run_batch_worker,
            args=(queries,),
            daemon=True,
        )
        self.worker.start()

    def _run_batch_worker(self, queries: list[str]) -> None:
        try:
            assert self.current_service is not None
            result = self.current_service.run(queries)
            self.event_queue.put(("done", result))
        except Exception as exc:
            self.event_queue.put(("error", str(exc)))

    def _request_stop(self) -> None:
        if self.current_service is None:
            self.status_var.set("当前没有运行中的任务")
            return
        self.current_service.request_stop()
        self.status_var.set("已请求停止，当前歌曲处理完成后结束")
        self._append_log("batch", "已请求停止队列，当前歌曲结束后会退出。")

    def _queue_log_event(self, stage: str, message: str) -> None:
        self.event_queue.put(("log", (stage, message)))

    def _queue_progress_event(self, payload: dict[str, object]) -> None:
        self.event_queue.put(("progress", payload))

    def _drain_events(self) -> None:
        while True:
            try:
                event_type, payload = self.event_queue.get_nowait()
            except queue.Empty:
                break

            if event_type == "log":
                stage, message = payload
                self._append_log(stage, message)
            elif event_type == "progress":
                self._handle_progress(payload)
            elif event_type == "done":
                if payload == "stopped":
                    self.status_var.set("队列已停止")
                else:
                    self.status_var.set("下载完成")
                self.current_service = None
                self.worker = None
            elif event_type == "error":
                self.status_var.set("下载失败")
                self.current_service = None
                self.worker = None
                messagebox.showerror("下载失败", str(payload))

        self.root.after(200, self._drain_events)

    def _handle_progress(self, payload: dict[str, object]) -> None:
        event = str(payload.get("event", ""))
        total = int(payload.get("total", 0) or 0)
        completed = int(payload.get("completed", 0) or 0)
        current = int(payload.get("current", 0) or 0)
        query = str(payload.get("query", "") or "")
        task_progress = int(payload.get("task_progress", 0) or 0)

        if total > 0:
            overall_percent = int((completed / total) * 100)
            if event in {"task_started", "task_log"} and total:
                overall_percent = int(((completed + task_progress / 100) / total) * 100)
            self.batch_progress_var.set(min(overall_percent, 100))
            self.overall_var.set(f"批量进度: {completed}/{total}")

        if query:
            self.current_song_var.set(f"当前任务: {current}/{total} - {query}")
        if task_progress:
            self.task_progress_var.set(task_progress)

        if event == "batch_started":
            self.status_var.set("批量任务已启动")
        elif event == "task_started":
            self.task_progress_var.set(0)
            self.status_var.set("正在下载当前歌曲")
        elif event == "task_completed":
            self.task_progress_var.set(100)
            self.overall_var.set(f"批量进度: {completed}/{total}")
        elif event == "batch_completed":
            self.task_progress_var.set(100)
            self.batch_progress_var.set(100)
            self.status_var.set("全部任务已完成")
            self.current_song_var.set("当前任务: 无")
            self.overall_var.set(f"批量进度: {completed}/{total}")
        elif event == "batch_stopped":
            self.status_var.set("队列已停止")

    def _append_log(self, stage: str, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, f"[{stage}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")

    def _load_site_config(self, path: Path) -> SiteConfig:
        if path.exists():
            return SiteConfig.from_file(path)
        return SiteConfig(
            search_url_template="",
            search_result_links=[],
            detail_download_buttons=[],
            quality_download_buttons=[],
            storage_row_selectors=[],
            row_name_selectors=[],
            row_size_selectors=[],
            row_download_selectors=[],
        )

    def _text_lines(self, widget: tk.Text) -> list[str]:
        raw = widget.get("1.0", tk.END)
        return [line.strip() for line in raw.splitlines() if line.strip()]


def launch_gui(settings_path: str | Path = DEFAULT_SETTINGS_PATH) -> None:
    MusicDownloaderGUI(settings_path=settings_path).run()
