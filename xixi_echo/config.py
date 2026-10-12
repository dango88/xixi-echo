"""配置持久化：Windows 存 %APPDATA%/xixi-echo/config.json。"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("xixi_echo.config")

DEFAULT_HOTKEYS: dict[str, str] = {"switch_char": "F9", "single": "F10", "multi": "F11"}
_VALID_KEYS = {"F8", "F9", "F10", "F11", "F12"}

# CI 打包时生成 xixi_echo/build_config.py，把连接参数内置进客户端（见 .github/workflows/build.yml）
try:
    from .build_config import DEFAULT_SERVER, DEFAULT_KEY_ID, DEFAULT_SECRET  # type: ignore[import-not-found]
except ImportError:
    DEFAULT_SERVER = ""  # 源码运行没有该文件，属正常
    DEFAULT_KEY_ID = ""
    DEFAULT_SECRET = ""


@dataclass
class Settings:
    server_url: str = ""
    token: str = ""  # 分发 token（申请审核后获得，持久化）
    qq: str = ""     # 申请时绑定的 QQ 号
    key_id: str = ""  # 旧静态 key（兼容保留）
    secret: str = ""
    gh_mirror: str = "proxy|https://gh-proxy.com"
    introduced: bool = False  # 首次安装后是否已展示过主页
    hotkeys: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_HOTKEYS))

    @property
    def is_configured(self) -> bool:
        return bool(self.server_url) and bool(self.token or (self.key_id and self.secret))


def settings_path() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / ".config"
    return base / "xixi-echo" / "config.json"


def _parse_hotkeys(raw: object) -> dict[str, str]:
    hotkeys = dict(DEFAULT_HOTKEYS)
    if not isinstance(raw, dict):
        return hotkeys
    for action in DEFAULT_HOTKEYS:
        value = raw.get(action)
        if isinstance(value, str) and value in _VALID_KEYS:
            hotkeys[action] = value
    return hotkeys


def load_settings() -> Settings:
    path = settings_path()
    if not path.exists():
        return Settings(server_url=DEFAULT_SERVER, key_id=DEFAULT_KEY_ID, secret=DEFAULT_SECRET)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logger.warning("配置文件读取失败，使用空配置: %s", path, exc_info=True)
        return Settings(server_url=DEFAULT_SERVER, key_id=DEFAULT_KEY_ID, secret=DEFAULT_SECRET)
    if not isinstance(raw, dict):
        return Settings(server_url=DEFAULT_SERVER, key_id=DEFAULT_KEY_ID, secret=DEFAULT_SECRET)
    server = raw.get("server_url") if isinstance(raw.get("server_url"), str) else ""
    token = raw.get("token") if isinstance(raw.get("token"), str) else ""
    qq = raw.get("qq") if isinstance(raw.get("qq"), str) else ""
    key_id = raw.get("key_id") if isinstance(raw.get("key_id"), str) else ""
    secret = raw.get("secret") if isinstance(raw.get("secret"), str) else ""
    mirror = raw.get("gh_mirror")
    gh_mirror = mirror if isinstance(mirror, str) else "https://gh-proxy.org"
    introduced = bool(raw.get("introduced", False))
    return Settings(
        server_url=(server or DEFAULT_SERVER).rstrip("/"),
        token=token,
        qq=qq,
        key_id=key_id,
        secret=secret,
        gh_mirror=gh_mirror,
        introduced=introduced,
        hotkeys=_parse_hotkeys(raw.get("hotkeys")),
    )


def save_settings(settings: Settings) -> None:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "server_url": settings.server_url,
        "key_id": settings.key_id,
        "secret": settings.secret,
        "gh_mirror": settings.gh_mirror,
        "introduced": settings.introduced,
        "token": settings.token,
        "qq": settings.qq,
        "hotkeys": settings.hotkeys,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
