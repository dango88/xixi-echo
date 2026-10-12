"""自动更新：GitHub Releases 检查 + 直连/国内镜像双通道下载。

版本检查按可靠性依次尝试三条通道：
1. api.github.com（最新鲜，多数网络可达）
2. github.com releases/latest 的 302（部分场景会跳列表页，故仅作参考）
3. jsDelivr 源码解析 __version__（国内快，有缓存延迟）

安装包走固定文件名约定 xixi-echo-setup.exe，gh-proxy 类文件镜像才能代理
（它们不代理 HTML/API 页面）。本仓库必须保持 public，匿名下载才可用。
"""

from __future__ import annotations

import logging
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from . import __version__

logger = logging.getLogger("xixi_echo.updater")

REPO = "dango88/xixi-echo"
ASSET_NAME = "xixi-echo-setup.exe"
DEFAULT_MIRROR = "proxy|https://gh-proxy.com"
DIRECT_BASE = "https://github.com"
_UA = {"User-Agent": "xixi-echo-updater/0.1"}

# 内置下载通道：(显示名, base, kind)——只保留实测可用的
#   proxy = URL 前缀代理（{base}/{github原始URL}）
#   direct = GitHub 直连（网络时通时断，仅作兜底）
MIRROR_PRESETS: list[tuple[str, str, str]] = [
    ("GitHub 直连", DIRECT_BASE, "direct"),
    ("gh-proxy.com 代理", "https://gh-proxy.com", "proxy"),
    ("gh-proxy.org 代理", "https://gh-proxy.org", "proxy"),
    ("ghfast.top 代理", "https://ghfast.top", "proxy"),
    ("ghproxy.net 代理（慢）", "https://ghproxy.net", "proxy"),
]
PROBE_TAG = "v0.0.1"  # 首版资产（勿删）：测速只看通道可达性与延迟，不校验状态码


def serialize_channel(kind: str, base: str) -> str:
    return f"{kind}|{base}"


def parse_channel(value: str) -> tuple[str, str]:
    """兼容旧配置：空=直连，裸 URL=proxy；新格式 = "kind|base"。"""
    value = value.strip()
    if "|" in value:
        kind, base = value.split("|", 1)
        if kind in ("direct", "proxy", "repo"):
            return kind, base
    if not value:
        return "direct", DIRECT_BASE
    return "proxy", value.rstrip("/")


def channel_label(kind: str, base: str) -> str:
    for label, b, k in MIRROR_PRESETS:
        if k == kind and b == base:
            return label
    if kind == "direct":
        return "GitHub 直连"
    return base


def asset_url_for(kind: str, base: str, tag: str, name: str) -> str:
    if kind == "repo":
        return f"{base}/releases/download/{tag}/{name}"
    if kind == "direct" or base == DIRECT_BASE:
        return f"{DIRECT_BASE}/{REPO}/releases/download/{tag}/{name}"
    return f"{base}/{DIRECT_BASE}/{REPO}/releases/download/{tag}/{name}"


class UpdaterError(Exception):
    """检查或下载失败。"""


@dataclass
class UpdateInfo:
    tag: str
    asset_url: str
    asset_name: str = ASSET_NAME


def _version_tuple(version: str) -> tuple[int, int, int]:
    numbers = re.findall(r"\d+", version)
    padded = [int(n) for n in (numbers + ["0", "0", "0"])[:3]]
    return padded[0], padded[1], padded[2]


def _tag_from_api() -> str:
    resp = httpx.get(f"https://api.github.com/repos/{REPO}/releases/latest", headers=_UA, timeout=15.0)
    resp.raise_for_status()
    data = resp.json()
    tag = data["tag_name"] if isinstance(data, dict) and isinstance(data.get("tag_name"), str) else ""
    if not tag:
        raise UpdaterError("api.github.com 响应里没有 tag_name")
    return tag


def _tag_from_redirect() -> str:
    resp = httpx.get(f"{DIRECT_BASE}/{REPO}/releases/latest", headers=_UA, timeout=15.0, follow_redirects=True)
    resp.raise_for_status()
    path = str(resp.url.path)
    if "releases/tag/" not in path:
        raise UpdaterError(f"github 302 落到了 {path}，无 tag")
    return path.rsplit("releases/tag/", 1)[-1]


def _tag_from_jsdelivr() -> str:
    resp = httpx.get(f"https://cdn.jsdelivr.net/gh/{REPO}@main/xixi_echo/__init__.py", headers=_UA, timeout=15.0)
    resp.raise_for_status()
    match = re.search(r'__version__\s*=\s*"([^"]+)"', resp.text)
    if match is None:
        raise UpdaterError("jsDelivr 源码里没找到 __version__")
    return match.group(1)


def _checkers() -> list[tuple[str, object]]:
    return [
        ("api.github.com", _tag_from_api),
        ("github-302", _tag_from_redirect),
        ("jsdelivr", _tag_from_jsdelivr),
    ]


def check() -> UpdateInfo | None:
    """有新版本返回 UpdateInfo（含镜像下载地址），已是最新返回 None。

    镜像只作用于下载阶段（见 download()）；版本检查走三条免镜像通道。
    """
    tag: str | None = None
    errors: list[str] = []
    for name, checker in _checkers():
        try:
            tag = checker()
            logger.info("更新检查成功（%s）: %s", name, tag)
            break
        except (httpx.HTTPError, UpdaterError) as exc:
            errors.append(f"{name}: {exc}")
            logger.warning("更新检查通道 %s 失败: %s", name, exc)
    if tag is None:
        raise UpdaterError("所有检查通道都失败：" + "; ".join(errors))
    if _version_tuple(tag) <= _version_tuple(__version__):
        return None
    return UpdateInfo(tag=tag, asset_url=f"{DIRECT_BASE}/{REPO}/releases/download/{tag}/{ASSET_NAME}")


def _channel_candidates(channel: str) -> list[tuple[str, str]]:
    """下载通道尝试顺序：用户选定通道优先，其余预设兜底。"""
    kind, base = parse_channel(channel)
    selected = (kind, base)
    ordered = [selected] + [(k, b) for l, b, k in MIRROR_PRESETS if (k, b) != selected]
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    for entry in ordered:
        if entry not in seen:
            seen.add(entry)
            out.append(entry)
    return out


def measure_channels(channel: str = DEFAULT_MIRROR) -> list[tuple[str, str, float | None]]:
    """逐通道测首字节延迟（Range 只拉 64KB）。

    判定标准是「通道可达 + 延迟」：任何 HTTP 响应（含 404）都算通——探针资产缺失时
    代理仍会快速应答，这同样证明通道本身在工作。
    """
    results: list[tuple[str, str, float | None]] = []
    for label, base, kind in MIRROR_PRESETS:
        url = asset_url_for(kind, base, PROBE_TAG, ASSET_NAME)
        ms: float | None = None
        start = time.monotonic()
        try:
            with httpx.stream(
                "GET", url, headers={**_UA, "Range": "bytes=0-65535"},
                timeout=8.0, follow_redirects=True,
            ) as resp:
                for chunk in resp.iter_bytes(1 << 14):
                    break  # 首块到达即计时
                ms = time.monotonic() - start
        except httpx.HTTPError:
            pass
        results.append((label, base, ms))
        _ = channel
    return results


def download(
    info: UpdateInfo,
    channel: str = DEFAULT_MIRROR,
    progress_cb: Callable[[int, int], bool] | None = None,
) -> Path:
    """流式下载安装包到临时目录：选定通道优先，失败自动遍历其余内置通道。

    progress_cb(已下载字节, 总字节|0)；回调返回 False 时中止下载。
    """
    dest = Path.home() / "AppData" / "Local" / "Temp" if _is_windows() else Path("/tmp")
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / info.asset_name
    last_error: Exception | None = None
    for kind, base in _channel_candidates(channel):
        url = asset_url_for(kind, base, info.tag, info.asset_name)
        try:
            with httpx.stream("GET", url, headers=_UA, timeout=60.0, follow_redirects=True) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("Content-Length") or 0)
                fetched = 0
                with open(target, "wb") as f:
                    for chunk in resp.iter_bytes(1 << 16):
                        f.write(chunk)
                        fetched += len(chunk)
                        if progress_cb is not None and progress_cb(fetched, total) is False:
                            target.unlink(missing_ok=True)
                            raise UpdaterError("下载已取消")
            return target
        except httpx.HTTPError as exc:
            last_error = exc
            logger.warning("安装包下载失败 %s: %s", url, exc)
    raise UpdaterError(f"安装包下载失败: {last_error}") from last_error


def run_installer(path: Path) -> None:
    """静默安装并自动重启应用（VRCX 等的做法）：Inno 负责关旧进程、装完拉起新版。

    /FORCECLOSEAPPLICATIONS 直接结束残留实例；/RESTARTAPPLICATIONS 装完自动重启。
    """
    if _is_windows():
        import subprocess

        subprocess.Popen(
            [str(path), "/SILENT", "/SUPPRESSMSGBOXES", "/FORCECLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"],
            close_fds=True,
        )  # noqa: S603,S607
    else:
        raise UpdaterError("非 Windows 平台无法启动安装包")


def _is_windows() -> bool:
    return sys.platform == "win32"
