"""S13.4 — Functional tests de WorkflowViewSet stub vía APIClient.

Usa creditos.Solicitud como modelo real (decorado en E12 con workflow_key='solicitud')
+ fixture que registra config adicional con expose_endpoints=True bajo otra
workflow_key. Esto evita modificar la decoración de producción + permite
ejercitar el router con un modelo Django con manager + DB real.

Pattern reusado: Client.force_login (S12.7b smoke admin sin browser).
"""
from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.urls import include, path
from rest_framework.test import APIClient

from sinpapel.registry import WorkflowConfig, WorkflowRegistry
from sinpapel_drf.routers import SinpapelRouter


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def expose_solicitud_config(cleanup_registry):
    """Registra config extra apuntando a creditos.Solicitud con expose=True.

    workflow_key='solicitud_test_exposed' (distinto al production 'solicitud')
    para evitar colisión. Slug='solicitudes-test'.
    """
    from creditos.models import Solicitud

    config = WorkflowConfig(
        model=Solicitud,
        state_field="estado",
        workflow_key="solicitud_test_exposed",
        expose_endpoints=True,
        endpoint_slug="solicitudes-test",
    )
    WorkflowRegistry.register("solicitud_test_exposed", config)
    yield config
    # cleanup_registry handles unregister


@pytest.fixture
def admin_user(db):
    """Superuser para force_login bypass de permission_classes=[IsAuthenticated]."""
    return User.objects.create_superuser(
        username="s13_4_admin", password="x", email="s13_4@example.com"
    )


@pytest.fixture
def solicitud_instance(db):
    """Instancia mínima de Solicitud para get_object() en endpoints."""
    from creditos.models import Solicitud
    return Solicitud.objects.create()


# ─────────────────────────────────────────────────────────────────────────────
# Tests — usa router directo + APIClient con URLs construidas manualmente
# ─────────────────────────────────────────────────────────────────────────────


def _build_url(slug: str, pk: int, action: str) -> str:
    """Construye URL manualmente sin depender de Django reverse() (que requiere
    sinpapel_drf.urls incluido en mossc/urls.py — diferido a S13.5)."""
    return f"/sinpapel/api/{slug}/{pk}/{action}/"


@pytest.fixture
def client_with_router(expose_solicitud_config, admin_user, settings):
    """Client con URL conf override que incluye sinpapel_drf.urls.

    Uses settings.ROOT_URLCONF override para wirear el router en runtime
    sin tocar mossc/urls.py (eso es S13.5).
    """
    # Construir URLPatterns dinámicos: include sinpapel_drf.urls bajo /sinpapel/api/
    from django.urls import include, path
    import importlib

    # Re-importar sinpapel_drf.urls para que recoja la config recién registrada
    import sinpapel_drf.urls
    importlib.reload(sinpapel_drf.urls)

    urlconf_module = type(
        "TestURLConf",
        (),
        {
            "urlpatterns": [
                path("sinpapel/api/", include(sinpapel_drf.urls.urlpatterns)),
            ]
        },
    )

    # Inyectar como ROOT_URLCONF dinámico
    import sys
    sys.modules["test_urlconf_s13_4"] = urlconf_module
    settings.ROOT_URLCONF = "test_urlconf_s13_4"

    # Forzar URL resolver refresh
    from django.urls import clear_url_caches
    clear_url_caches()

    client = APIClient()
    client.force_authenticate(user=admin_user)
    yield client

    # Cleanup
    sys.modules.pop("test_urlconf_s13_4", None)
    clear_url_caches()


def test_available_transitions_returns_200(
    expose_solicitud_config, admin_user, solicitud_instance, client_with_router
):
    """S13.4 AC6: GET /sinpapel/api/<slug>/<pk>/available-transitions/ retorna 200."""
    url = _build_url("solicitudes-test", solicitud_instance.pk, "available-transitions")
    resp = client_with_router.get(url)
    assert resp.status_code == 200, f"Expected 200 got {resp.status_code}: {resp.content!r}"
    assert isinstance(resp.json(), list)


def test_transition_stub_returns_200(
    expose_solicitud_config, admin_user, solicitud_instance, client_with_router
):
    """S13.4 AC6: POST .../transition/ retorna 200 con stub response (no 500/404)."""
    url = _build_url("solicitudes-test", solicitud_instance.pk, "transition")
    resp = client_with_router.post(url, data={}, content_type="application/json")
    assert resp.status_code == 200, f"Expected 200 got {resp.status_code}: {resp.content!r}"
    body = resp.json()
    assert body.get("status") == "stub"
    assert "S13.5" in body.get("todo", "")


def test_history_returns_200(
    expose_solicitud_config, admin_user, solicitud_instance, client_with_router
):
    """S13.4 AC6: GET .../history/ retorna 200 con lista (puede vacía)."""
    url = _build_url("solicitudes-test", solicitud_instance.pk, "history")
    resp = client_with_router.get(url)
    assert resp.status_code == 200, f"Expected 200 got {resp.status_code}: {resp.content!r}"
    assert isinstance(resp.json(), list)


def test_unauthenticated_returns_403(
    expose_solicitud_config, solicitud_instance, settings
):
    """S13.4: permission_classes=[IsAuthenticated] rechaza sin auth."""
    import importlib
    import sys
    from django.urls import clear_url_caches, include, path

    import sinpapel_drf.urls
    importlib.reload(sinpapel_drf.urls)

    urlconf_module = type(
        "TestURLConfNoAuth",
        (),
        {
            "urlpatterns": [
                path("sinpapel/api/", include(sinpapel_drf.urls.urlpatterns)),
            ]
        },
    )
    sys.modules["test_urlconf_s13_4_noauth"] = urlconf_module
    settings.ROOT_URLCONF = "test_urlconf_s13_4_noauth"
    clear_url_caches()

    try:
        client = APIClient()  # NO force_authenticate
        url = _build_url("solicitudes-test", solicitud_instance.pk, "available-transitions")
        resp = client.get(url)
        # DRF SessionAuthentication+BasicAuth retorna 401 (no credentials provided)
        # cuando IsAuthenticated permission falla sin auth ninguna.
        # Si fuera authenticated-pero-sin-permission seria 403.
        assert resp.status_code in (401, 403), f"Expected 401/403 got {resp.status_code}"
    finally:
        sys.modules.pop("test_urlconf_s13_4_noauth", None)
        clear_url_caches()
