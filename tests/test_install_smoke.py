"""S13.7 — Integration smoke E2E test (skip-by-default).

Validates that sinpapel + sinpapel-drf install correctly via uv en venv tmp,
y que los main entry points son importables. NOT run en default CI suite —
manual run only via:

    pytest -m install_smoke -v sinpapel_drf/tests/test_install_smoke.py

Skip cleanly cuando uv no está en PATH (developers locales sin uv aún funcional).
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.mark.install_smoke
def test_install_smoke_creates_venv_and_imports(tmp_path):
    """Manual smoke: uv venv tmp + uv pip install both packages + import verify.

    El test instala los dos paquetes desde paths locales (REPO_ROOT/sinpapel
    y REPO_ROOT/sinpapel_drf) en un venv temporal aislado. Verifica que los
    main entry points importan correctamente y que SCHEMA_VERSION = "0.1".
    """
    if not shutil.which("uv"):
        pytest.skip("uv not in PATH; install smoke requires `uv` (skip cleanly)")

    venv_dir = tmp_path / ".venv"
    subprocess.run(
        ["uv", "venv", str(venv_dir)],
        check=True, capture_output=True, text=True,
    )
    python_bin = venv_dir / "bin" / "python"
    assert python_bin.exists(), f"venv python not found at {python_bin}"

    sinpapel_path = REPO_ROOT / "sinpapel"
    sinpapel_drf_path = REPO_ROOT / "sinpapel_drf"
    assert sinpapel_path.exists(), f"sinpapel package not found at {sinpapel_path}"
    assert sinpapel_drf_path.exists(), f"sinpapel_drf package not found at {sinpapel_drf_path}"

    # Install both packages from local paths into venv
    subprocess.run(
        [
            "uv", "pip", "install",
            "--python", str(python_bin),
            str(sinpapel_path),
            str(sinpapel_drf_path),
        ],
        check=True, capture_output=True, text=True,
    )

    # Verify imports succeed + schema version contract.
    # Pure imports — no Django setup required (avoid DJANGO_SETTINGS_MODULE
    # dependency en isolated venv smoke).
    result = subprocess.run(
        [
            str(python_bin), "-c",
            "import sinpapel; "
            "import sinpapel_drf; "
            "from sinpapel.schemas.flujo_export import SCHEMA_VERSION; "
            "assert SCHEMA_VERSION == '0.1', f'Expected 0.1 got {SCHEMA_VERSION}'; "
            "print('OK')",
        ],
        check=True, capture_output=True, text=True,
    )
    assert "OK" in result.stdout, (
        f"Import verify did not print OK: stdout={result.stdout!r}, "
        f"stderr={result.stderr!r}"
    )
