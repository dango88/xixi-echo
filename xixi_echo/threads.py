"""把同步函数丢到工作线程执行，用 Qt 信号把结果带回主线程。"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Generic, TypeVar

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger("xixi_echo.threads")

T = TypeVar("T")


class AsyncCall(QObject, Generic[T]):
    ok = Signal(object)
    fail = Signal(str)

    def __init__(
        self,
        fn: Callable[[], T],
        on_ok: Callable[[T], None],
        on_fail: Callable[[str], None],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._fn = fn
        self._on_ok = on_ok
        self._on_fail = on_fail
        self.ok.connect(self._dispatch_ok)
        self.fail.connect(self._dispatch_fail)

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        try:
            result = self._fn()
        except Exception as exc:
            logger.warning("后台任务失败: %s: %s", type(exc).__name__, exc, exc_info=True)
            self.fail.emit(str(exc))
        else:
            self.ok.emit(result)

    def _dispatch_ok(self, result: object) -> None:
        self._on_ok(result)  # type: ignore[arg-type]

    def _dispatch_fail(self, message: str) -> None:
        self._on_fail(message)
