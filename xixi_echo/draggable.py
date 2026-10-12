"""无边框窗口的拖拽把手与置顶切换。

角色浮窗 / 待发浮窗这类 frameless 窗口没有标题栏：顶部把手条承担「移动整窗 +
置顶切换」，按住把手移动、点图钉固定置顶。
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QHBoxLayout, QFrame, QLabel, QPushButton, QWidget


class DragHandle(QFrame):
    """浮窗顶部的拖拽把手：抓住把手条移动整窗，右侧是置顶切换按钮。"""

    def __init__(self, window: QWidget, title: str = "") -> None:
        super().__init__(window)
        self._win = window
        self._offset: QPoint | None = None
        self.setFixedHeight(34)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self._title = QLabel(title)
        self._title.setObjectName("dragTitle")
        self._pin_btn = QPushButton("置顶")
        self._pin_btn.setObjectName("pinBtn")
        self._pin_btn.setCheckable(True)
        self._pin_btn.setFixedSize(44, 22)
        self._pin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pin_btn.setToolTip("置顶 / 取消置顶")
        # checkable 按钮：toggled 自带新状态，按状态设窗口而不是再翻转
        self._pin_btn.toggled.connect(self._toggle_pin)

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 0, 8, 0)
        row.addWidget(self._title)
        row.addStretch(1)
        row.addWidget(self._pin_btn)

    def _toggle_pin(self, checked: bool) -> None:
        self._win.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, checked)
        self._win.show()

    def set_pinned(self, pinned: bool) -> None:
        # 同步按钮状态但不再次触发窗口切换（阻塞 toggled）
        self._pin_btn.blockSignals(True)
        self._pin_btn.setChecked(pinned)
        self._pin_btn.blockSignals(False)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._offset = event.globalPosition().toPoint() - self._win.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._win.move(event.globalPosition().toPoint() - self._offset)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._offset = None
