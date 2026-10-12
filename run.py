"""PyInstaller 打包入口：用绝对导入，避免 __main__ 相对导入失败。"""

import logging
import os
import sys

from xixi_echo.config import settings_path

from xixi_echo.app import run_app

if __name__ == "__main__":
    # 无控制台打包：日志落文件，热键/上传问题看这里
    os.makedirs(settings_path().parent, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(settings_path().parent / "app.log", encoding="utf-8")],
    )
    sys.exit(run_app())
