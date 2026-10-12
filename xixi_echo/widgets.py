"""小组件：按钮、KeyCapture 热键捕捉、Toast 深玻璃药丸。"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QLabel, QPushButton, QWidget

_PURE_MODIFIER_KEYS = {
    Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt,
    Qt.Key.Key_Meta, Qt.Key.Key_AltGr, Qt.Key.Key_unknown,
}


class KeyCaptureButton(QPushButton):
    """点击进入捕获模式，按下任意组合键完成设置；Esc 取消。"""

    bindingCaptured = Signal(str)

    def __init__(self, binding: str = "", parent: QWidget | None = None) -> None:
        super().__init__(binding or "点击设置热键", parent)
        self._capturing = False
        self._previous = binding
        self.clicked.connect(self._start_capture)

    def set_binding(self, binding: str) -> None:
        self._previous = binding
        self.setText(binding)

    def _start_capture(self) -> None:
        self._previous = self.text()
        self._capturing = True
        self.setText("按下组合键…（Esc 取消）")
        self.setFocus()

    def _stop(self, restore: str | None = None) -> None:
        self._capturing = False
        if restore is not None:
            self.setText(restore)
        self.clearFocus()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if not self._capturing:
            super().keyPressEvent(event)
            return
        key = event.key()
        if key in _PURE_MODIFIER_KEYS or key == Qt.Key.Key_unknown:
            self.setText("再按一个普通键…")
            event.accept()
            return
        if key == Qt.Key.Key_Escape:
            self._stop(self._previous)
            event.accept()
            return
        # PySide6 的 KeyboardModifier | Key 需要 QKeyCombination 桥接（key 必须是枚举）
        from PySide6.QtCore import QKeyCombination

        combo = QKeyCombination(event.modifiers(), Qt.Key(key))
        text = QKeySequence(combo.toCombined()).toString(QKeySequence.SequenceFormat.NativeText)
        self._capturing = False
        if text:
            self.setText(text)
            self.bindingCaptured.emit(text)
        else:
            self._stop(self._previous)
        event.accept()


class XButton(QPushButton):
    def __init__(self, text: str, tone: str = "soft", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setProperty("tone", tone)
        self.setCursor(Qt.CursorShape.PointingHandCursor)


class Toast(QLabel):
    """右下角深玻璃药丸，自动消失。"""

    def __init__(self, text: str, tone: str = "info") -> None:
        super().__init__(text)
        self.setObjectName("toast")
        self.setProperty("tone", tone)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setWordWrap(True)
        self.setMaximumWidth(420)
        self.adjustSize()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)


def show_toast(text: str, tone: str = "info", duration_ms: int = 2600) -> None:
    toast = Toast(text, tone)
    toast.adjustSize()
    screen = toast.screen()
    if screen is not None:
        geo = screen.availableGeometry()
        toast.move(geo.right() - toast.width() - 24, geo.bottom() - toast.height() - 24)
    toast.show()
    QTimer.singleShot(duration_ms, toast.deleteLater)
