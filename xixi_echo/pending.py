"""待发浮窗：单次=确认后提交；多次=汇总截图一次提交。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .draggable import DragHandle
from .widgets import XButton


def _thumb(png: bytes, height: int = 110) -> QLabel:
    label = QLabel()
    pixmap = QPixmap()
    pixmap.loadFromData(png)
    label.setPixmap(pixmap.scaledToHeight(height, Qt.TransformationMode.SmoothTransformation))
    return label


class PendingWindow(QWidget):
    submitRequested = Signal()
    addMoreRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.shots: list[bytes] = []
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(520)

        card = QWidget()
        card.setObjectName("glassCard")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card)
        self._layout = QVBoxLayout(card)
        self._layout.setContentsMargins(18, 0, 18, 16)
        self._layout.setSpacing(10)
        self._handle = DragHandle(self, "待发评分")
        self._layout.addWidget(self._handle)

        self._title = QLabel()
        self._title.setObjectName("appTitle")
        self._char_label = QLabel()
        self._char_label.setObjectName("meta")
        self._char_label.setStyleSheet(f"color: {theme.ACCENT}; font-weight: 600;")
        self._strip_host = QWidget()
        self._strip_host.setObjectName("thumbStrip")
        self._strip = QHBoxLayout(self._strip_host)
        self._strip.setContentsMargins(8, 8, 8, 8)
        self._strip.setSpacing(8)
        self._empty_hint = QLabel("还没有截图")
        self._empty_hint.setObjectName("hint")

        self._submit_btn = XButton("提交评分", tone="primary")
        self._submit_btn.clicked.connect(self.submitRequested)
        self._add_btn = XButton("再截一张 (F11)", tone="soft")
        self._add_btn.clicked.connect(self.addMoreRequested)
        self._cancel_btn = XButton("取消", tone="ghost")
        self._cancel_btn.clicked.connect(self.reset)

        buttons = QHBoxLayout()
        buttons.addWidget(self._empty_hint, stretch=1)
        buttons.addWidget(self._add_btn)
        buttons.addWidget(self._submit_btn)
        buttons.addWidget(self._cancel_btn)

        self._layout.addWidget(self._title)
        self._layout.addWidget(self._char_label)
        self._layout.addWidget(self._strip_host)
        self._layout.addLayout(buttons)
        self._multi = False
        self._redraw()

    # --- 状态填充 ---

    def set_single(self, png: bytes, char: str) -> None:
        self._multi = False
        self.shots = [png]
        self._add_btn.setVisible(False)
        self._title.setText("确认本次截图")
        self._char_label.setText(f"当前角色：{char}")
        self._redraw()

    def set_multi(self, char: str) -> None:
        self._multi = True
        self._add_btn.setVisible(True)
        self._title.setText("多图评分（一次提交）")
        self._char_label.setText(f"当前角色：{char} · Enter 提交 / F11 继续添加")
        self._redraw()

    def add_shot(self, png: bytes) -> None:
        self.shots.append(png)
        self._redraw()

    def reset(self) -> None:
        self.shots.clear()
        self.hide()
        self._redraw()

    def set_submitting(self, busy: bool) -> None:
        self._submit_btn.setDisabled(busy)
        self._submit_btn.setText("评分中…" if busy else "提交评分")

    # --- 渲染 ---

    def _redraw(self) -> None:
        while self._strip.count():
            item = self._strip.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for png in self.shots[-4:]:
            self._strip.addWidget(_thumb(png))
        if not self.shots:
            self._submit_btn.setEnabled(False)
        else:
            self._submit_btn.setEnabled(True)
        count_text = f"已捕获 {len(self.shots)} 张" if self._multi else ""
        if self._multi:
            self._char_label.setText(self._char_label.text().split(" · ")[0] + f" · {count_text}")
        self.adjustSize()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.shots:
            self.submitRequested()
        elif event.key() == Qt.Key.Key_Escape:
            self.reset()
