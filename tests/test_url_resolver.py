"""S13.4 — URL resolver smoke test (validación arquitectónica).

Verifica que SinpapelRouter genera correctamente las 3 actions URL patterns
para cada modelo con expose_endpoints=True. Inspecciona router.urls
(URLPattern objects de DRF) sin requerir Django reverse() ni include en
mossc/urls.py (ese wireup es S13.5).

Este test EJERCE el riesgo arquitectónico (Django app loading order):
si SinpapelRouter no se popula correctamente del registry, las URLs
no se generan.
"""
from __future__ import annotations

import pytest

from sinpapel.decorators import workflow_enabled
from sinpapel.registry import WorkflowRegistry
from sinpapel_drf.routers import SinpapelRouter


class _MockMeta:
    def __init__(self, fields: list[str]) -> None:
        self._fields = fields

    def get_field(self, name: str):
        if name not in self._fields:
            from django.core.exceptions import FieldDoesNotExist
            raise FieldDoesNotExist(f"no field {name}")
        return object()


def _make_mock_model(name: str):
    return type(name, (), {"_meta": _MockMeta(["estado", "actualizado"])})


def test_router_urls_include_3_actions(cleanup_registry):
    """S13.4 AC7: router.urls expone los 3 actions per modelo expuesto.

    Inspecciona DRF URLPattern objects directamente — no depende de Django
    reverse() ni mossc/urls.py include.
    """
    M = _make_mock_model("UrlResolverTestModel")
    workflow_enabled(
        state_field="estado",
        workflow_key="url_resolver_test",
        expose_endpoints=True,
        endpoint_slug="url-test-models",
    )(M)

    router = SinpapelRouter()
    url_patterns = router.urls

    # router.urls retorna lista de URLPattern objects. Convertir patterns a strings
    # para inspección (DRF usa RoutePattern por default; .pattern atributo).
    pattern_strings = [str(p.pattern) for p in url_patterns]

    # Esperamos al menos: 3 actions × 1 modelo = 3 patterns + DRF API root + format suffix.
    # Cada action genera un URLPattern con ruta tipo
    # 'url-test-models/(?P<pk>[^/.]+)/available-transitions/'
    expected_actions = ["available-transitions", "transition", "history"]
    found_actions = []
    for pat_str in pattern_strings:
        for action in expected_actions:
            if action in pat_str:
                found_actions.append(action)

    for action in expected_actions:
        assert action in found_actions, (
            f"Action '{action}' not found in router URLs. "
            f"Patterns: {pattern_strings}"
        )


def test_router_urls_include_pk_capture(cleanup_registry):
    """S13.4 AC7: detail actions capturan <pk> en la URL pattern."""
    M = _make_mock_model("PkCaptureTestModel")
    workflow_enabled(
        state_field="estado",
        workflow_key="pk_capture_test",
        expose_endpoints=True,
        endpoint_slug="pk-test-models",
    )(M)

    router = SinpapelRouter()
    pattern_strings = [str(p.pattern) for p in router.urls]

    # Al menos un pattern debe capturar pk via regex (?P<pk>...)
    pk_patterns = [p for p in pattern_strings if "pk" in p]
    assert len(pk_patterns) > 0, (
        f"No URL pattern captures <pk>. Patterns: {pattern_strings}"
    )
