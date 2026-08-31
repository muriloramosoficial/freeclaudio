"""freeclaudio: proxy local + Claude Code para providers gratuitos/locais."""
from __future__ import annotations

from .config import AppConfig, load_config
from .launcher import run

__all__ = ["AppConfig", "load_config", "run"]
__version__ = "0.1.0"
