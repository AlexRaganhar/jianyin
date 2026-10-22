"""Small background-job runner for Tkinter without blocking the UI thread."""

from __future__ import annotations

import tkinter as tk
from queue import Empty, Queue
from threading import Event, Thread
from typing import Any, Callable

EventCallback = Callable[[str, str, Any], None]


class JobRunner:
    """Run one job at a time; deliver progress/success/error on the UI thread."""

    def __init__(self, root: tk.Tk, callback: EventCallback) -> None:
        self._root = root
        self._callback = callback
        self._queue: Queue[tuple[str, str, Any]] = Queue()
        self._cancel = Event()
        self._thread: Thread | None = None
        self._kind: str | None = None
        self._after_id: str | None = None
        self._after_id = self._root.after(100, self._poll)

    @property
    def running(self) -> bool:
        return self._kind is not None

    @property
    def kind(self) -> str | None:
        return self._kind

    def is_cancelled(self) -> bool:
        return self._cancel.is_set()

    def progress(self, payload: dict[str, Any]) -> None:
        if self._kind is not None:
            self._queue.put(("progress", self._kind, payload))

    def start(self, kind: str, job: Callable[[], Any]) -> bool:
        if self.running:
            return False
        self._cancel.clear()
        self._kind = kind

        def runner() -> None:
            try:
                result = job()
            except Exception as error:
                self._queue.put(("error", kind, error))
            else:
                self._queue.put(("success", kind, result))

        self._thread = Thread(target=runner, daemon=True)
        self._thread.start()
        return True

    def cancel(self) -> None:
        self._cancel.set()

    def _poll(self) -> None:
        try:
            while True:
                status, kind, payload = self._queue.get_nowait()
                if status in {"success", "error"}:
                    self._thread = None
                    self._kind = None
                try:
                    self._callback(status, kind, payload)
                except Exception:
                    pass
        except Empty:
            pass
        try:
            self._after_id = self._root.after(100, self._poll)
        except tk.TclError:
            self._after_id = None

    def shutdown(self) -> None:
        self._cancel.set()
        if self._after_id is not None:
            try:
                self._root.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None
