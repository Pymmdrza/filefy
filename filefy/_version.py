"""
Single source of truth for the Filefy package version.

Do not import anything from this module's siblings here, so that build
backends can read ``__version__`` statically without triggering package
initialisation.

The value of ``__version__`` is mirrored into ``filefy/config/details.json``
by ``scripts/bump_version.py`` and is the value exposed via:

    >>> from filefy import __version__

The PyPI release workflow validates that the git tag (``vX.Y.Z``) matches
the value defined here before publishing.
"""

__version__ = "2.0.17"