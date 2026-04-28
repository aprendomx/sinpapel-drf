"""S13.4 — Tests structural de SinpapelRouter.

Verifican que el router itera WorkflowRegistry.list_exposed() correctamente
e ignora modelos sin expose_endpoints=True. Tests inspeccionan
`router.registry` (lista interna DRF de tuplas (prefix, viewset, basename))
sin invocar Django URL resolver.
"""
from __future__ import annotations

import logging

import pytest

from sinpapel.decorators import workflow_enabled
from sinpapel.registry import WorkflowRegistry
from sinpapel_drf.routers import SinpapelRouter


class _MockMeta:
    """Mock minimal de Django _meta para validación del decorator."""

    def __init__(self, fields: list[str]) -> None:
        self._fields = fields

    def get_field(self, name: str):
        if name not in self._fields:
            from django.core.exceptions import FieldDoesNotExist
            raise FieldDoesNotExist(f"no field {name}")
        return object()


def _make_mock_model(name: str):
    """Construye una clase mock con _meta para tests del decorator."""
    return type(name, (), {"_meta": _MockMeta(["estado"])})


def test_router_registers_exposed_only(cleanup_registry):
    """S13.4 AC5: SinpapelRouter ignora modelos con expose_endpoints=False."""
    M_yes = _make_mock_model("M_router_yes")
    M_no = _make_mock_model("M_router_no")

    workflow_enabled(
        state_field="estado",
        workflow_key="router_exposed",
        expose_endpoints=True,
        endpoint_slug="exposed-things",
    )(M_yes)
    workflow_enabled(
        state_field="estado",
        workflow_key="router_hidden",
        expose_endpoints=False,
    )(M_no)

    router = SinpapelRouter()
    # router.registry es lista de tuplas (prefix, viewset, basename)
    prefixes = [r[0] for r in router.registry]

    assert "exposed-things" in prefixes, f"Expected slug not registered: {prefixes}"
    assert "router_hiddens" not in prefixes, "Hidden model should NOT register"


def test_router_uses_effective_slug(cleanup_registry):
    """S13.4 AC1+AC5: default slug = workflow_key + 's'; override funciona."""
    M_default = _make_mock_model("M_default_slug")
    M_custom = _make_mock_model("M_custom_slug")

    # Default — endpoint_slug=None → effective_slug = workflow_key + "s"
    workflow_enabled(
        state_field="estado",
        workflow_key="default_router_test",
        expose_endpoints=True,
    )(M_default)

    # Override explícito
    workflow_enabled(
        state_field="estado",
        workflow_key="custom_router_test",
        expose_endpoints=True,
        endpoint_slug="custom-slug-override",
    )(M_custom)

    router = SinpapelRouter()
    prefixes = {r[0] for r in router.registry}

    assert "default_router_tests" in prefixes  # default + "s"
    assert "custom-slug-override" in prefixes  # explícito


def test_router_empty_when_no_exposed_warns(cleanup_registry, caplog):
    """S13.4 SHOULD: warning log si registry está vacío al __init__."""
    # cleanup_registry removerá cualquier key creada en otros tests previos,
    # pero puede haber configs persistentes (creditos.Solicitud sin expose).
    # El test verifica solo que el router NO crashea con registry vacío de
    # exposed (independientemente de hidden registrations).

    with caplog.at_level(logging.WARNING, logger="sinpapel_drf.routers"):
        router = SinpapelRouter()
        # router.registry contiene solo configs con expose_endpoints=True
        exposed_count = sum(1 for c in WorkflowRegistry.list_exposed())
        assert len(router.registry) == exposed_count, (
            f"Router registered {len(router.registry)} but registry has {exposed_count} exposed"
        )

        # Si exposed_count == 0, debe haber warning log
        if exposed_count == 0:
            assert any(
                "expose_endpoints=True" in record.message
                for record in caplog.records
            ), f"Expected warning log when registry is empty: {[r.message for r in caplog.records]}"
