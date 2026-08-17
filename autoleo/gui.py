from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .browser import (
    autoleo_chrome_is_running,
    chrome_profile_dir,
    clear_chrome_profile,
    open_autoleo_chrome,
)
from .lingualeo_client import DEFAULT_CDP_URL, LingualeoClient
from .models import BatchReport, WordSet
from .parser import parse_file


class AutoLeoApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()

        self.title("AutoLeo")
        self.geometry("760x590")
        self.minsize(680, 520)

        self.file_path = tk.StringVar()
        self.selected_word_set = tk.StringVar()
        self.status_text = tk.StringVar(value="Загрузите наборы Lingualeo и выберите TXT-файл.")
        self.progress_text = tk.StringVar(value="—")
        self.word_sets: list[WordSet] = []
        self._events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._progress_active = False

        self._build_ui()
        self.after(100, self._poll_events)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=16)
        root.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(root, text="AutoLeo", font=("Segoe UI", 18, "bold"))
        title.pack(anchor=tk.W)

        subtitle = ttk.Label(
            root,
            text="Добавление слов в выбранный набор Lingualeo через уже открытый Chrome на порту 9223.",
        )
        subtitle.pack(anchor=tk.W, pady=(2, 14))

        browser_row = ttk.LabelFrame(root, text="Браузер AutoLeo", padding=10)
        browser_row.pack(fill=tk.X, pady=(0, 10))

        self.open_browser_button = ttk.Button(
            browser_row,
            text="Открыть в Chrome",
            command=self._open_browser,
        )
        self.open_browser_button.pack(side=tk.LEFT)

        self.clear_browser_button = ttk.Button(
            browser_row,
            text="Очистить данные браузера",
            command=self._clear_browser_data,
        )
        self.clear_browser_button.pack(side=tk.LEFT, padx=(8, 0))

        browser_hint = ttk.Label(
            browser_row,
            text="Открывает отдельный профиль с Lingualeo.",
            foreground="#555",
        )
        browser_hint.pack(side=tk.LEFT, padx=(12, 0))

        set_row = ttk.LabelFrame(root, text="Набор Lingualeo", padding=10)
        set_row.pack(fill=tk.X, pady=(0, 10))

        self.word_set_combo = ttk.Combobox(
            set_row,
            textvariable=self.selected_word_set,
            state="readonly",
            values=[],
        )
        self.word_set_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.load_sets_button = ttk.Button(
            set_row,
            text="Загрузить наборы",
            command=self._load_word_sets,
        )
        self.load_sets_button.pack(side=tk.LEFT, padx=(8, 0))

        file_row = ttk.Frame(root)
        file_row.pack(fill=tk.X)

        file_entry = ttk.Entry(file_row, textvariable=self.file_path)
        file_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        browse_button = ttk.Button(file_row, text="Обзор...", command=self._choose_file)
        browse_button.pack(side=tk.LEFT, padx=(8, 0))

        action_row = ttk.Frame(root)
        action_row.pack(fill=tk.X, pady=(12, 8))

        self.start_button = ttk.Button(action_row, text="Запустить добавление", command=self._start)
        self.start_button.pack(side=tk.LEFT)

        self.progress = ttk.Progressbar(
            action_row,
            mode="determinate",
            maximum=100,
            value=0,
        )
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(12, 0))

        progress_label = ttk.Label(
            action_row,
            textvariable=self.progress_text,
            width=16,
            anchor=tk.E,
        )
        progress_label.pack(side=tk.LEFT, padx=(8, 0))

        status = ttk.Label(root, textvariable=self.status_text)
        status.pack(anchor=tk.W, pady=(0, 8))

        log_frame = ttk.Frame(root)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log = tk.Text(log_frame, wrap=tk.WORD, height=18, state=tk.DISABLED)
        self.log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log.configure(yscrollcommand=scrollbar.set)

        help_text = (
            "Перед загрузкой наборов откройте Chrome кнопкой выше и войдите в Lingualeo."
        )
        footer = ttk.Label(root, text=help_text, foreground="#555")
        footer.pack(anchor=tk.W, pady=(10, 0))

    def _open_browser(self) -> None:
        try:
            profile_dir = open_autoleo_chrome()
        except Exception as exc:
            messagebox.showerror("AutoLeo", str(exc))
            return

        self.status_text.set("Chrome с профилем AutoLeo открыт.")
        self._append_log(f"Chrome открыт. Профиль: {profile_dir}\n")

    def _clear_browser_data(self) -> None:
        profile_dir = chrome_profile_dir()
        if autoleo_chrome_is_running():
            messagebox.showwarning(
                "AutoLeo",
                "Сначала закройте окно Chrome, открытое для AutoLeo, затем повторите очистку.",
            )
            return

        if not profile_dir.exists():
            messagebox.showinfo("AutoLeo", "Данных браузера AutoLeo уже нет.")
            return

        confirmed = messagebox.askyesno(
            "Очистить данные браузера?",
            "Будут удалены вход в аккаунт, cookies и настройки только отдельного "
            f"профиля AutoLeo:\n\n{profile_dir}\n\nПродолжить?",
            icon=messagebox.WARNING,
        )
        if not confirmed:
            return

        try:
            removed = clear_chrome_profile()
        except Exception as exc:
            messagebox.showerror(
                "AutoLeo",
                f"Не удалось очистить данные браузера. Убедитесь, что Chrome закрыт.\n\n{exc}",
            )
            return

        if removed:
            self.status_text.set("Данные браузера AutoLeo очищены.")
            self._append_log(f"Удалён профиль браузера: {profile_dir}\n")
            messagebox.showinfo(
                "AutoLeo",
                "Данные браузера AutoLeo очищены. При следующем открытии Chrome "
                "нужно будет войти в нужный аккаунт.",
            )

    def _load_word_sets(self) -> None:
        if self._worker and self._worker.is_alive():
            return

        self._clear_log()
        self._progress_active = False
        self._set_running(True)
        self.status_text.set("Подключаюсь к Chrome и загружаю наборы Lingualeo...")
        self._worker = threading.Thread(target=self._run_load_word_sets, daemon=True)
        self._worker.start()

    def _run_load_word_sets(self) -> None:
        try:
            with LingualeoClient(cdp_url=DEFAULT_CDP_URL) as client:
                word_sets = client.list_word_sets()

            if not word_sets:
                raise RuntimeError("Lingualeo не вернул ни одного набора слов.")

            self._events.put(("word_sets", word_sets))
        except Exception as exc:
            self._events.put(("error", str(exc)))
        finally:
            self._events.put(("done", None))

    def _choose_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Выберите файл со словами",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if path:
            self.file_path.set(path)

    def _start(self) -> None:
        if self._worker and self._worker.is_alive():
            return

        path_text = self.file_path.get().strip()
        if not path_text:
            messagebox.showwarning("AutoLeo", "Сначала выберите TXT-файл со словами.")
            return

        word_set = self._selected_word_set_or_none()
        if word_set is None:
            messagebox.showwarning("AutoLeo", "Сначала загрузите и выберите набор Lingualeo.")
            return

        path = Path(path_text)
        if not path.exists():
            messagebox.showerror("AutoLeo", f"Файл не найден:\n{path}")
            return

        self._clear_log()
        self._prepare_progress()
        self._progress_active = True
        self._set_running(True)
        self._worker = threading.Thread(target=self._run_import, args=(path, word_set), daemon=True)
        self._worker.start()

    def _run_import(self, path: Path, word_set: WordSet) -> None:
        results = []
        try:
            entries = parse_file(path)
            self._events.put(("progress_start", len(entries)))
            self._events.put(("status", f"Найдено слов: {len(entries)}. Подключаюсь к Chrome..."))
            self._events.put(("log", f"Файл: {path}\n"))
            self._events.put(("log", f"Набор: {word_set.name} (id: {word_set.id})\n\n"))

            with LingualeoClient(
                cdp_url=DEFAULT_CDP_URL,
                word_set_id=word_set.id,
                word_set_name=word_set.name,
            ) as client:
                for index, entry in enumerate(entries, start=1):
                    self._events.put(("status", f"Обработка {index}/{len(entries)}: {entry.word}"))
                    result = client.process_entry(entry)
                    results.append(result)

                    if result.ok:
                        self._events.put(
                            ("log", f"[{index}/{len(entries)}] OK: {entry.word} ({result.action.value})\n")
                        )
                    else:
                        reason = result.error or "проверка результата не прошла"
                        self._events.put(
                            ("log", f"[{index}/{len(entries)}] ОШИБКА: {entry.word}: {reason}\n")
                        )

                    self._events.put(("progress", (index, len(entries))))

                self._events.put(("status", "Перезагружаю страницу Lingualeo..."))
                client.refresh_dictionary_page()
                self._events.put(("log", "\nСтраница Lingualeo перезагружена.\n"))

            report = BatchReport(results)
            self._events.put(("report", report))
        except Exception as exc:
            self._events.put(("error", str(exc)))
        finally:
            self._events.put(("done", None))

    def _poll_events(self) -> None:
        while True:
            try:
                event, payload = self._events.get_nowait()
            except queue.Empty:
                break

            if event == "status":
                self.status_text.set(str(payload))
            elif event == "log":
                self._append_log(str(payload))
            elif event == "progress_start":
                self._prepare_progress(int(payload))
            elif event == "progress":
                current, total = payload
                self._update_progress(int(current), int(total))
            elif event == "word_sets":
                self._set_word_sets(payload)
            elif event == "report":
                self._show_report(payload)
            elif event == "error":
                if self._progress_active:
                    self.progress_text.set("Ошибка")
                self._append_log(f"\nОШИБКА: {payload}\n")
                messagebox.showerror("AutoLeo", str(payload))
            elif event == "done":
                self._set_running(False)
                self._progress_active = False

        self.after(100, self._poll_events)

    def _set_word_sets(self, word_sets: list[WordSet]) -> None:
        self.word_sets = word_sets
        labels = [item.label for item in word_sets]
        self.word_set_combo.configure(values=labels)

        default = word_sets[0]
        self.selected_word_set.set(default.label)
        self.status_text.set(f"Загружено наборов: {len(word_sets)}. Выбран: {default.name}.")
        self._append_log("Наборы Lingualeo загружены:\n")
        for item in word_sets:
            marker = " *" if item.id == default.id else ""
            self._append_log(f"- {item.name} (id: {item.id}){marker}\n")

    def _selected_word_set_or_none(self) -> WordSet | None:
        selected_label = self.selected_word_set.get()
        return next((item for item in self.word_sets if item.label == selected_label), None)

    def _show_report(self, report: BatchReport) -> None:
        text = (
            "\nГотово.\n"
            f"- добавлено: {len(report.added)}\n"
            f"- обновлено: {len(report.updated)}\n"
            f"- уже было правильно: {len(report.already_ok)}\n"
            f"- сброшен статус: {report.reset_status_count}\n"
            f"- ошибок: {len(report.failed)}\n"
        )
        if report.failed:
            text += "\nНе удалось обработать:\n"
            for item in report.failed:
                reason = item.error or "проверка результата не прошла"
                text += f"- {item.entry.word}: {reason}\n"
        self._append_log(text)
        self.status_text.set("Готово." if not report.failed else "Готово, но есть ошибки.")

    def _set_running(self, running: bool) -> None:
        self.start_button.configure(state=tk.DISABLED if running else tk.NORMAL)
        self.load_sets_button.configure(state=tk.DISABLED if running else tk.NORMAL)
        self.open_browser_button.configure(state=tk.DISABLED if running else tk.NORMAL)
        self.clear_browser_button.configure(state=tk.DISABLED if running else tk.NORMAL)
        self.word_set_combo.configure(state=tk.DISABLED if running else "readonly")

    def _prepare_progress(self, total: int | None = None) -> None:
        maximum = max(1, total or 1)
        self.progress.configure(maximum=maximum, value=0)
        if total is None:
            self.progress_text.set("0%")
        else:
            self.progress_text.set(f"0 / {total} (0%)")

    def _update_progress(self, current: int, total: int) -> None:
        safe_total = max(1, total)
        safe_current = min(max(0, current), safe_total)
        percent = round(safe_current / safe_total * 100)
        self.progress.configure(maximum=safe_total, value=safe_current)
        self.progress_text.set(f"{safe_current} / {total} ({percent}%)")

    def _append_log(self, text: str) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, text)
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _clear_log(self) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.delete("1.0", tk.END)
        self.log.configure(state=tk.DISABLED)


def main() -> None:
    app = AutoLeoApp()
    app.mainloop()
