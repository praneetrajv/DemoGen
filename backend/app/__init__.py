"""DemoGen Backend Application"""

# Re-exported from the repo-root __version__.py so the version lives in exactly
# one place. This file used to carry its own "0.1.0" literal, which would
# silently drift the moment the root file was bumped.
try:
    from __version__ import __author__, __version__
except ImportError:  # pragma: no cover - repo root not on sys.path
    __version__ = "0.0.0"
    __author__ = "DemoGen Team"

__all__ = ["__version__", "__author__"]
