"""结果窗：评分卡完整显示（自适应窗口 + 最大化跟随放大）+ 最近 5 条内存历史。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from . import __version__, theme
from .widgets import XButton

MAX_HISTORY = 5
WINDOW_WIDTH = 560
CHROME_HEIGHT = 180  # 按钮行 + 缩略条 + 边距的估算值


class ZoomViewer(QGraphicsView):
    """Windows 照片式缩放：滚轮以鼠标为锚点、可超 100%、左键拖拽平移。

    实现模式与 marcel-goldschen-ohm/PyQtImageViewer 一致：QGraphicsView +
    AnchorUnderMouse 变换锚点 + ScrollHandDrag。
    """

    zoomChanged = Signal(float)
    MIN_SCALE = 0.1
    MAX_SCALE = 10.0

    def __init__(self, pixmap: QPixmap, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._zoom = 1.0
        scene = QGraphicsScene(self)
        self._item = scene.addPixmap(pixmap)
        self.setScene(scene)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setBackgroundBrush(QColor("#2B2420"))

    def wheelEvent(self, event) -> None:  # noqa: N802
        factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        self.zoom_step(factor)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        # 双击在 适应/1:1 间切换（Windows 照片习惯）
        if self._zoom > 1.05:
            self.fit()
        else:
            self.one_to_one()
        super().mouseDoubleClickEvent(event)

    def current_zoom(self) -> float:
        return self._zoom

    def zoom_step(self, factor: float) -> None:
        new = self._zoom * factor
        if not (self.MIN_SCALE <= new <= self.MAX_SCALE):
            return
        self._zoom = new
        center = self.mapToScene(self.viewport().rect().center())
        self.scale(factor, factor)
        self.centerOn(center)
        self.zoomChanged.emit(self._zoom)

    def one_to_one(self) -> None:
        self.resetTransform()
        self._zoom = 1.0
        self.centerOn(self._item)
        self.zoomChanged.emit(self._zoom)

    def fit(self) -> None:
        self.resetTransform()
        self.fitInView(self._item, Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom = self.transform().m11()
        self.zoomChanged.emit(self._zoom)


class PreviewDialog(QDialog):
    """原图查看器：适应窗口起步，滚轮/按钮缩放（可超 100%），左键拖拽平移，双击切适应/1:1。"""

    def __init__(self, pixmap: QPixmap, matched: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"原图 · {matched}")
        self.setModal(True)
        self.resize(960, 900)

        self._viewer = ZoomViewer(pixmap)
        self._percent = QLabel("100%")
        self._percent.setObjectName("meta")

        zoom_in = XButton("放大", tone="soft")
        zoom_in.clicked.connect(lambda: self._viewer.zoom_step(1.25))
        zoom_out = XButton("缩小", tone="soft")
        zoom_out.clicked.connect(lambda: self._viewer.zoom_step(0.8))
        one_to_one = XButton("1:1", tone="soft")
        one_to_one.clicked.connect(self._viewer.one_to_one)
        fit_btn = XButton("适应窗口", tone="soft")
        fit_btn.clicked.connect(self._viewer.fit)

        self._viewer.zoomChanged.connect(lambda z: self._percent.setText(f"{round(z * 100)}%"))

        buttons = QHBoxLayout()
        buttons.addWidget(self._percent)
        buttons.addStretch(1)
        buttons.addWidget(zoom_out)
        buttons.addWidget(one_to_one)
        buttons.addWidget(fit_btn)
        buttons.addWidget(zoom_in)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.addWidget(self._viewer, stretch=1)
        layout.addLayout(buttons)
        self._viewer.fit()


class ResultWindow(QWidget):
    rescoreRequested = Signal()
    checkUpdateRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Window)
        self.setWindowTitle(f"西西的声骸评分工具 v{__version__}")
        self.setFixedWidth(WINDOW_WIDTH)
        self.setMinimumHeight(420)

        self._history: list[dict[str, object]] = []
        self._index = 0
        self._current: QPixmap | None = None

        self._image_label = QLabel("还没有评分结果")
        self._image_label.setObjectName("hint")
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 点击大图弹原图查看器（见 _open_preview）
        self._image_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._image_label.mousePressEvent = lambda _event: self._open_preview()
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setWidget(self._image_label)
        self._scroll.setMinimumHeight(320)
        # 视口尺寸在布局落定后才变化，窗口 resizeEvent 里读到的是旧值——监听视口自身
        self._scroll.viewport().installEventFilter(self)

        self._meta = QLabel()
        self._meta.setObjectName("meta")

        self._copy_btn = XButton("复制到剪贴板", tone="soft")
        self._copy_btn.clicked.connect(self._copy)
        self._save_btn = XButton("另存为…", tone="soft")
        self._save_btn.clicked.connect(self._save)
        self._rescore_btn = XButton("重新评分", tone="ghost")
        self._rescore_btn.clicked.connect(self.rescoreRequested)
        self._check_update_btn = XButton("检测更新", tone="ghost")
        self._check_update_btn.clicked.connect(self.checkUpdateRequested)
        version_label = QLabel(f"v{__version__}")
        version_label.setObjectName("hint")

        buttons = QHBoxLayout()
        buttons.addWidget(self._meta, stretch=1)
        buttons.addWidget(version_label)
        buttons.addWidget(self._check_update_btn)
        buttons.addWidget(self._copy_btn)
        buttons.addWidget(self._save_btn)
        buttons.addWidget(self._rescore_btn)

        self._strip_host = QWidget()
        self._strip_host.setObjectName("thumbStrip")
        self._strip = QHBoxLayout(self._strip_host)
        self._strip.setContentsMargins(8, 8, 8, 8)
        self._strip.setSpacing(8)
        self._token_label = QLabel("⚪ 尚未申请 token")
        self._token_label.setObjectName("hint")
        self._strip.addWidget(self._token_label)


        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 14)
        layout.addWidget(self._scroll, stretch=1)
        layout.addLayout(buttons)
        layout.addWidget(self._strip_host)

    # --- 数据 ---

    def add_result(self, char: str, image: bytes, matched: str, elapsed_ms: int) -> None:
        self._history.insert(0, {"char": char, "image": image, "matched": matched, "elapsed": elapsed_ms})
        del self._history[MAX_HISTORY:]
        self._index = 0
        self._resize_to_image()
        self._redraw()
        self.show()
        self.raise_()
        self.activateWindow()

    def has_rescorable(self) -> bool:
        return bool(self._history)

    def current_shots(self) -> tuple[str, list[bytes]] | None:
        if not self._history:
            return None
        entry = self._history[self._index]
        return str(entry["char"]), [entry["image"]]

    # --- 渲染 ---

    def set_token_status(self, text: str) -> None:
        self._token_label.setText(text)

    def set_actions_enabled(self, enabled: bool) -> None:
        """未申请 token 时禁用全部操作按钮。"""
        for button in (self._copy_btn, self._save_btn, self._rescore_btn, self._check_update_btn):
            button.setEnabled(enabled)

    def _resize_to_image(self) -> None:
        """窗口高度跟随卡片比例，保证整卡可见；超出屏幕则回落到可滚动。"""
        if not self._history:
            return
        pixmap = QPixmap()
        if not pixmap.loadFromData(self._history[self._index]["image"]):  # type: ignore[arg-type]
            return
        screen = self.screen() or QApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else None
        image_height = int(pixmap.height() * ((WINDOW_WIDTH - 40) / pixmap.width()))
        wanted = image_height + CHROME_HEIGHT
        if avail is not None:
            wanted = min(wanted, int(avail.height() * 0.92))
        self.resize(WINDOW_WIDTH, max(self.minimumHeight(), wanted))

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        from PySide6.QtCore import QEvent

        if watched is self._scroll.viewport() and event.type() == QEvent.Type.Resize:
            self._fit()
        return super().eventFilter(watched, event)

    def _fit(self) -> None:
        """按滚动区可视大小缩放，最大化窗口时图跟着变大。"""
        if self._current is None:
            return
        viewport = self._scroll.viewport().size()
        scaled = self._current.scaled(
            viewport.width() - 4,
            viewport.height() - 4,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._image_label.setPixmap(scaled)

    def _open_preview(self) -> None:
        if self._current is None or self._current.isNull():
            return
        entry = self._history[self._index]
        PreviewDialog(self._current, str(entry["matched"] or entry["char"]), self).exec()

    def _redraw(self) -> None:
        # token 状态标签常驻左下角：清空时跳过它，重排后放回首位
        while self._strip.count():
            item = self._strip.takeAt(0)
            widget = item.widget()
            if widget is not None and widget is not self._token_label:
                widget.deleteLater()
        self._strip.addWidget(self._token_label)
        if not self._history:
            self._image_label.setText("还没有评分结果")
            self._image_label.setPixmap(QPixmap())
            self._current = None
            self._meta.setText("")
            return
        entry = self._history[self._index]
        pixmap = QPixmap()
        pixmap.loadFromData(entry["image"])  # type: ignore[arg-type]
        self._current = pixmap
        self._fit()
        self._meta.setText(f"{entry['matched']} · {entry['elapsed']}ms · 第 {self._index + 1}/{len(self._history)} 条")
        for i, item in enumerate(self._history):
            thumb = QPixmap()
            thumb.loadFromData(item["image"])  # type: ignore[arg-type]
            label = QLabel()
            label.setObjectName("charCard")
            label.setFixedSize(56, 70)
            label.setPixmap(thumb.scaledToHeight(64, Qt.TransformationMode.SmoothTransformation))
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.mousePressEvent = lambda _event, idx=i: self._show(idx)  # noqa: B023
            self._strip.addWidget(label)


    def _show(self, index: int) -> None:
        self._index = index
        self._resize_to_image()
        self._redraw()

    def _copy(self) -> None:
        if self._current is not None:
            QApplication.clipboard().setPixmap(self._current)

    def _save(self) -> None:
        if not self._history:
            return
        entry = self._history[self._index]
        suggested = f"{entry['matched'] or entry['char']}.jpg"
        path, _filter = QFileDialog.getSaveFileName(self, "另存评分卡", suggested, "图片 (*.jpg *.png)")
        if path:
            with open(path, "wb") as f:
                f.write(entry["image"])  # type: ignore[arg-type]
