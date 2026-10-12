"""屏幕捕获：优先 DXcam（Desktop Duplication，兼容独占全屏），退化 mss（GDI）。

返回 PIL.Image；坐标一律是物理像素，由调用方（overlay）完成 logical→physical 换算。
"""

from __future__ import annotations

import io
import logging
import sys

from PIL import Image

logger = logging.getLogger("xixi_echo.capture")

IS_WINDOWS = sys.platform == "win32"

_dxcam_camera: object | None = None


def _grab_dxcam(left: int, top: int, right: int, bottom: int) -> Image.Image | None:
    global _dxcam_camera
    try:
        import dxcam
    except ImportError:
        return None
    try:
        if _dxcam_camera is None:
            _dxcam_camera = dxcam.create(output_color="RGB")
        frame = _dxcam_camera.grab(region=(left, top, right, bottom))  # type: ignore[attr-defined]
        if frame is None:
            return None
        return Image.fromarray(frame)
    except Exception:
        # DXcam 在部分驱动/多屏组合上会抛运行时异常，退回 mss
        logger.warning("DXcam 截屏失败，退回 mss", exc_info=True)
        return None


def _grab_mss(left: int, top: int, width: int, height: int) -> Image.Image:
    import mss

    with mss.mss() as sct:
        shot = sct.grab({"left": left, "top": top, "width": width, "height": height})
        return Image.frombytes("RGB", shot.size, shot.rgb)


def grab_region(left: int, top: int, width: int, height: int) -> Image.Image:
    """抓取物理像素区域。"""
    if width <= 0 or height <= 0:
        raise ValueError(f"截图区域尺寸非法: {width}x{height}")
    if IS_WINDOWS:
        frame = _grab_dxcam(left, top, left + width, top + height)
        if frame is not None:
            return frame
    return _grab_mss(left, top, width, height)


def to_png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
