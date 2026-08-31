"""Entrypoint do subprocesso que roda apenas o servidor proxy."""
from __future__ import annotations

import argparse
import os
import sys

from .config import load_config
from .proxy import serve


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=None)
    args = parser.parse_args()

    config_path = args.config or os.environ.get("FREECLAUDIO_CFG")
    config = load_config(config_path)
    serve(config)


if __name__ == "__main__":
    main()
