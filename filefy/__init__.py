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

from ._version import __version__

# Pull the bundled configuration package. This works both for an editable
# install from a source checkout and for a wheel installed via pip.
try:
    from .config import get_details

    _details = get_details()
    __author__ = _details.programmer or "Mmdrza"
    __email__ = _details.email or "pymmdrza@gmail.com"
except Exception:  # pragma: no cover - defensive fallback
    __author__ = "Mmdrza"
    __email__ = "pymmdrza@gmail.com"

__license__ = "MIT"

from .server import app, create_app  # noqa: E402

__all__ = ["app", "create_app", "__version__", "__author__", "__email__", "__license__"]
