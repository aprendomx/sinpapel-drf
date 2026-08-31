"""Tests skeleton S13.3 — verify package surface."""
from __future__ import annotations


def test_package_importable():
    """sinpapel_drf is importable as a Python module."""
    import sinpapel_drf
    assert sinpapel_drf is not None


def test_version_accessible():
    """`__version__` and the installed distribution metadata agree.

    Compared against the distribution metadata rather than a fixed string: the
    real error is bumping one place and forgetting the other, and this way the
    test catches it without needing an edit on every release.
    """
    from importlib.metadata import version

    from sinpapel_drf import __version__
    assert __version__ == version("sinpapel-drf")
