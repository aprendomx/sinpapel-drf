"""sinpapel-drf — pytest fixtures."""
from __future__ import annotations

import pytest

from sinpapel.registry import WorkflowRegistry


@pytest.fixture
def cleanup_registry():
    """Limpia entries del registry creadas durante el test.

    Usar en tests que registran configs vía @workflow_enabled o
    WorkflowRegistry.register() directo. Captura el set de keys
    pre-test y elimina los nuevos post-test (yield).
    """
    keys_before = set(WorkflowRegistry.list_keys())
    yield
    keys_after = set(WorkflowRegistry.list_keys())
    for key in keys_after - keys_before:
        WorkflowRegistry.unregister(key)
