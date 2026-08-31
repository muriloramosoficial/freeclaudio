"""Permite rodar `python -m freeclaudio` como o comando freeclaudio."""
from __future__ import annotations

import sys

from .launcher import run

if __name__ == "__main__":
    sys.exit(run())
