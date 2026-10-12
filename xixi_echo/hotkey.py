"""全局热键：RegisterHotKey，支持组合键（Ctrl/Alt/Shift/Win + F1-F24/字母/数字）。

绑定格式为文本（如 "F9"、"Ctrl+Alt+S"），由 parse_binding 解析为 (修饰键, 虚拟键)。
"""

from __future__ import annotations

import logging
import sys
import threading
from typing import Mapping

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger("xixi_echo.hotkey")

IS_WINDOWS = sys.platform == "win32"

ACTION_SWITCH_CHAR = "switch_char"
ACTION_SINGLE = "single"
ACTION_MULTI = "multi"

_MOD_NOREPEAT = 0x4000
_WM_HOTKEY = 0x0312
_WM_QUIT = 0x0012
_HOTKEY_IDS = {ACTION_SWITCH_CHAR: 1, ACTION_SINGLE: 2, ACTION_MULTI: 3}

_MOD_MAP = {"ctrl": 0x0002, "alt": 0x0001, "shift": 0x0004, "win": 0x0008}


def _vk_of(name: str) -> int | None:
    n = name.upper()
    if len(n) >= 2 and n.startswith("F") and n[1:].isdigit():
        index = int(n[1:])
        if 1 <= index <= 24:
            return 0x70 + index - 1
        return None
    if len(n) == 1:
        if "A" <= n <= "Z":
            return 0x41 + ord(n) - ord("A")
        if "0" <= n <= "9":
            return 0x30 + int(n)
    return None


def parse_binding(text: str) -> tuple[int, int] | None:
    """解析 "Ctrl+Alt+S" / "F9" 为 (win32 修饰键掩码, 虚拟键码)；非法返回 None。"""
    parts = [p.strip() for p in text.split("+") if p.strip()]
    if not parts:
        return None
    mods = 0
    for name in parts[:-1]:
        mod = _MOD_MAP.get(name.lower())
        if mod is None:
            return None
        mods |= mod
    vk = _vk_of(parts[-1])
    if vk is None:
        return None
    return mods, vk


class HotkeyManager(QObject):
    fired = Signal(str)
    registered = Signal(list)  # list[str]：注册失败的动作名

    def __init__(self) -> None:
        super().__init__()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._thread_id: int | None = None

    def start(self, bindings: Mapping[str, str]) -> list[str]:
        """bindings: 动作名 → 绑定文本（如 "Ctrl+Alt+S"）。返回注册失败的动作。"""
        if not IS_WINDOWS:
            logger.warning("非 Windows 平台，全局热键不可用")
            return list(bindings)
        by_id: dict[int, tuple[str, int, int]] = {}
        failed: list[str] = []
        for action, text in bindings.items():
            parsed = parse_binding(text)
            if parsed is None:
                failed.append(action)
                logger.warning("热键绑定无法解析: %s = %r", action, text)
                continue
            mods, vk = parsed
            by_id[_HOTKEY_IDS[action]] = (action, mods, vk)
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, args=(by_id,), daemon=True)
        self._thread.start()
        return failed

    def stop(self) -> None:
        if self._thread is None or not IS_WINDOWS:
            return
        self._stop.set()
        import ctypes

        if self._thread_id is not None:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, _WM_QUIT, 0, 0)
        self._thread.join(timeout=2.0)
        self._thread = None

    def _run(self, by_id: dict[int, tuple[str, int, int]]) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()

        active: dict[int, str] = {}
        failed: list[str] = []
        for hotkey_id, (action, mods, vk) in by_id.items():
            if user32.RegisterHotKey(None, hotkey_id, mods | _MOD_NOREPEAT, vk):
                active[hotkey_id] = action
                logger.info("热键已注册: %s (mods=0x%x vk=0x%x)", action, mods, vk)
            else:
                failed.append(action)
                logger.warning("热键注册失败（可能被占用）: %s", action)
        self.registered.emit(failed)

        msg = wintypes.MSG()
        while not self._stop.is_set():
            # GetMessage 返回 0 = WM_QUIT，-1 = 错误
            result = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if result <= 0:
                break
            if msg.message == _WM_HOTKEY and msg.wParam in active:
                logger.info("热键触发: %s", active[msg.wParam])
                self.fired.emit(active[msg.wParam])

        for hotkey_id in active:
            user32.UnregisterHotKey(None, hotkey_id)
