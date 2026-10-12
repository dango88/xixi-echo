"""应用主控制器：托盘、热键、截图流程、提交与结果串联。"""

from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QProgressBar,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from . import hotkey as hk
from . import theme, updater
from .api import ApiError, GatewayClient
from .capture import IS_WINDOWS
from .charpicker import CharPicker
from .config import DEFAULT_KEY_ID, DEFAULT_SECRET, Settings, load_settings, save_settings
from .overlay import RegionOverlay, screen_under_cursor
from .pending import PendingWindow
from .result import ResultWindow
from .token_apply import TokenApplyDialog
from .threads import AsyncCall
from .widgets import KeyCaptureButton
from .widgets import XButton, show_toast

logger = logging.getLogger("xixi_echo.app")


def asset_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "assets" / name


def _rounded_pixmap(path: Path, size: int) -> QPixmap:
    from PIL import Image, ImageDraw
    import io

    image = Image.open(path).convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size, size), radius=size // 2, fill=255)
    image.putalpha(mask)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    pixmap = QPixmap()
    pixmap.loadFromData(buffer.getvalue())
    return pixmap


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置 · 西西的声骸评分工具")
        self.setModal(True)
        self.setFixedWidth(440)
        self._settings = settings
        # 连接参数已内置进客户端时不展示，避免暴露域名与密钥
        self._baked = bool(DEFAULT_KEY_ID and DEFAULT_SECRET)

        form = QFormLayout()

        # 快捷键自定义：点击捕捉组合键
        self._hotkey_captures: dict[str, KeyCaptureButton] = {}
        action_labels = [("switch_char", "切换角色"), ("single", "单次截图"), ("multi", "多次截图")]
        for action, label_text in action_labels:
            capture = KeyCaptureButton(self._settings.hotkeys.get(action, "F9"))
            capture.bindingCaptured.connect(lambda _t, a=action: self._on_binding_captured(a))
            self._hotkey_captures[action] = capture
            form.addRow(f"{label_text}热键", capture)

        if not self._baked:
            self._server = QLineEdit(settings.server_url)
            self._server.setPlaceholderText("https://score.example.com")
            self._key_id = QLineEdit(settings.key_id)
            self._key_id.setPlaceholderText("gui-xxxx")
            self._secret = QLineEdit(settings.secret)
            self._secret.setPlaceholderText("评分服务的 secret")
            self._secret.setEchoMode(QLineEdit.EchoMode.Password)
            form.addRow("服务端地址", self._server)
            form.addRow("Key ID", self._key_id)
            form.addRow("Secret", self._secret)

        # 下载通道 + 测延迟
        self._mirror_combo = QComboBox()
        for label, base, kind in updater.MIRROR_PRESETS:
            self._mirror_combo.addItem(label, updater.serialize_channel(kind, base))
        cur_kind, cur_base = updater.parse_channel(settings.gh_mirror)
        cur_idx = self._mirror_combo.findData(updater.serialize_channel(cur_kind, cur_base))
        self._mirror_combo.setCurrentIndex(cur_idx if cur_idx >= 0 else 1)
        self._channel_test_btn = XButton("测延迟", tone="soft")
        self._channel_test_btn.clicked.connect(self._test_channels)
        mirror_row = QHBoxLayout()
        mirror_row.addWidget(self._mirror_combo, stretch=1)
        mirror_row.addWidget(self._channel_test_btn)
        form.addRow("下载通道", mirror_row)

        save_btn = XButton("保存", tone="primary")
        save_btn.clicked.connect(self._save)
        cancel_btn = XButton("先不了", tone="ghost")
        cancel_btn.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(save_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.addLayout(form)
        layout.addLayout(buttons)

    def _on_binding_captured(self, action: str) -> None:
        text = self._hotkey_captures[action].text()
        others = [btn.text() for a, btn in self._hotkey_captures.items() if a != action]
        if text in others:
            self._hotkey_captures[action].setText(self._settings.hotkeys.get(action, "F9"))
            show_toast(f"{text} 已被其它动作占用，已还原", tone="bad")
            return
        from .hotkey import parse_binding

        if parse_binding(text) is None:
            self._hotkey_captures[action].setText(self._settings.hotkeys.get(action, "F9"))
            show_toast(f"{text} 不是可注册的热键组合", tone="bad")

    def _hotkey_conflict(self) -> str | None:
        chosen = [btn.text() for btn in self._hotkey_captures.values()]
        if len(set(chosen)) != len(chosen):
            return "、".join(sorted(set(chosen)))
        return None

    def _test_channels(self) -> None:
        self._channel_test_btn.setDisabled(True)
        self._channel_test_btn.setText("测速中…")
        self._channel_test_task = AsyncCall(
            lambda: updater.measure_channels(self._mirror_combo.currentData() or ""),
            self._on_channel_test,
            self._on_channel_test_fail,
            self,
        )
        self._channel_test_task.start()

    def _on_channel_test(self, results: object) -> None:
        self._channel_test_btn.setDisabled(False)
        self._channel_test_btn.setText("测延迟")
        assert isinstance(results, list)
        # 延迟结果直接写进下拉框选项：名称左对齐，毫秒数右对齐；<1000ms 绿、≥1000ms 红
        from PySide6.QtGui import QColor

        metrics = self._mirror_combo.fontMetrics()
        space_px = max(1, metrics.horizontalAdvance(" "))
        names = [label for label, _base, _ms in results]
        max_name_px = max(metrics.horizontalAdvance(n) for n in names)
        texts: dict[str, str] = {}
        colors: dict[str, QColor] = {}
        best: tuple[str, str] | None = None  # (base, label)
        best_ms = float("inf")
        for label, base, ms in results:
            ms_text = "不可用" if ms is None else f"{int(ms * 1000)}ms"
            pad = max(0, round((max_name_px - metrics.horizontalAdvance(label)) / space_px)) + 3
            texts[base] = f"{label}{' ' * pad}{ms_text}"
            if ms is None:
                colors[base] = QColor(theme.INK3)
            elif ms < 1.0:
                colors[base] = QColor(theme.GOOD)
            else:
                colors[base] = QColor(theme.BAD)
            if ms is not None and ms < best_ms:
                best_ms = ms
                best = (base, label)
        self._rebuild_channel_items(texts, colors)
        if best is not None:
            for label, base, kind in updater.MIRROR_PRESETS:
                if base == best[0]:
                    self._mirror_combo.setCurrentIndex(
                        self._mirror_combo.findData(updater.serialize_channel(kind, base))
                    )

    def _rebuild_channel_items(
        self, texts: dict[str, str], colors: dict[str, QColor]
    ) -> None:
        previous = self._mirror_combo.currentData()
        self._mirror_combo.clear()
        for label, base, kind in updater.MIRROR_PRESETS:
            self._mirror_combo.addItem(texts.get(base, label), updater.serialize_channel(kind, base))
            if base in colors:
                self._mirror_combo.setItemData(
                    self._mirror_combo.count() - 1, colors[base], Qt.ItemDataRole.ForegroundRole
                )
        idx = self._mirror_combo.findData(previous)
        self._mirror_combo.setCurrentIndex(idx if idx >= 0 else 0)

    def _on_channel_test_fail(self, message: str) -> None:
        self._channel_test_btn.setDisabled(False)
        self._channel_test_btn.setText("测延迟")
        show_toast(f"测速失败：{message}", tone="bad")

    def _save(self) -> None:
        chosen = {action: btn.text() for action, btn in self._hotkey_captures.items()}
        if len(set(chosen.values())) != len(chosen):
            show_toast(f"快捷键重复：{'、'.join(sorted(set(chosen.values())))}，请改成分开的不同按键", tone="bad")
            return
        if not self._baked:
            self._settings.server_url = self._server.text().strip().rstrip("/")
            self._settings.key_id = self._key_id.text().strip()
            self._settings.secret = self._secret.text().strip()
        self._settings.hotkeys = chosen
        self._settings.gh_mirror = self._mirror_combo.currentData() or ""
        save_settings(self._settings)
        self.accept()


class UpdateDownloadDialog(QDialog):
    """更新下载进度框：进度条 + 已下载量，可取消。"""

    succeeded = Signal(object)  # Path
    failed = Signal(str)
    _progress = Signal(int, int)

    def __init__(self, info: updater.UpdateInfo, mirror: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("下载更新")
        self.setModal(True)
        self.setFixedWidth(420)
        self._cancel = threading.Event()

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._label = QLabel("准备下载…")
        self._label.setObjectName("hint")
        cancel_btn = XButton("取消", tone="ghost")
        cancel_btn.clicked.connect(self._on_cancel)

        row = QHBoxLayout()
        row.addWidget(self._label, stretch=1)
        row.addWidget(cancel_btn)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 14)
        layout.addWidget(self._bar)
        layout.addLayout(row)

        self._progress.connect(self._on_progress)
        self._task = AsyncCall(
            lambda: updater.download(info, mirror, self._progress_cb),
            self._emit_ok,
            self._emit_fail,
            self,
        )
        self._task.start()

    def _progress_cb(self, fetched: int, total: int) -> bool:
        if self._cancel.is_set():
            return False
        self._progress.emit(fetched, total)
        return True

    def _on_progress(self, fetched: int, total: int) -> None:
        fetched_mb = fetched / 1048576
        if total > 0:
            percent = min(100, round(fetched * 100 / total))
            self._bar.setValue(percent)
            self._label.setText(f"已下载 {fetched_mb:.1f} / {total / 1048576:.1f} MB")
        else:
            self._bar.setRange(0, 0)  # 不确定进度
            self._label.setText(f"已下载 {fetched_mb:.1f} MB")

    def _on_cancel(self) -> None:
        self._cancel.set()
        self.reject()

    def _emit_ok(self, result: object) -> None:
        self._bar.setValue(100)
        self.succeeded.emit(result)
        self.accept()

    def _emit_fail(self, message: str) -> None:
        self.failed.emit(message)
        self.reject()


class EchoApp(QObject):
    _capture_done = Signal(bytes)  # 从 overlay 回到主线程

    def __init__(self, qtapp: QApplication) -> None:
        super().__init__()
        self._qtapp = qtapp
        self._settings: Settings = load_settings()
        self._client = GatewayClient(self._settings)
        self._overlay: RegionOverlay | None = None
        self._capture_mode: str | None = None
        self._submit_busy = False
        self._picker: CharPicker | None = None
        self._picker_task: AsyncCall | None = None
        self._submit_task: AsyncCall | None = None

        self.current_char: str | None = None

        self._pending = PendingWindow()
        self._pending.submitRequested.connect(self._submit_pending)
        self._pending.addMoreRequested.connect(lambda: self._start_capture(hk.ACTION_MULTI))

        self._result_win = ResultWindow()
        self._result_win.rescoreRequested.connect(self._rescore)
        self._result_win.checkUpdateRequested.connect(lambda: self._check_update(silent=False))

        self._apply_dialog = None
        self._update_task: AsyncCall | None = None
        self._download_task: AsyncCall | None = None
        self._update_timer: QTimer | None = None

        self._tray = self._build_tray()
        self._hotkey = hk.HotkeyManager()
        self._hotkey.fired.connect(self._on_hotkey)
        self._hotkey.registered.connect(self._on_hotkey_failed)
        self._capture_done.connect(self._on_captured)

    def start(self) -> None:
        failed = self._hotkey.start(dict(self._settings.hotkeys))
        self._on_hotkey_failed(failed)
        self._tray.show()
        self._refresh_token_ui()
        if not self._settings.is_configured:
            if self._settings.server_url:
                self._open_token_apply()   # 有服务端地址，缺 token → 直接走申请流程
            else:
                show_toast("先配置服务端地址（右键托盘 → 设置）")
                self._open_settings()
        if not self._settings.introduced:
            # 首次安装：打开一次主页（评分记录），让用户知道程序在托盘里
            self._result_win.show()
            self._settings.introduced = True
            save_settings(self._settings)
        self._update_timer = QTimer(self)
        self._update_timer.setInterval(4 * 60 * 60 * 1000)
        self._update_timer.timeout.connect(lambda: self._check_update(silent=True))
        self._update_timer.start()
        self._check_update(silent=True)
        self._prefetch_chars()
        self._token_check_timer = QTimer(self)
        self._token_check_timer.setInterval(5 * 60 * 1000)
        self._token_check_timer.timeout.connect(self._verify_token)
        self._token_check_timer.start()
        self._verify_token()
        self._tray.setToolTip(f"西西的声骸评分工具 v{__version__}")

    def _refresh_token_ui(self) -> None:
        configured = self._settings.is_configured
        self._result_win.set_actions_enabled(configured)
        if self._settings.token:
            self._result_win.set_token_status(f"🟢 token 已绑定（QQ {self._settings.qq or '未知'}）")
        elif self._settings.key_id:
            self._result_win.set_token_status("🔑 内置凭据（已停用，请申请评分资格）")
        else:
            self._result_win.set_token_status("⚪ 尚未申请 token")

    def _verify_token(self) -> None:
        """向服务端核查凭据有效性；被吊销/停用（401）时清凭据并引导重新申请。

        分发 token 与内置静态 key 都核验——后者已从客户端下线，残留的旧凭据
        必须能被识别并引导到申请流程。"""
        if not self._settings.is_configured:
            return
        client = self._client

        def job():
            try:
                return {"ok": True, "data": client.token_check()}
            except ApiError as exc:
                return {"ok": False, "status": exc.status, "message": str(exc)}

        self._token_verify_task = AsyncCall(job, self._on_verify_ok, self._on_verify_fail, self)
        self._token_verify_task.start()

    def _on_verify_ok(self, result: object) -> None:
        assert isinstance(result, dict)
        if not result.get("ok"):
            status = result.get("status", 0)
            message = str(result.get("message", ""))
            if status == 401:
                self._invalidate_token(message)
            else:
                self._result_win.set_token_status(f"⚠️ 无法连接服务，稍后自动重试（{message[:40]}）")
            return
        data = result.get("data", {})
        qq = str(data.get("ident", self._settings.qq or "未知"))
        self._result_win.set_token_status(f"🟢 token 已绑定（QQ {qq}）")
        self._result_win.set_actions_enabled(True)

    def _on_verify_fail(self, message: str) -> None:
        self._result_win.set_token_status(f"⚠️ 核查失败：{message[:40]}")

    def _invalidate_token(self, message: str) -> None:
        if self._settings.token:
            self._settings.token = ""
            save_settings(self._settings)
        else:
            # 内置静态凭据已下线：清掉本地残留，避免反复 401
            self._settings.key_id = ""
            self._settings.secret = ""
            save_settings(self._settings)
        self._refresh_token_ui()
        self._result_win.set_token_status(f"🔴 {message}")
        show_toast(message, tone="bad", duration_ms=5000)
        self._open_token_apply()

    def _prefetch_chars(self) -> None:
        """启动即拉角色目录，F9 打开浮窗时零等待。"""
        self._prefetch_task = AsyncCall(
            lambda: self._client.chars(),
            self._on_prefetch_chars,
            lambda m: logger.warning("启动拉取角色目录失败: %s", m),
            self,
        )
        self._prefetch_task.start()

    def _on_prefetch_chars(self, chars: object) -> None:
        self._prefetched = chars  # type: ignore[assignment]
        if self._picker is not None:
            self._picker.set_chars(chars)

    def _open_token_apply(self) -> None:
        if self._apply_dialog is not None and self._apply_dialog.isVisible():
            self._apply_dialog.raise_()
            return
        self._apply_dialog = TokenApplyDialog(
            lambda: self._client, self._settings, self._result_win
        )
        self._apply_dialog.token_saved.connect(self._on_token_saved)
        self._apply_dialog.destroyed.connect(lambda: setattr(self, "_apply_dialog", None))
        # 非模态：启动时不阻塞主页展示，未申请期间主页按钮保持禁用
        self._apply_dialog.show()

    def _on_token_saved(self, token: object, qq: object) -> None:
        show_toast(f"评分资格已开通（QQ {qq}），开始使用吧~")
        self._tray.setToolTip(f"西西的声骸评分工具 v{__version__} | 当前角色：{self.current_char or '未选择'}")
        self._refresh_token_ui()

    def _show_no_update(self) -> None:
        dialog = QDialog(self._result_win)
        dialog.setWindowTitle("检查更新")
        dialog.setModal(True)
        dialog.setFixedWidth(360)
        note = QLabel(f"已是最新版本 v{__version__}，当前没有可用更新。")
        ok_btn = XButton("好的", tone="primary")
        ok_btn.clicked.connect(dialog.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(ok_btn)
        lay = QVBoxLayout(dialog)
        lay.setContentsMargins(20, 18, 20, 14)
        lay.addWidget(note)
        lay.addLayout(row)
        dialog.exec()

    # --- 自动更新 ---

    def _check_update(self, silent: bool) -> None:
        def job() -> updater.UpdateInfo | None:
            return updater.check()

        def on_ok(info: object) -> None:
            if info is None:
                if not silent:
                    self._show_no_update()
                return
            assert isinstance(info, updater.UpdateInfo)
            self._offer_update(info)

        def on_fail(message: str) -> None:
            logger.warning("检查更新失败: %s", message)
            if not silent:
                show_toast(f"检查更新失败：{message}", tone="bad")

        self._update_task = AsyncCall(job, on_ok, on_fail, self)
        self._update_task.start()

    def _offer_update(self, info: updater.UpdateInfo) -> None:
        dialog = QDialog()
        dialog.setWindowTitle("发现新版本")
        dialog.setModal(True)
        dialog.setFixedWidth(380)
        note = QLabel(f"新版本 {info.tag} 可用（当前 {__version__}）。\n直接下载安装包并启动安装？")
        download_btn = XButton("下载并安装", tone="primary")
        download_btn.clicked.connect(lambda: self._download_update(info, dialog, download_btn))
        later_btn = XButton("先不了", tone="ghost")
        later_btn.clicked.connect(dialog.reject)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(later_btn)
        row.addWidget(download_btn)
        lay = QVBoxLayout(dialog)
        lay.setContentsMargins(20, 18, 20, 14)
        lay.addWidget(note)
        lay.addLayout(row)
        dialog.exec()

    def _download_update(self, info: updater.UpdateInfo, dialog: QDialog, button: XButton) -> None:
        button.setDisabled(True)
        download_dialog = UpdateDownloadDialog(info, self._settings.gh_mirror, self._result_win)
        download_dialog.succeeded.connect(self._install_and_quit)
        download_dialog.failed.connect(self._on_download_failed)
        download_dialog.exec()
        if button is not None:
            button.setDisabled(False)

    def _install_and_quit(self, path: object) -> None:
        assert isinstance(path, Path)
        show_toast("安装包已下载，即将启动安装程序…")
        try:
            updater.run_installer(path)
        finally:
            self._quit()

    def _on_download_failed(self, message: str) -> None:
        show_toast(f"下载失败（直连与镜像都试过了）：{message}", tone="bad", duration_ms=5000)

    # --- 托盘 ---

    def _build_tray(self) -> QSystemTrayIcon:
        icon = QIcon(str(asset_path("xixi-avatar.png")))
        tray = QSystemTrayIcon(icon)
        tray.setToolTip(f"西西的声骸评分工具 v{__version__}")
        menu = QMenu()
        actions: list[tuple[str, Callable[[], None]]] = [
            ("切换角色 (F9)", lambda: self._on_hotkey(hk.ACTION_SWITCH_CHAR)),
            ("单次截图 (F10)", lambda: self._on_hotkey(hk.ACTION_SINGLE)),
            ("多次截图 (F11)", lambda: self._on_hotkey(hk.ACTION_MULTI)),
        ]
        for label, handler in actions:
            action = QAction(label, menu)
            action.triggered.connect(handler)
            menu.addAction(action)
        menu.addSeparator()
        recent = QAction("评分记录（主页）", menu)
        recent.triggered.connect(self._result_win.show)
        menu.addAction(recent)
        apply_action = QAction("申请评分资格", menu)
        apply_action.triggered.connect(self._open_token_apply)
        menu.addAction(apply_action)
        check_update = QAction("检查更新", menu)
        check_update.triggered.connect(lambda: self._check_update(silent=False))
        menu.addAction(check_update)
        config_action = QAction("设置", menu)
        config_action.triggered.connect(self._open_settings)
        menu.addAction(config_action)
        menu.addSeparator()
        quit_action = QAction("退出", menu)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)
        tray.setContextMenu(menu)
        tray.activated.connect(self._on_tray_activated)
        return tray

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            win = self._result_win
            win.setWindowState(win.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
            win.show()
            win.raise_()
            win.activateWindow()

    def _on_hotkey_failed(self, failed: list) -> None:
        if failed:
            show_toast(f"热键注册失败：{', '.join(str(f) for f in failed)}（可能被其它软件占用，改键位后重启）", tone="bad")

    # --- 热键动作 ---

    def _on_hotkey(self, action: str) -> None:
        logger.info("热键动作: %s (当前角色=%r)", action, self.current_char)
        if not self._settings.is_configured:
            show_toast("先完成评分资格申请（托盘 → 申请评分资格）", tone="bad")
            self._open_token_apply()
            return
        if action == hk.ACTION_SWITCH_CHAR:
            self._open_picker()
        else:
            self._start_capture(action)

    def _open_picker(self) -> None:
        if self._picker is None:
            self._picker = CharPicker(lambda: self._client)
            self._picker.chosen.connect(self._set_char)
            if getattr(self, "_prefetched", None):
                self._picker.set_chars(self._prefetched)
        self._picker.open_and_load()

    def _set_char(self, name: str) -> None:
        self.current_char = name
        self._tray.setToolTip(f"西西的声骸评分工具 | 当前角色：{name}")
        show_toast(f"当前角色：{name}")

    # --- 截图流程 ---

    def _start_capture(self, mode: str) -> None:
        if self._overlay is not None:
            return  # 已经在框选中
        if mode == hk.ACTION_SINGLE and self.current_char is None:
            show_toast("先按 F9 选一个角色，再开始单次截图")
            self._open_picker()
            return
        self._capture_mode = mode
        if self._pending.isVisible():
            self._pending.hide()  # 避免自家浮窗入镜
        overlay = RegionOverlay(screen_under_cursor())
        overlay.captured.connect(self._capture_done)
        overlay.cancelled.connect(self._capture_cancelled)
        self._overlay = overlay
        overlay.start()

    def _capture_cancelled(self) -> None:
        self._overlay = None
        self._capture_mode = None
        if self._pending.shots:
            self._pending.show()

    def _on_captured(self, png: bytes) -> None:
        mode = self._capture_mode
        self._overlay = None
        self._capture_mode = None
        if mode == hk.ACTION_SINGLE:
            self._pending.set_single(png, self.current_char or "")
        else:
            if not self._pending.isVisible() and self._pending.shots:
                pass  # 继续累加
            self._pending.set_multi(self.current_char or "")
            self._pending.add_shot(png)
        self._pending.show()
        self._pending.raise_()
        self._pending.activateWindow()

    # --- 提交 ---

    def _submit_pending(self) -> None:
        self._submit_with(self.current_char, list(self._pending.shots), on_done=self._pending.reset)

    def _rescore(self) -> None:
        current = self._result_win.current_shots()
        if current is None:
            return
        char, shots = current
        self._submit_with(char, shots, on_done=None)

    def _submit_with(self, char: str | None, shots: list[bytes], on_done: Callable[[], None] | None) -> None:
        if self._submit_busy:
            return
        if not shots:
            show_toast("还没有截图", tone="bad")
            return
        if not char:
            show_toast("先按 F9 选择角色再评分", tone="bad")
            self._open_picker()
            return
        self._submit_busy = True
        self._pending.set_submitting(True)
        client = self._client
        shot_snapshot = list(shots)
        char_snapshot = char

        def do_score() -> object:
            return client.score(char_snapshot, shot_snapshot)

        def on_ok(result: object) -> None:
            self._submit_busy = False
            self._pending.set_submitting(False)
            score = result  # ScoreResult
            self._result_win.add_result(char_snapshot, score.image, score.matched_character or char_snapshot, score.elapsed_ms)  # type: ignore[attr-defined]
            if on_done is not None:
                on_done()
            show_toast(f"{score.matched_character or char_snapshot} 评分完成 ({score.elapsed_ms}ms)")  # type: ignore[attr-defined]

        def on_fail(message: str) -> None:
            self._submit_busy = False
            self._pending.set_submitting(False)
            show_toast(message, tone="bad", duration_ms=4200)
            self._verify_token()  # 若因 token 被吊销/停用而失败，自动核查并引导重新申请

        self._submit_task = AsyncCall(do_score, on_ok, on_fail, self)
        self._submit_task.start()

    # --- 设置 / 退出 ---

    def _apply_hotkeys(self) -> None:
        self._hotkey.stop()
        failed = self._hotkey.start(dict(self._settings.hotkeys))
        self._on_hotkey_failed(failed)

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self._settings)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._client = GatewayClient(self._settings)
            self._apply_hotkeys()
            self._refresh_token_ui()
            show_toast("设置已保存")

    def _quit(self) -> None:
        self._hotkey.stop()
        self._qtapp.quit()


def _guard_single_instance() -> None:
    """命名互斥锁防多开：旧实例残留会占住全局热键，第二实例直接退出。"""
    import ctypes

    ctypes.windll.kernel32.CreateMutexW(None, False, "xixi-echo-single-instance")
    ERROR_ALREADY_EXISTS = 183
    if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        logger.warning("已有实例在运行，退出当前进程")
        ctypes.windll.user32.MessageBoxW(
            None,
            "西西的声骸评分工具已经在运行了（看屏幕右下角托盘）。\n"
            "如果托盘里找不到图标，请先在任务管理器结束旧的 xixi-echo.exe。",
            "提示",
            0x40,
        )
        sys.exit(0)


def run_app() -> int:
    if IS_WINDOWS:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("xixi.echo")
        _guard_single_instance()

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    qtapp = QApplication(sys.argv)
    qtapp.setApplicationName("西西的声骸评分工具")
    qtapp.setApplicationDisplayName("西西的声骸评分工具")
    qtapp.setWindowIcon(QIcon(str(asset_path("xixi-echo.ico"))))
    qtapp.setQuitOnLastWindowClosed(False)
    qtapp.setStyleSheet(theme.build_qss())

    controller = EchoApp(qtapp)
    controller.start()
    return qtapp.exec()
