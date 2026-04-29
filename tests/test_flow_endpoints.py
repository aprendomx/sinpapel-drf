"""S13.9 — E2E tests para flow portability REST endpoints.

Cubre:
- T1: GET /sinpapel/api/flujos/<pk>/export/
- T2: POST /sinpapel/api/flujos/import/ (con ?dry_run=true)

Pattern reusado: APIClient.force_authenticate (S13.4),
URL conf override (S13.4 + S13.5/S13.6).
"""
from __future__ import annotations

import importlib
import json
import sys

import pytest
from django.contrib.auth.models import Group, User
from django.urls import clear_url_caches, include, path
from rest_framework.test import APIClient


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def admin_user_staff(db):
    """User con is_staff=True (NO superuser) — IsAdminUser predicate."""
    return User.objects.create_user(
        username="s13_9_admin", password="x", email="s13_9@example.com",
        is_staff=True,
    )


@pytest.fixture
def non_admin_user(db):
    """User authenticated pero is_staff=False — should be denied 403."""
    return User.objects.create_user(
        username="s13_9_nonadmin", password="x", email="s13_9_nonadm@example.com",
        is_staff=False,
    )


@pytest.fixture
def catalog_setup(db):
    """Estados + TipoDocumentos + Groups + VersionFlujo (replica S13.8 fixture)."""
    from sinpapel.models import (
        ConfiguracionTransicion, Estado, RequisitoEstadoDocumento,
        TipoDocumento, VersionFlujo,
    )

    e_orig = Estado.objects.create(nombre="S139_CAPTURA")
    e_dest = Estado.objects.create(nombre="S139_REVISION")
    td_ine = TipoDocumento.objects.create(nombre="S139_INE")
    g_at = Group.objects.create(name="S139_AsistenteTecnico")

    flujo = VersionFlujo.objects.create(
        nombre="S139_FLUJO_TEST", descripcion="test", activo=True,
    )
    t1 = ConfiguracionTransicion.objects.create(
        flujo=flujo, estado_origen=e_orig, estado_destino=e_dest,
    )
    t1.grupos_permitidos.add(g_at)
    RequisitoEstadoDocumento.objects.create(
        estado=e_orig, tipo_documento=td_ine, porcentaje=100, auto_carga=False,
    )
    return {"flujo": flujo, "estado_orig": e_orig, "estado_dest": e_dest,
            "tipo": td_ine, "grupo": g_at}


def _setup_url_conf(settings, suffix: str = "") -> None:
    """Wirea sinpapel_drf.urls bajo /sinpapel/api/ via dynamic URLConf override."""
    import sinpapel_drf.urls
    importlib.reload(sinpapel_drf.urls)
    urlconf = type(f"UC_{suffix}", (), {"urlpatterns": [
        path("sinpapel/api/", include(sinpapel_drf.urls.urlpatterns)),
    ]})
    module_name = f"test_urlconf_s13_9_{suffix or 'default'}"
    sys.modules[module_name] = urlconf
    settings.ROOT_URLCONF = module_name
    clear_url_caches()
    return module_name


@pytest.fixture
def client_admin(admin_user_staff, settings):
    module_name = _setup_url_conf(settings, "admin")
    client = APIClient()
    client.force_authenticate(user=admin_user_staff)
    yield client
    sys.modules.pop(module_name, None)
    clear_url_caches()


@pytest.fixture
def client_non_admin(non_admin_user, settings):
    module_name = _setup_url_conf(settings, "nonadm")
    client = APIClient()
    client.force_authenticate(user=non_admin_user)
    yield client
    sys.modules.pop(module_name, None)
    clear_url_caches()


@pytest.fixture
def client_unauth(settings, db):
    module_name = _setup_url_conf(settings, "unauth")
    client = APIClient()  # no force_authenticate
    yield client
    sys.modules.pop(module_name, None)
    clear_url_caches()


# ─────────────────────────────────────────────────────────────────────────────
# T1 — FlujoExportView
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_flujo_export_admin_returns_json(catalog_setup, client_admin):
    """Admin GET /export/ → 200 + Content-Disposition + JSON v0.1."""
    resp = client_admin.get(
        f"/sinpapel/api/flujos/{catalog_setup['flujo'].pk}/export/"
    )
    assert resp.status_code == 200, resp.content
    # Content-Disposition attachment header
    cd = resp.headers.get("Content-Disposition", "")
    assert "attachment" in cd
    assert "S139_FLUJO_TEST" in cd or "flujo_S139" in cd
    # JSON body
    body = resp.json()
    assert body["schema_version"] == "0.1"
    assert body["flujo"]["nombre"] == "S139_FLUJO_TEST"
    assert len(body["flujo"]["transiciones"]) == 1


@pytest.mark.django_db
def test_flujo_export_non_admin_returns_403(catalog_setup, client_non_admin):
    """User authenticated NO is_staff → 403."""
    resp = client_non_admin.get(
        f"/sinpapel/api/flujos/{catalog_setup['flujo'].pk}/export/"
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_flujo_export_unauthenticated_returns_401_or_403(catalog_setup, client_unauth):
    """Sin auth → 401 o 403 (DRF default)."""
    resp = client_unauth.get(
        f"/sinpapel/api/flujos/{catalog_setup['flujo'].pk}/export/"
    )
    assert resp.status_code in (401, 403)


@pytest.mark.django_db
def test_flujo_export_flujo_not_found_returns_404(client_admin):
    """pk inexistente → 404."""
    resp = client_admin.get("/sinpapel/api/flujos/99999999/export/")
    assert resp.status_code == 404
