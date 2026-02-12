"""
Filefy - A Professional Web-Based File Manager

A powerful web-based file manager written in Python with Flask.
Features include file upload/download, remote URL downloads with progress,
copy, move, delete, rename operations, and a beautiful dark theme UI.

Usage:
    $ filefy              # Start with default settings
    $ filefy --port 8080  # Start on port 8080
    $ filefy --host 127.0.0.1 --port 3000  # Custom host and port
"""

import sys
from pathlib import Path

# Add parent directory to path for config imports
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Try to get version from config
try:
    from config import get_details
    _details = get_details()
    __version__ = _details.version
    __author__ = _details.programmer
    __email__ = _details.email
except ImportError:
    __version__ = "1.0.0"
    __author__ = "Mmdrza"
    __email__ = "pymmdrza@gmail.com"

__license__ = "MIT"

from .server import app, create_app

__all__ = ["app", "create_app", "__version__"]
