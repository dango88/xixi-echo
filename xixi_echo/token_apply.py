"""评分资格申请弹窗：填 QQ → 提交 → 轮询审核状态 → 拿到 token 自动保存。"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from .api import ApiError, GatewayClient
from .threads import AsyncCall
from .widgets import XButton

logger = logging.getLogger("xixi_echo.token_apply")

STATUS_TEXT = {"pending": "已提交，等待审核…", "active": "已通过！", "rejected": "被拒绝", "revoked": "已被停用"}


class TokenApplyDialog(QDialog):
    token_saved = Signal(str, str)  # token, qq

    def __init__(self, client_provider, settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("申请评分资格 · 西西的声骸评分工具")
        self.setModal(True)
        self.setFixedWidth(400)
        self._client_provider = client_provider
        self._settings_ref = settings
        self._apply_task: AsyncCall | None = None
        self._poll_task: AsyncCall | None = None
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(10_000)
        self._poll_timer.timeout.connect(self._poll_status)
        self._qq = ""
        self._ticket = ""

        self._qq_input = QLineEdit()
        self._qq_input.setPlaceholderText("你的 QQ 号（审核标识）")
        self._note_input = QLineEdit()
        self._note_input.setPlaceholderText("备注给主人看（可选，如：xx群群友）")
        self._status = QLabel("通过审核后即可使用，通常几分钟内处理。\n申请 / 审核问题请加 QQ 群：1085339175")
        self._status.setObjectName("hint")
        self._status.setWordWrap(True)

        self._submit_btn = XButton("提交申请", tone="primary")
        self._submit_btn.clicked.connect(self._submit)
        self._cancel_btn = XButton("先不了", tone="ghost")
        self._cancel_btn.clicked.connect(self.reject)

        form = QFormLayout()
        form.addRow("QQ 号", self._qq_input)
        form.addRow("备注", self._note_input)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self._cancel_btn)
        row.addWidget(self._submit_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 14)
        layout.addLayout(form)
        layout.addWidget(self._status)
        layout.addLayout(row)

    # --- 提交 ---

    def _submit(self) -> None:
        qq = self._qq_input.text().strip()
        if not qq.isdigit() or not 5 <= len(qq) <= 12:
            self._set_status("QQ 号必须是 5-12 位数字", bad=True)
            return
        client = self._client_provider()
        self._submit_btn.setDisabled(True)
        self._set_status("提交中…")
        self._apply_task = AsyncCall(
            lambda: client.apply_token(qq, self._note_input.text().strip()),
            lambda r: self._on_applied(r),  # type: ignore[arg-type]
            self._submit_fail,
            self,
        )
        self._apply_task.start()

    def _on_applied(self, data: dict) -> None:
        status = data.get("status")
        self._qq = str(data.get("qq", self._qq_input.text().strip()))
        self._ticket = str(data.get("ticket", ""))
        if status == "active" and isinstance(data.get("token"), str):
            self._finish(data["token"])
            return
        self._set_status(STATUS_TEXT.get(status, f"状态：{status}"))
        if status == "rejected":
            reason = data.get("reject_reason", "")
            self._set_status(f"被拒绝：{reason or '未说明原因'}，可修改后重新提交", bad=True)
            self._submit_btn.setDisabled(False)
            return
        self._submit_btn.setDisabled(True)
        self._poll_timer.start()
        self._poll_status()

    # --- 轮询 ---

    def _poll_status(self) -> None:
        if not self._qq or not self._ticket:
            return
        client = self._client_provider()
        self._poll_task = AsyncCall(
            lambda: client.token_status(self._qq, self._ticket),
            lambda r: self._on_polled(r),  # type: ignore[arg-type]
            lambda m: self._set_status(f"查询失败：{m}"),
            self,
        )
        self._poll_task.start()

    def _on_polled(self, data: dict) -> None:
        status = data.get("status")
        if status == "active" and isinstance(data.get("token"), str):
            self._poll_timer.stop()
            self._finish(data["token"])
        elif status == "rejected":
            self._poll_timer.stop()
            self._set_status(f"被拒绝：{data.get('reject_reason', '')}，可重新提交", bad=True)
            self._submit_btn.setDisabled(False)

    def _finish(self, token: str) -> None:
        self._set_status("已通过！token 已保存，开始使用吧~")
        self._settings_ref.token = token
        self._settings_ref.qq = self._qq
        from .config import save_settings

        save_settings(self._settings_ref)
        self.token_saved.emit(token, self._qq)
        QTimer.singleShot(900, self.accept)

    def _submit_fail(self, message: str) -> None:
        self._submit_btn.setDisabled(False)
        self._set_status(f"提交失败：{message}", bad=True)

    def _set_status(self, text: str, bad: bool = False) -> None:
        self._status.setText(text)
        self._status.setStyleSheet(f"color: {'#DC2626' if bad else '#8A705F'};")
