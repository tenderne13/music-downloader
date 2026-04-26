from __future__ import annotations

import re
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import quote, urljoin

from playwright.sync_api import BrowserContext, Download, Locator, Page, TimeoutError, sync_playwright

from .config import SiteConfig


@dataclass(slots=True)
class FileEntry:
    row: Locator
    name: str
    size_text: str
    size_bytes: float


class DownloadRunner:
    def __init__(
        self,
        *,
        config: SiteConfig,
        query: str,
        download_dir: Path,
        headless: bool,
        user_data_dir: Path,
        browser_channel: str,
        log_callback: Callable[[str, str], None] | None = None,
    ) -> None:
        self.config = config
        self.query = query
        self.download_dir = download_dir
        self.headless = headless
        self.user_data_dir = user_data_dir
        self.browser_channel = browser_channel
        self.log_callback = log_callback

    def run(self) -> None:
        with sync_playwright() as playwright:
            self.user_data_dir.mkdir(parents=True, exist_ok=True)
            self._log(
                "初始化",
                (
                    f"启动持久化浏览器: channel={self.browser_channel}, "
                    f"headless={self.headless}, profile={self.user_data_dir}"
                ),
            )

            launch_kwargs = {
                "user_data_dir": str(self.user_data_dir),
                "headless": self.headless,
                "accept_downloads": True,
            }
            if self.browser_channel != "chromium":
                launch_kwargs["channel"] = self.browser_channel

            try:
                context = playwright.chromium.launch_persistent_context(**launch_kwargs)
            except Exception as exc:
                raise RuntimeError(self._build_browser_launch_error(exc)) from exc
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(self.config.timeout_ms)

            try:
                self._process(context, page)
            except Exception as exc:
                self._log("错误", f"{type(exc).__name__}: {exc}")
                self._log("错误", traceback.format_exc().rstrip())
                self._dump_debug_artifacts(page, "runtime-error")
                raise
            finally:
                self._log("完成", "关闭浏览器上下文")
                context.close()

    def _process(self, context: BrowserContext, page: Page) -> None:
        search_url = self.config.search_url_template.format(query=quote(self.query))
        self._log("步骤 1/5", f"打开搜索页: {search_url}")
        page.goto(search_url, wait_until="domcontentloaded")
        self._log("步骤 1/5", f"搜索页已加载: {page.url}")

        detail_page = self._open_first_result(context, page)
        self._log("步骤 2/5", f"已进入详情页: {detail_page.url}")

        intermediate_page = self._click_download_buttons(context, detail_page)
        self._log("步骤 3/5", f"已到达存储页: {intermediate_page.url}")
        self._dismiss_optional_confirm(intermediate_page, self.config.post_quality_close_buttons)

        storage_page = self._enter_numeric_directory(intermediate_page)
        self._log("步骤 4/5", f"开始扫描列表行: {storage_page.url}")

        download = self._download_largest_file(storage_page, auto_enter_attempts=max(1, self.config.max_depth))
        target_path = self.download_dir / download.suggested_filename
        download.save_as(str(target_path))
        self._log("步骤 5/5", f"下载完成: {target_path}")

    def _open_first_result(self, context: BrowserContext, page: Page) -> Page:
        original_url = page.url
        self._log("结果", "定位第一条搜索结果")
        locator = self._first_visible(page, self.config.search_result_links)
        self._log("结果", f"已找到候选结果，当前页面: {page.url}")

        clicked_page = self._click_and_capture_page(
            context=context,
            page=page,
            locator=locator.first,
            expect_new_page=self.config.expect_new_page_after_result_click,
        )
        self._log("结果", f"已点击搜索结果，当前页面: {clicked_page.url}")

        if clicked_page.url == original_url:
            fallback_href = self._extract_clickable_href(page, locator.first)
            if fallback_href:
                self._log("结果", f"点击后未跳转，回退使用 href: {fallback_href}")
                page.goto(fallback_href, wait_until="domcontentloaded")
                if page.url != original_url:
                    self._log("结果", f"href 回退跳转成功: {page.url}")
                    return page

            self._dump_debug_artifacts(clicked_page, "result-click-no-navigation")
            raise RuntimeError(
                "点击第一条搜索结果后仍停留在搜索页。请检查搜索结果选择器是否命中真实链接，"
                "或者页面是否需要点击别的元素。"
            )

        return clicked_page

    def _click_download_buttons(self, context: BrowserContext, page: Page) -> Page:
        self._log("下载", f"处理详情页动作: {page.url}")
        self._dismiss_optional_confirm(page, self.config.pre_download_confirm_buttons)

        self._log("下载", "查找详情页下载按钮")
        self._first_visible(page, self.config.detail_download_buttons).first.click()
        self._log("下载", "已点击详情页下载按钮")
        self._dismiss_optional_confirm(page, self.config.post_download_confirm_buttons)

        self._log("下载", "查找音质下载按钮")
        quality_button = self._first_visible(page, self.config.quality_download_buttons)
        return self._click_and_capture_page(
            context=context,
            page=page,
            locator=quality_button.first,
            expect_new_page=self.config.expect_new_page_after_quality_click,
        )

    def _enter_numeric_directory(self, page: Page) -> Page:
        pattern = re.compile(self.config.directory_name_pattern)
        for depth in range(self.config.max_depth):
            self._log("目录", f"扫描数字目录，深度 {depth + 1}: {page.url}")
            rows = self._visible_rows(page)
            self._log("目录", f"可见行数: {len(rows)}")

            numeric_row = None
            for row in rows:
                name = self._text_from_row(row, self.config.row_name_selectors)
                if pattern.fullmatch(name):
                    numeric_row = row
                    self._log("目录", f"匹配到数字目录: {name}")
                    break

            if numeric_row is None:
                self._log("目录", "未找到数字目录，停止下钻")
                return page

            if not self._open_row(page, numeric_row):
                self._log("目录", "点击行后未进入新目录，停止下钻")
                return page
            self._clear_selected_rows(page)
            self._log("目录", f"已进入目录，当前页面: {page.url}")
        return page

    def _download_largest_file(self, page: Page, auto_enter_attempts: int) -> Download:
        self._log("文件", f"收集下载候选项: {page.url}")
        entries: list[FileEntry] = []
        mp3_entries: list[FileEntry] = []
        downloadable_unknown_rows: list[tuple[Locator, str]] = []
        folder_rows: list[tuple[Locator, str]] = []

        rows = self._visible_rows(page)
        self._log("文件", f"当前层级可见行数: {len(rows)}")

        for row in rows:
            name = self._text_from_row(row, self.config.row_name_selectors, optional=True)
            raw_row_text = row.inner_text().strip()
            self._log("文件", f"原始行文本: {raw_row_text}")
            if not name:
                self._log("文件", "未识别到名称，跳过该行")
                continue

            size_text = self._extract_size_text(row)
            if self._looks_like_folder(row, name, size_text):
                folder_rows.append((row, name))
                self._log("文件", f"识别为文件夹样式行: {name}")
                continue

            if size_text:
                size_value = parse_size_to_bytes(size_text)
                if size_value > 0:
                    entry = FileEntry(
                        row=row,
                        name=name,
                        size_text=size_text,
                        size_bytes=size_value,
                    )
                    entries.append(entry)
                    if self._is_target_mp3(name):
                        mp3_entries.append(entry)
                    self._log("文件", f"候选文件: {name} ({size_text})")
                    continue

                self._log("文件", f"大小文本无法解析，继续探测: {name} / {size_text}")

            if self._has_download_button(row, page):
                downloadable_unknown_rows.append((row, name))
                self._log("文件", f"可下载但未解析出大小的行: {name}")
            else:
                self._log("文件", f"既没有识别到大小，也没有识别到下载按钮: {name}")

        if mp3_entries:
            target = max(mp3_entries, key=lambda item: item.size_bytes)
            self._log("文件", f"已选择最大的 MP3 文件: {target.name} ({target.size_text})")
            return self._trigger_row_download(page, target.row)

        if entries:
            largest_entry = max(entries, key=lambda item: item.size_bytes)
            self._log("文件", f"仅发现非 MP3 文件，最大的是: {largest_entry.name} ({largest_entry.size_text})")

        if folder_rows and auto_enter_attempts > 0:
            folder_row, folder_name = folder_rows[0]
            self._log("文件", f"未找到文件，尝试进入文件夹样式行: {folder_name}")
            if self._open_row(page, folder_row):
                self._clear_selected_rows(page)
                return self._download_largest_file(page, auto_enter_attempts=auto_enter_attempts - 1)
            if self._has_download_button(folder_row, page):
                self._log("文件", f"文件夹未打开，回退为直接下载该项: {folder_name}")
                return self._trigger_row_download(page, folder_row)

        if downloadable_unknown_rows:
            mp3_unknown_rows = [(row, name) for row, name in downloadable_unknown_rows if self._is_target_mp3(name)]
            if mp3_unknown_rows:
                row, name = mp3_unknown_rows[0]
                self._log("文件", f"回退为第一个可下载但未解析大小的 MP3 行: {name}")
                return self._trigger_row_download(page, row)

        self._dump_debug_artifacts(page, "no-downloadable-file-found")
        raise RuntimeError("当前页面没有找到可下载的 MP3 文件，也没有识别到可进入的文件夹。")

    def _trigger_row_download(self, page: Page, row: Locator) -> Download:
        row.scroll_into_view_if_needed()
        self._ensure_row_not_selected(page, row)
        try:
            row.hover(timeout=1000, force=True)
        except Exception:
            pass

        button = self._find_download_trigger(row, page)
        try:
            with page.expect_download(timeout=30000) as download_info:
                self._log("文件", "点击最终下载按钮")
                if not self._native_mouse_click(page, button):
                    button.click(force=True)
            return download_info.value
        except TimeoutError as exc:
            self._dump_debug_artifacts(page, "download-trigger-timeout")
            raise RuntimeError(self._diagnose_download_failure(page)) from exc

    def _ensure_row_not_selected(self, page: Page, row: Locator) -> None:
        checkbox = row.locator(".ant-checkbox-input, input[type='checkbox']")
        if checkbox.count() == 0:
            self._log("文件", "未找到行复选框，跳过取消选中步骤")
            return

        try:
            is_checked = bool(checkbox.first.is_checked())
        except Exception:
            is_checked = "ant-table-row-selected" in (row.get_attribute("class") or "")

        self._log("文件", f"下载前该行是否已选中: {is_checked}")
        if not is_checked:
            return

        click_target = row.locator(".ant-checkbox-wrapper, .ant-checkbox, td:nth-child(1)")
        target = click_target.first if click_target.count() > 0 else checkbox.first
        self._log("文件", "取消选中该行以显示悬浮下载按钮")

        if not self._native_mouse_click(page, target):
            try:
                target.click(force=True)
            except Exception:
                checkbox.first.evaluate("element => element.click()")

        page.wait_for_timeout(500)

    def _clear_selected_rows(self, page: Page) -> None:
        self._log("文件", "进入目录后清除默认选中行")

        if self._clear_header_selection(page):
            page.wait_for_timeout(500)
            self._dismiss_preview_notice(page)
            return

        selected_rows = page.locator("tr.ant-table-row-selected")
        if selected_rows.count() == 0:
            self._log("文件", "当前目录中未检测到已选中行")
            return

        row = selected_rows.first
        click_target = row.locator(".ant-checkbox-wrapper, .ant-checkbox, td:nth-child(1)")
        target = click_target.first if click_target.count() > 0 else row.locator(".ant-checkbox-input, input[type='checkbox']").first

        if not self._native_mouse_click(page, target):
            try:
                target.click(force=True)
            except Exception:
                target.evaluate("element => element.click()")

        page.wait_for_timeout(500)
        self._dismiss_preview_notice(page)

    def _clear_header_selection(self, page: Page) -> bool:
        header_checkbox = page.locator(
            "thead .ant-checkbox-wrapper, thead .ant-checkbox, th .ant-checkbox-wrapper, th .ant-checkbox"
        )
        if header_checkbox.count() == 0:
            self._log("文件", "未找到表头复选框")
            return False

        checkbox_input = page.locator("thead .ant-checkbox-input, th .ant-checkbox-input")
        is_checked = False
        try:
            if checkbox_input.count() > 0:
                is_checked = bool(checkbox_input.first.is_checked())
            else:
                cls = header_checkbox.first.get_attribute("class") or ""
                is_checked = "ant-checkbox-checked" in cls
        except Exception:
            cls = header_checkbox.first.get_attribute("class") or ""
            is_checked = "ant-checkbox-checked" in cls

        self._log("文件", f"表头复选框是否选中: {is_checked}")
        if not is_checked:
            return False

        self._log("文件", "取消表头复选框以清除所有选中行")
        target = header_checkbox.first
        if not self._native_mouse_click(page, target):
            try:
                target.click(force=True)
            except Exception:
                if checkbox_input.count() > 0:
                    checkbox_input.first.evaluate("element => element.click()")
                else:
                    return False
        return True

    def _dismiss_preview_notice(self, page: Page) -> None:
        preview_close = page.locator(".ant-modal-close, .ant-modal-close-x, button[aria-label='Close']")
        if preview_close.count() == 0:
            return
        try:
            if preview_close.first.is_visible():
                self._log("弹窗", "清除选中后关闭预览弹窗")
                preview_close.first.click(force=True)
                page.wait_for_timeout(300)
        except Exception:
            pass

    def _visible_rows(self, page: Page) -> list[Locator]:
        self._log("行", "定位存储列表行")
        row_root = self._first_visible(page, self.config.storage_row_selectors)
        count = row_root.count()
        self._log("行", f"匹配到的行数: {count}")
        rows: list[Locator] = []
        for index in range(count):
            candidate = row_root.nth(index)
            rows.append(self._normalize_row_locator(candidate))
        return rows

    def _click_and_capture_page(
        self,
        *,
        context: BrowserContext,
        page: Page,
        locator: Locator,
        expect_new_page: bool,
    ) -> Page:
        if expect_new_page:
            self._log("跳转", f"点击后预期打开新页面，当前页面: {page.url}")
            with context.expect_page(timeout=self.config.timeout_ms) as new_page_info:
                locator.click()
            new_page = new_page_info.value
            new_page.wait_for_load_state("domcontentloaded")
            self._log("跳转", f"已打开新页面: {new_page.url}")
            return new_page

        current_url = page.url
        self._log("跳转", f"在当前页面点击: {current_url}")
        locator.click()

        try:
            page.wait_for_url(lambda url: url != current_url, timeout=5000)
            self._log("跳转", f"URL 已变化: {page.url}")
        except TimeoutError:
            self._log("跳转", "5000ms 内 URL 未变化")

        page.wait_for_load_state("domcontentloaded")
        self._log("跳转", f"页面已就绪: {page.url}")
        return page

    def _first_visible(self, scope: Page | Locator, selectors: list[str]) -> Locator:
        last_error: Exception | None = None
        for selector in selectors:
            locator = scope.locator(selector)
            self._log("选择器", f"尝试选择器: {selector}")
            try:
                locator.first.wait_for(state="visible", timeout=self.config.timeout_ms)
                self._log("选择器", f"选择器可见: {selector}")
                return locator
            except TimeoutError as exc:
                self._log("选择器", f"选择器等待超时: {selector}")
                last_error = exc
        joined = ", ".join(selectors)
        raise RuntimeError(f"以下选择器都未能变为可见: {joined}")

    def _normalize_row_locator(self, locator: Locator) -> Locator:
        row_like = locator.locator(
            "xpath=ancestor-or-self::*[self::tr or @role='row' or contains(@class,'ant-table-row') or contains(@class,'file-row')][1]"
        )
        try:
            row_like.first.wait_for(state="attached", timeout=1000)
            tag_name = row_like.first.evaluate("element => element.tagName")
            self._log("行", f"归一化为行容器: {tag_name}")
            return row_like.first
        except TimeoutError:
            self._log("行", "归一化失败，使用原始定位器")
            return locator

    def _dismiss_optional_confirm(self, page: Page, selectors: list[str]) -> None:
        if not selectors:
            self._log("弹窗", "未配置可选确认弹窗选择器")
            return
        for selector in selectors:
            locator = page.locator(selector)
            self._log("弹窗", f"检查确认弹窗选择器: {selector}")
            try:
                locator.first.wait_for(state="visible", timeout=2000)
            except TimeoutError:
                self._log("弹窗", f"确认弹窗选择器不可见: {selector}")
                continue

            locator.first.click()
            try:
                locator.first.wait_for(state="hidden", timeout=3000)
            except TimeoutError:
                pass
            self._log("弹窗", f"已处理确认弹窗: {selector}")
            return
        self._log("弹窗", "没有处理任何确认弹窗")

    def _extract_clickable_href(self, page: Page, locator: Locator) -> str:
        href = locator.evaluate(
            """element => {
                const anchor = element.closest('a') || element.querySelector?.('a');
                return anchor ? anchor.getAttribute('href') : element.getAttribute('href');
            }"""
        )
        if not href:
            return ""
        return urljoin(page.url, href)

    def _dump_debug_artifacts(self, page: Page, label: str) -> None:
        safe_label = re.sub(r"[^a-zA-Z0-9_-]+", "-", label)
        screenshot_path = self.download_dir / f"{safe_label}.png"
        html_path = self.download_dir / f"{safe_label}.html"
        details_path = self.download_dir / f"{safe_label}.txt"
        page.screenshot(path=str(screenshot_path), full_page=True)
        html_path.write_text(page.content(), encoding="utf-8")
        details_path.write_text(
            "\n".join(
                [
                    f"url={page.url}",
                    f"title={page.title()}",
                ]
            ),
            encoding="utf-8",
        )
        self._log("调试", f"截图已保存: {screenshot_path}")
        self._log("调试", f"HTML 已保存: {html_path}")
        self._log("调试", f"详情已保存: {details_path}")

    def _text_from_row(self, row: Locator, selectors: list[str], optional: bool = False) -> str:
        for selector in selectors:
            locator = row.locator(selector)
            if locator.count() == 0:
                continue
            text = locator.first.inner_text().strip()
            if text:
                self._log("文本", f"通过嵌套选择器读取文本 {selector}: {text}")
                return normalize_single_line(text)

        try:
            direct_text = row.inner_text().strip()
            if direct_text:
                self._log("文本", f"直接从行读取文本: {direct_text}")
                return normalize_single_line(direct_text)
        except Exception:
            pass

        if optional:
            return ""
        raise RuntimeError(f"无法从以下选择器读取行文本: {selectors}")

    def _extract_size_text(self, row: Locator) -> str:
        configured_text = self._text_from_row(row, self.config.row_size_selectors, optional=True)
        if configured_text:
            size_match = find_size_token(configured_text)
            if size_match:
                self._log("文本", f"从配置字段识别到大小: {size_match}")
                return size_match
            return normalize_single_line(configured_text)

        cell_texts = row.locator("td, [role='cell']").all_inner_texts()
        for cell_text in cell_texts:
            size_match = find_size_token(cell_text)
            if size_match:
                self._log("文本", f"从表格单元格识别到大小: {size_match}")
                return size_match
        return ""

    def _has_download_button(self, row: Locator, page: Page | None = None) -> bool:
        for selector in self._download_selectors():
            if row.locator(selector).count() > 0:
                self._log("文件", f"命中行级下载选择器: {selector}")
                return True
        if page is not None:
            for selector in self._page_download_selectors():
                if page.locator(selector).count() > 0:
                    self._log("文件", f"命中页面级下载选择器: {selector}")
                    return True
        return False

    def _looks_like_folder(self, row: Locator, name: str, size_text: str) -> bool:
        if self._looks_like_entry_count(size_text):
            return True

        if re.fullmatch(r"\d+", name) and row.locator(".filename-text, .file-click-wrap, .filename").count() > 0:
            return True

        row_text = row.inner_text().strip().lower()
        hints = ("folder", "items", "dir", "目录", "文件夹", "子项")
        return any(hint in row_text for hint in hints)

    def _looks_like_entry_count(self, text: str) -> bool:
        if not text:
            return False
        if parse_size_to_bytes(text) > 0:
            return False

        normalized = text.strip().lower().replace(" ", "")
        if re.fullmatch(r"\d+?", normalized):
            return True
        if re.fullmatch(r"\d+?", normalized):
            return True
        if re.fullmatch(r"\d+items?", normalized):
            return True
        if re.fullmatch(r"\d+files?", normalized):
            return True
        return False

    def _is_target_mp3(self, name: str) -> bool:
        return name.strip().lower().endswith(".mp3")

    def _find_download_trigger(self, row: Locator, page: Page) -> Locator:
        for selector in self._download_selectors():
            locator = row.locator(selector)
            if locator.count() == 0:
                continue
            try:
                locator.first.wait_for(state="visible", timeout=1000)
                return locator.first
            except TimeoutError:
                continue

        for selector in self._page_download_selectors():
            locator = page.locator(selector)
            if locator.count() == 0:
                continue
            try:
                locator.first.wait_for(state="visible", timeout=3000)
                return locator.first
            except TimeoutError:
                continue

        for selector in self._download_selectors():
            locator = row.locator(selector)
            if locator.count() > 0:
                return locator.first

        for selector in self._page_download_selectors():
            locator = page.locator(selector)
            if locator.count() > 0:
                return locator.first

        selectors = ", ".join(self._download_selectors() + self._page_download_selectors())
        raise RuntimeError(f"未找到可用的下载按钮: {selectors}")

    def _download_selectors(self) -> list[str]:
        return [*self.config.row_download_selectors, ".hoitem-down", ".share-hover-menu-download"]

    def _page_download_selectors(self) -> list[str]:
        return [".share-download", "div[title='下载']", "button[title='下载']"]

    def _open_row(self, page: Page, row: Locator) -> bool:
        current_url = page.url
        before_signature = self._page_signature(page)
        row.scroll_into_view_if_needed()

        target, target_label = self._resolve_row_open_target(row)
        self._log("跳转", f"打开行的目标元素: {target_label}")
        self._log("跳转", "尝试在文件名区域通过原生鼠标单击打开")
        try:
            if not self._native_mouse_open(page, target, click_count=1):
                raise RuntimeError("原生单击缺少可点击区域")
        except Exception:
            self._log("跳转", "原生单击失败，回退为派发 DOM click")
            self._dispatch_click(target)

        if self._wait_for_row_open(page, before_signature, current_url):
            return True

        self._log("跳转", "单击无效，尝试在文件名区域原生双击")
        try:
            if not self._native_mouse_open(page, target, click_count=2):
                raise RuntimeError("原生双击缺少可点击区域")
        except Exception:
            self._log("跳转", "原生双击失败，回退为派发 DOM dblclick")
            self._dispatch_dblclick(target)

        if self._wait_for_row_open(page, before_signature, current_url):
            return True

        if target is not row:
            self._log("跳转", "文件名区域操作无效，回退为整行原生双击")
            try:
                if not self._native_mouse_open(page, row, click_count=2):
                    raise RuntimeError("整行原生双击缺少可点击区域")
            except Exception:
                self._dispatch_dblclick(row)

        return self._wait_for_row_open(page, before_signature, current_url)

    def _resolve_row_open_target(self, row: Locator) -> tuple[Locator, str]:
        candidates = [
            (".filename-text", "filename-text"),
            ("td:nth-child(2) .editable-cell", "editable-cell"),
            (".file-name", "file-name"),
            (".filename", "filename"),
            (".file-click-wrap", "file-click-wrap"),
        ]
        for selector, label in candidates:
            locator = row.locator(selector)
            if locator.count() > 0:
                return locator.first, label
        return row, "?"

    def _native_mouse_open(self, page: Page, locator: Locator, click_count: int) -> bool:
        locator.scroll_into_view_if_needed()
        box = locator.bounding_box()
        if not box:
            return False

        x = box["x"] + box["width"] / 2
        y = box["y"] + box["height"] / 2
        self._log("跳转", f"原生鼠标目标区域=({box['x']:.1f},{box['y']:.1f},{box['width']:.1f},{box['height']:.1f}) 点击=({x:.1f},{y:.1f}) 次数={click_count}")
        page.mouse.move(x, y)
        if click_count == 2:
            page.mouse.dblclick(x, y, delay=120)
        else:
            page.mouse.click(x, y)
        return True

    def _native_mouse_click(self, page: Page, locator: Locator) -> bool:
        locator.scroll_into_view_if_needed()
        box = locator.bounding_box()
        if not box:
            return False

        x = box["x"] + box["width"] / 2
        y = box["y"] + box["height"] / 2
        self._log("文件", f"原生鼠标点击区域=({box['x']:.1f},{box['y']:.1f},{box['width']:.1f},{box['height']:.1f}) 点击=({x:.1f},{y:.1f})")
        page.mouse.move(x, y)
        page.mouse.down()
        page.mouse.up()
        return True

    def _wait_for_row_open(self, page: Page, before_signature: str, current_url: str) -> bool:
        try:
            page.wait_for_url(lambda url: url != current_url, timeout=5000)
            self._log("跳转", f"打开行后 URL 已变化: {page.url}")
        except TimeoutError:
            self._log("跳转", "打开行后 URL 未变化，继续等待 DOM 或内容变化")

        try:
            page.wait_for_load_state("domcontentloaded", timeout=3000)
        except TimeoutError:
            pass

        for _ in range(10):
            page.wait_for_timeout(500)
            after_signature = self._page_signature(page)
            if page.url != current_url or after_signature != before_signature:
                self._log("跳转", f"检测到内容变化，视为已打开行: {after_signature}")
                return True
        return False

    def _dispatch_dblclick(self, locator: Locator) -> None:
        locator.evaluate(
            """element => {
                const eventInit = { bubbles: true, cancelable: true, composed: true, detail: 2 };
                element.dispatchEvent(new MouseEvent('mousedown', eventInit));
                element.dispatchEvent(new MouseEvent('mouseup', eventInit));
                element.dispatchEvent(new MouseEvent('click', eventInit));
                element.dispatchEvent(new MouseEvent('mousedown', eventInit));
                element.dispatchEvent(new MouseEvent('mouseup', eventInit));
                element.dispatchEvent(new MouseEvent('click', eventInit));
                element.dispatchEvent(new MouseEvent('dblclick', eventInit));
            }"""
        )

    def _dispatch_click(self, locator: Locator) -> None:
        locator.evaluate(
            """element => {
                const eventInit = { bubbles: true, cancelable: true, composed: true, detail: 1 };
                element.dispatchEvent(new MouseEvent('mousedown', eventInit));
                element.dispatchEvent(new MouseEvent('mouseup', eventInit));
                element.dispatchEvent(new MouseEvent('click', eventInit));
            }"""
        )

    def _page_signature(self, page: Page) -> str:
        locator = page.locator("tbody tr")
        count = min(locator.count(), 5)
        texts: list[str] = []
        try:
            breadcrumb = page.locator(".file-list-breadcrumb, .share-path-wrap, .path-name").first.inner_text().strip()
            if breadcrumb:
                texts.append(normalize_single_line(breadcrumb))
        except Exception:
            pass
        for index in range(count):
            try:
                texts.append(normalize_single_line(locator.nth(index).inner_text()))
            except Exception:
                continue
        return " | ".join(texts)

    def _diagnose_download_failure(self, page: Page) -> str:
        if page.locator("button:has-text('登录账号')").count() > 0 or page.get_by_text("登录账号").count() > 0:
            return "点击下载后没有触发浏览器下载。当前夸克分享页处于未登录状态，可能需要先登录夸克账号后再下载。"

        page_text = page.locator("body").inner_text()
        if "账号涉嫌违规已被封禁" in page_text:
            return "点击下载后没有触发浏览器下载。页面提示当前夸克账号存在风控或封禁限制，暂时无法使用该功能。"
        if "打开客户端" in page_text:
            return "点击下载后没有触发浏览器下载。当前页面可能要求打开客户端或完成额外交互后才能继续下载。"

        return "点击下载按钮后没有触发浏览器下载事件。请检查该站点是否要求登录、客户端中转，或额外确认弹窗。"

    def _build_browser_launch_error(self, exc: Exception) -> str:
        message = str(exc)
        if self.browser_channel == "chromium":
            return (
                "浏览器启动失败。当前使用的是 Playwright 自带的 chromium，请先执行 `playwright install chromium`，"
                "或者在界面里把浏览器通道改成已安装的 `chrome` / `msedge` 后再试。\n"
                f"原始错误: {message}"
                f"原始错误: {message}"
            )
        return (
            f"浏览器启动失败，请确认本机已安装 {self.browser_channel}，"
            "或者切换为 `chromium` 并先执行 `playwright install chromium`。\n"
            f"原始错误: {message}"
        )

    def _log(self, stage: str, message: str) -> None:
        if self.log_callback is not None:
            self.log_callback(stage, message)
        print(f"[{stage}] {message}")


def parse_size_to_bytes(size_text: str) -> float:
    cleaned = size_text.strip().replace(" ", "")
    match = re.fullmatch(r"(?P<value>\d+(?:\.\d+)?)(?P<unit>[KMGTP]?B?)", cleaned, re.I)
    if not match:
        return 0

    value = float(match.group("value"))
    unit = match.group("unit").upper()
    if len(unit) == 1 and unit in {"K", "M", "G", "T", "P"}:
        unit = f"{unit}B"
    scale = {
        "B": 1,
        "KB": 1024,
        "MB": 1024**2,
        "GB": 1024**3,
        "TB": 1024**4,
        "PB": 1024**5,
    }[unit]
    return value * scale


def find_size_token(text: str) -> str:
    match = re.search(r"\d+(?:\.\d+)?\s*(?:[KMGTP]B?|B)\b", text, re.I)
    if not match:
        return ""
    return match.group(0).replace(" ", "")


def normalize_single_line(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    return lines[0]
