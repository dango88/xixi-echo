"""全屏冻结选区浮层：先抓整屏快照再弹遮罩，框选后从快照裁剪，避免把遮罩拍进图里。"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QCursor, QImage, QPainter, QPixmap, QScreen
from PySide6.QtWidgets import QApplication, QRubberBand, QWidget

from . import capture

MIN_SIZE = 8


class RegionOverlay(QWidget):
    captured = Signal(bytes)  # PNG
    cancelled = Signal()

    def __init__(self, screen: QScreen) -> None:
        super().__init__()
        self._screen = screen
        self._origin = None
        self._frozen = capture.grab_region(*self._physical_geometry())
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setGeometry(screen.geometry())
        self._band = QRubberBand(QRubberBand.Shape.Rectangle, self)

    def _physical_geometry(self) -> tuple[int, int, int, int]:
        geo = self._screen.geometry()
        dpr = self._screen.devicePixelRatio()
        return (
            round(geo.x() * dpr),
            round(geo.y() * dpr),
            round(geo.width() * dpr),
            round(geo.height() * dpr),
        )

    def start(self) -> None:
        image = self._frozen
        # 快照尺寸应等于物理尺寸；驱动异常时按实际快照铺满即可
        qimage = QImage(image.tobytes(), image.width, image.height, image.width * 3, QImage.Format.Format_RGB888)
        self._pixmap = QPixmap.fromImage(qimage)
        self.show()
        self.raise_()
        self.activateWindow()
        self.setGeometry(self._screen.geometry())

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self._pixmap)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self._finish_cancel()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.position().toPoint()
            self._band.setGeometry(QRect(self._origin, self._origin))
            self._band.show()
        elif event.button() == Qt.MouseButton.RightButton:
            self._finish_cancel()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._origin is not None:
            self._band.setGeometry(QRect(self._origin, event.position().toPoint()).normalized())

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._origin is None or event.button() != Qt.MouseButton.LeftButton:
            return
        rect = self._band.geometry()
        if rect.width() < MIN_SIZE or rect.height() < MIN_SIZE:
            self._finish_cancel()
            return
        self._band.hide()
        png = self._crop_png(rect)
        self.close()
        self.captured.emit(png)

    def _crop_png(self, rect: QRect) -> bytes:
        dpr = self._frozen.width / self._screen.geometry().width()
        box = (
            round(rect.x() * dpr),
            round(rect.y() * dpr),
            round(rect.right() * dpr) + 1,
            round(rect.bottom() * dpr) + 1,
        )
        return capture.to_png(self._frozen.crop(box))

    def _finish_cancel(self) -> None:
        self.close()
        self.cancelled.emit()


def screen_under_cursor() -> QScreen:
    return QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
