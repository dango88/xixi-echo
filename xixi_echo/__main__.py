"""入口：python -m xixi_echo"""

from __future__ import annotations

import logging
import sys

from .app import run_app


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return run_app()


if __name__ == "__main__":
    raise SystemExit(main())
