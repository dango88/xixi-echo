"""F9 角色选择浮窗：搜索 + 头像网格，点击即设为当前角色。

头像加载性能（参考 Hillobar/Rope ★5.4k 的 ThumbnailLoader 模式）：
磁盘缓存先行 → 单个后台 worker 复用一条 HTTP 连接批量补齐缺失 → 主线程 O(1) 回填。
不再为每张头像创建线程，也不再每次启动重复下载。
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .api import GatewayClient
from .draggable import DragHandle
from .threads import AsyncCall
from .widgets import XButton

logger = logging.getLogger("xixi_echo.charpicker")

_COLUMNS = 5
_CARD_SIZE = QSize(96, 108)
_ICON_SIZE = 56
AVATAR_CACHE: dict[str, QPixmap] = {}  # 键为头像 URL（进程内存缓存）


def _avatar_cache_dir() -> Path:
    from .config import settings_path

    path = settings_path().parent / "avatar-cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _disk_key(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:20] + ".png"


def _disk_load(url: str) -> bytes | None:
    path = _avatar_cache_dir() / _disk_key(url)
    if not path.exists():
        return None
    try:
        return path.read_bytes()
    except OSError:
        logger.warning("头像读缓存失败 %s", path, exc_info=True)
        return None


def _disk_store(url: str, png: bytes) -> None:
    path = _avatar_cache_dir() / _disk_key(url)
    try:
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(png)
        tmp.replace(path)
    except OSError:
        logger.warning("头像写盘失败 %s", path, exc_info=True)


def _avatar_pixmap(png: bytes, size: int = _ICON_SIZE) -> QPixmap:
    """服务端已处理好圆角方形，直接缩放即可。"""
    pixmap = QPixmap()
    pixmap.loadFromData(png)
    return pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)


class CharPicker(QWidget):
    chosen = Signal(str)
    _avatar_ready = Signal(str, object)  # 工作线程 → 主线程（url, png bytes）

    def __init__(self, client_provider: Callable[[], GatewayClient], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._client_provider = client_provider
        self._chars: list[dict] = []
        self._cards: dict[str, QToolButton] = {}
        # 一个 URL 可能对应多个角色卡（如漂泊者共用头像），所以是列表
        self._cards_by_url: dict[str, list[QToolButton]] = {}
        self._avatar_worker_running = False
        self._avatar_ready.connect(self._on_avatar_ready)
        self._task: AsyncCall | None = None

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(640)
        self.setFixedHeight(560)

        card = QWidget()
        card.setObjectName("pickerCard")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card)

        # 顶部拖拽把手：抓住移动整窗，右侧置顶
        self._handle = DragHandle(self, "选择角色")

        self._search = QLineEdit()
        self._search.setPlaceholderText("搜索角色名 / 属性…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._refilter)
        self._close_btn = XButton("关闭", tone="ghost")
        self._close_btn.clicked.connect(self.close)

        header = QHBoxLayout()
        header.addWidget(self._search, stretch=1)
        header.addWidget(self._close_btn)

        self._grid_host = QWidget()
        self._grid_host.setObjectName("pickerGrid")
        self._grid = QGridLayout(self._grid_host)
        self._grid.setSpacing(8)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._grid_host)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 0, 18, 14)
        layout.addWidget(self._handle)
        layout.addLayout(header)
        layout.addWidget(scroll, stretch=1)

    # —— 数据 ——

    def set_chars(self, chars: object) -> None:
        """外部（启动预取）直接灌入目录，浮窗打开时零等待。"""
        self._chars = [c for c in chars if c.get("name")]  # type: ignore[union-attr]
        self._refilter(self._search.text())

    def open_and_load(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        if self._chars:
            # 已有数据先展示，再后台刷新（新角色/新头像由服务端自刷新保证）
            self._refilter(self._search.text())
        self._load()

    def _load(self) -> None:
        client = self._client_provider()
        self._search.setPlaceholderText("正在加载角色目录…")
        self._task = AsyncCall(client.chars, self._on_chars, self._on_error, self)
        self._task.start()

    def _on_chars(self, chars: object) -> None:
        self._chars = [c for c in chars if c.get("name")]  # type: ignore[union-attr]
        self._search.setPlaceholderText("搜索角色名 / 属性…")
        # 刷新后保留用户当前输入的过滤条件
        self._refilter(self._search.text())

    def _on_error(self, message: str) -> None:
        self._search.setPlaceholderText(f"加载失败：{message}")

    # —— 卡片网格 ——

    def _refilter(self, query: str) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._cards.clear()
        self._cards_by_url.clear()
        query = query.strip().lower()
        row = col = 0
        for info in self._chars:
            if query and query not in info["name"].lower() and query not in info["attr_zh"]:
                continue
            card = self._build_card(info)
            self._cards[info["name"]] = card
            self._grid.addWidget(card, row, col)
            col += 1
            if col == _COLUMNS:
                row, col = row + 1, 0
        self._load_missing_avatars()

    def _build_card(self, info: dict) -> QToolButton:
        name = info["name"]
        url = info["avatar_url"] or ""
        button = QToolButton()
        button.setObjectName("charCard")
        button.setFixedSize(_CARD_SIZE)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        button.setIconSize(QSize(_ICON_SIZE, _ICON_SIZE))
        star_text = "★" * min(info["star"], 5) if info["star"] else ""
        button.setText(f"{name}\n{info['attr_zh']} {star_text}".strip())
        if not info["in_tuning"]:
            button.setEnabled(False)
            button.setToolTip(f"{name}：该角色暂无评分模板")
        else:
            button.setToolTip(name)
        button.clicked.connect(lambda _=False, n=name: self._choose(n))

        if url:
            self._cards_by_url.setdefault(url, []).append(button)
            cached = AVATAR_CACHE.get(url)
            if cached is not None:
                button.setIcon(QIcon(cached))
        return button

    def _load_missing_avatars(self) -> None:
        """磁盘缓存先行；缺失的交给单个后台 worker 批量补齐（复用一条连接）。"""
        pending: list[str] = []
        seen: set[str] = set()
        for url, cards in self._cards_by_url.items():
            if url in AVATAR_CACHE or url in seen:
                continue
            seen.add(url)
            png = _disk_load(url)
            if png is not None:
                pixmap = _avatar_pixmap(png)
                AVATAR_CACHE[url] = pixmap
                for card in cards:
                    card.setIcon(QIcon(pixmap))
            else:
                pending.append(url)

        if not pending or self._avatar_worker_running:
            return
        self._avatar_worker_running = True

        def job() -> None:
            import httpx

            # 单连接顺序补齐：60 张 56px 头像 ~10KB/张，远快于 60 个线程各自建连
            with httpx.Client(timeout=15.0, headers={"User-Agent": "xixi-echo"}) as client:
                for url in pending:
                    try:
                        resp = client.get(url)
                        resp.raise_for_status()
                    except httpx.HTTPError as exc:
                        logger.warning("头像下载失败 %s: %s", url, exc)
                        continue
                    _disk_store(url, resp.content)
                    self._avatar_ready.emit(url, resp.content)

        def done(_result: object) -> None:
            self._avatar_worker_running = False

        def failed(message: str) -> None:
            logger.warning("头像批量下载失败: %s", message)
            self._avatar_worker_running = False

        self._avatar_task = AsyncCall(job, done, failed, self)
        self._avatar_task.start()

    def _on_avatar_ready(self, url: str, png: object) -> None:
        """主线程回填：O(1) 查索引，不遍历全表。"""
        assert isinstance(png, bytes)
        pixmap = _avatar_pixmap(png)
        AVATAR_CACHE[url] = pixmap
        for card in self._cards_by_url.get(url, []):
            card.setIcon(QIcon(pixmap))

    def _choose(self, name: str) -> None:
        self.close()
        self.chosen.emit(name)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close()
