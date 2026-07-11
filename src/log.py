"""Logging setup: rotating file in logs/ plus console output.

Entrypoints (main.py, serve.py) call setup() once; every module then logs via
its own `logging.getLogger(__name__)`.
"""

import logging
from logging.handlers import RotatingFileHandler

from config import LOG_DIR


def setup():
    root = logging.getLogger()
    if root.handlers:  # already configured
        return
    LOG_DIR.mkdir(exist_ok=True)
    root.setLevel(logging.INFO)
    fmt = logging.Formatter('%(asctime)s %(levelname)-7s %(name)s: %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S')
    file_handler = RotatingFileHandler(LOG_DIR / 'mangasearch.log',
                                       maxBytes=5 * 1024 * 1024, backupCount=3)
    file_handler.setFormatter(fmt)
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(file_handler)
    root.addHandler(console)
