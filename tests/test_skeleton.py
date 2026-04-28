"""Tests skeleton S13.3 — verify package surface."""
from __future__ import annotations


def test_package_importable():
    """sinpapel_drf is importable as a Python module."""
    import sinpapel_drf
    assert sinpapel_drf is not None


def test_version_accessible():
    """__version__ matches pyproject.toml v0.1.0."""
    from sinpapel_drf import __version__
    assert __version__ == "0.1.0"
