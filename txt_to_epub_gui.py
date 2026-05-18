#!/usr/bin/env python3
"""
pywebview desktop shell for the TXT to EPUB converter.

The UI is built as a React/Vite/Tailwind frontend in frontend/. This launcher
keeps the existing Python converter as the backend, exposes a small API to
JavaScript, and packages cleanly with PyInstaller.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import queue
import sys
import threading
import traceback
import uuid
from pathlib import Path
from typing import Any

try:
    import webview
except ImportError:
    raise SystemExit(
        "Missing dependency: pywebview. Install with `python -m pip install -r requirements-gui.txt`."
    )


sys.dont_write_bytecode = True
import txt_to_epub as converter  # noqa: E402


APP_TITLE = "TXT 转 EPUB 转换器"
AUTO_ENCODING = "自动识别"
ENCODING_OPTIONS = ["自动识别", "utf-8", "gb18030", "big5", "cp950", "utf-16", "utf-16-le", "utf-16-be"]


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def frontend_index() -> Path:
    return app_root() / "frontend" / "dist" / "index.html"


class ConverterApi:
    def __init__(self) -> None:
        self.window: webview.Window | None = None
        self.stop_requested = threading.Event()
        self.event_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.last_output_dir: Path | None = None
        self.run_id: str | None = None

    def attach_window(self, window: webview.Window) -> None:
        self.window = window

    def get_initial_state(self) -> dict[str, Any]:
        return {
            "appTitle": APP_TITLE,
            "encodingOptions": ENCODING_OPTIONS,
            "defaults": {
                "encoding": AUTO_ENCODING,
                "language": converter.DEFAULT_LANGUAGE,
                "recursive": True,
                "overwrite": False,
                "keepTocText": False,
                "allowWeakTitle": False,
                "maxTitleLength": converter.MAX_TITLE_LENGTH,
                "maxCharsPerXhtml": converter.DEFAULT_MAX_CHARS_PER_XHTML,
                "previewLimit": 80,
            },
        }

    def choose_txt_files(self) -> list[str]:
        result = self._dialog(
            webview.OPEN_DIALOG,
            allow_multiple=True,
            file_types=("TXT 文件 (*.txt)", "所有文件 (*.*)"),
        )
        return self._normalize_dialog_result(result)

    def choose_folder(self) -> list[str]:
        result = self._dialog(webview.FOLDER_DIALOG, allow_multiple=True)
        return self._normalize_dialog_result(result)

    def choose_output_dir(self) -> str | None:
        result = self._dialog(webview.FOLDER_DIALOG, allow_multiple=False)
        items = self._normalize_dialog_result(result)
        return items[0] if items else None

    def choose_cover_image(self) -> str | None:
        result = self._dialog(
            webview.OPEN_DIALOG,
            allow_multiple=False,
            file_types=("图片文件 (*.jpg;*.jpeg;*.png;*.gif;*.webp)", "所有文件 (*.*)"),
        )
        items = self._normalize_dialog_result(result)
        return items[0] if items else None

    def choose_font(self) -> str | None:
        result = self._dialog(
            webview.OPEN_DIALOG,
            allow_multiple=False,
            file_types=("字体文件 (*.ttf;*.otf;*.ttc)", "所有文件 (*.*)"),
        )
        items = self._normalize_dialog_result(result)
        return items[0] if items else None

    def start_conversion(self, config: dict[str, Any]) -> dict[str, Any]:
        if self.worker and self.worker.is_alive():
            return {"ok": False, "error": "当前任务还在运行。"}

        try:
            args, input_paths, output_dir = self._build_args(config)
        except Exception as exc:  # noqa: BLE001 - surface validation to frontend.
            return {"ok": False, "error": str(exc)}

        self._clear_events()
        self.stop_requested.clear()
        self.run_id = uuid.uuid4().hex
        self.worker = threading.Thread(
            target=self._run_worker,
            args=(self.run_id, args, input_paths, output_dir),
            daemon=True,
        )
        self.worker.start()
        return {"ok": True, "runId": self.run_id}

    def stop_conversion(self) -> dict[str, Any]:
        self.stop_requested.set()
        self._event("log", message="已请求停止，当前文件处理完后会停下。")
        return {"ok": True}

    def poll_events(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        while True:
            try:
                events.append(self.event_queue.get_nowait())
            except queue.Empty:
                break
        return events

    def open_output_dir(self, path: str | None = None) -> dict[str, Any]:
        target = Path(path).expanduser() if path else self.last_output_dir
        if not target:
            return {"ok": False, "error": "还没有输出目录。"}
        if not target.exists():
            return {"ok": False, "error": f"输出目录不存在：{target}"}
        os.startfile(str(target))  # type: ignore[attr-defined]
        return {"ok": True}

    def _dialog(self, dialog_type: int, **kwargs: Any) -> Any:
        window = self.window or (webview.windows[0] if webview.windows else None)
        if not window:
            return None
        return window.create_file_dialog(dialog_type, **kwargs)

    @staticmethod
    def _normalize_dialog_result(result: Any) -> list[str]:
        if not result:
            return []
        if isinstance(result, (str, os.PathLike)):
            return [str(result)]
        return [str(item) for item in result]

    def _build_args(self, config: dict[str, Any]) -> tuple[argparse.Namespace, list[Path], Path]:
        inputs = [Path(item).expanduser() for item in config.get("inputs", []) if str(item).strip()]
        if not inputs:
            raise ValueError("请先添加至少一个 TXT 文件或文件夹。")

        encoding = str(config.get("encoding") or "").strip()
        if encoding == AUTO_ENCODING:
            encoding = ""

        def parse_int(key: str, label: str, minimum: int) -> int:
            raw = config.get(key)
            try:
                value = int(str(raw).strip())
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{label} 必须是整数。") from exc
            if value < minimum:
                raise ValueError(f"{label} 不能小于 {minimum}。")
            return value

        chapter_regex_text = str(config.get("chapterRegex") or "")
        chapter_regex = [line.strip() for line in chapter_regex_text.splitlines() if line.strip()]
        output_value = str(config.get("outputDir") or "").strip()
        output_dir = Path(output_value).expanduser() if output_value else converter.make_default_output_dir()

        args = argparse.Namespace(
            encoding=encoding or None,
            title=self._optional_text(config.get("title")),
            author=self._optional_text(config.get("author")),
            language=self._optional_text(config.get("language")) or converter.DEFAULT_LANGUAGE,
            publisher=self._optional_text(config.get("publisher")),
            description=self._optional_text(config.get("description")),
            font=self._optional_text(config.get("font")),
            cover_image=self._optional_text(config.get("coverImage")),
            chapter_regex=chapter_regex,
            allow_weak_numbered_title=bool(config.get("allowWeakTitle")),
            max_title_length=parse_int("maxTitleLength", "章节标题最大长度", 1),
            max_chars_per_xhtml=parse_int("maxCharsPerXhtml", "单个 XHTML 最大字符数", 20_000),
            keep_toc_text=bool(config.get("keepTocText")),
            preview=bool(config.get("preview")),
            preview_limit=parse_int("previewLimit", "预览章节数", 1),
            recursive=bool(config.get("recursive")),
            overwrite=bool(config.get("overwrite")),
        )
        return args, inputs, output_dir

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    def _run_worker(self, run_id: str, args: argparse.Namespace, input_paths: list[Path], output_dir: Path) -> None:
        results: list[converter.ConversionResult] = []
        try:
            files = converter.collect_input_files(input_paths, args.recursive)
            if not files:
                raise ValueError("没有找到可转换的 TXT 文件。")

            custom_patterns = converter.compile_custom_patterns(args.chapter_regex)
            if args.allow_weak_numbered_title:
                custom_patterns.append(converter.WEAK_NUMBERED_TITLE_PATTERN)

            if not args.preview:
                output_dir.mkdir(parents=True, exist_ok=True)
                self.last_output_dir = output_dir
                self._event("outputDir", runId=run_id, path=str(output_dir))
                self._event("log", runId=run_id, message=f"输出目录：{output_dir}")

            self._event("started", runId=run_id, total=len(files), preview=args.preview)
            for index, file_path in enumerate(files, start=1):
                if self.stop_requested.is_set():
                    self._event("log", runId=run_id, message="已停止，剩余文件不再处理。")
                    break

                self._event("progress", runId=run_id, current=index - 1, total=len(files), file=str(file_path))
                self._event("log", runId=run_id, message=f"[{index}/{len(files)}] 处理：{file_path}")

                captured = io.StringIO()
                with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
                    result = converter.convert_one(file_path, output_dir, args, custom_patterns)
                printed = captured.getvalue().strip()
                if printed:
                    self._event("log", runId=run_id, message=printed)

                results.append(result)
                self._event("result", runId=run_id, result=self._result_to_dict(result))
                self._event("log", runId=run_id, message=self._format_result(result))
                for warning in result.warnings:
                    self._event("log", runId=run_id, message=f"  警告：{warning}")
                self._event("progress", runId=run_id, current=index, total=len(files), file=str(file_path))

            if results and not args.preview:
                converter.write_reports(output_dir, results)
                self._event("log", runId=run_id, message=f"转换报告：{output_dir / 'conversion_report.txt'}")

            summary = self._summary(results)
            self._event("done", runId=run_id, summary=summary, stopped=self.stop_requested.is_set())
        except Exception as exc:  # noqa: BLE001 - keep desktop process alive and show details.
            self._event("error", runId=run_id, message=str(exc), detail=traceback.format_exc())

    def _event(self, kind: str, **payload: Any) -> None:
        self.event_queue.put({"type": kind, **payload})

    def _clear_events(self) -> None:
        while True:
            try:
                self.event_queue.get_nowait()
            except queue.Empty:
                break

    @staticmethod
    def _result_to_dict(result: converter.ConversionResult) -> dict[str, Any]:
        return {
            "source": result.source,
            "output": result.output,
            "title": result.title,
            "author": result.author,
            "encoding": result.encoding,
            "strictEncoding": result.strict_encoding,
            "chapterCount": result.chapter_count,
            "warnings": result.warnings,
            "status": result.status,
            "error": result.error,
        }

    @staticmethod
    def _summary(results: list[converter.ConversionResult]) -> dict[str, int]:
        return {
            "ok": sum(1 for item in results if item.status == "ok"),
            "failed": sum(1 for item in results if item.status == "failed"),
            "preview": sum(1 for item in results if item.status == "preview"),
            "total": len(results),
        }

    @staticmethod
    def _format_result(result: converter.ConversionResult) -> str:
        if result.status == "ok":
            return f"  已生成：{result.output}\n  书名：{result.title}，章节：{result.chapter_count}，编码：{result.encoding}"
        if result.status == "preview":
            return f"  预览完成：{result.title}，章节：{result.chapter_count}，编码：{result.encoding}"
        return f"  失败：{result.error}"


def main() -> None:
    index = frontend_index()
    if not index.exists():
        raise SystemExit(f"Frontend build not found: {index}. Run `npm install && npm run build` in frontend/.")

    api = ConverterApi()
    window = webview.create_window(
        APP_TITLE,
        index.as_uri(),
        js_api=api,
        width=1220,
        height=780,
        min_size=(1024, 680),
        text_select=True,
    )
    api.attach_window(window)
    webview.start(debug=False)


if __name__ == "__main__":
    main()
