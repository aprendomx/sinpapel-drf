"""v0.2.0 — E2E tests for WorkflowViewSet.metadatos GET + PATCH.

NOT runnable in this workspace (no creditos host). Exercised when sinpapel-drf
v0.2.0 is installed in the mossc (creditos) project.
"""
from __future__ import annotations

import importlib
import sys

import pytest
from django.contrib.auth.models import User
from django.urls import clear_url_caches, include, path
from rest_framework.test import APIClient

from sinpapel.mixins import CampoMetadato
from sinpapel.registry import WorkflowConfig, WorkflowRegistry


TEST_SCHEMA = [
    CampoMetadato(nombre="rfc", tipo=str, requerido=True, etiqueta="RFC"),
    CampoMetadato(nombre="edad", tipo=int, requerido=False, default=0),
    CampoMetadato(nombre="nivel", tipo=str, choices=["A", "B", "C"]),
]


@pytest.fixture
def patched_schema(monkeypatch):
    """Inyecta SCHEMA_METADATOS en Solicitud por el test."""
    from creditos.models import Solicitud

    monkeypatch.setattr(Solicitud, "SCHEMA_METADATOS", TEST_SCHEMA, raising=False)
    from sinpapel_drf.metadata_views import get_meta_serializer_class
    get_meta_serializer_class.cache_clear()
    yield
    get_meta_serializer_class.cache_clear()


@pytest.fixture
def expose_config(cleanup_registry):
    from creditos.models import Solicitud

    config = WorkflowConfig(
        model=Solicitud,
        state_field="estado",
        workflow_key="solicitud_meta_t",
        expose_endpoints=True,
        endpoint_slug="solicitudes-meta",
    )
    WorkflowRegistry.register("solicitud_meta_t", config)
    yield config


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(
        username="meta_admin", password="x", email="m@example.com"
    )


@pytest.fixture
def solicitud(db):
    from creditos.models import ProductoCreditoFOVISSSTE, Solicitud
    from sinpapel.models import Estado

    estado = Estado.objects.create(nombre="META_ORIGEN")
    producto = ProductoCreditoFOVISSSTE.objects.create(
        nombre="P_META", clave="P-META", identificador="MM",
        marca="TEST", monto_minimo=0, monto_maximo=0,
        tasa_interes=0, tasa_interes_moratorio=0,
    )
    return Solicitud.objects.create(
        producto=producto, estado=estado, monto_solicitado=1000,
    )


@pytest.fixture
def api_client(patched_schema, expose_config, admin_user, settings):
    import sinpapel_drf.urls
    importlib.reload(sinpapel_drf.urls)
    mod = type("TestURLConfMeta", (), {
        "urlpatterns": [path("sinpapel/api/", include(sinpapel_drf.urls.urlpatterns))],
    })
    sys.modules["test_urlconf_meta"] = mod
    settings.ROOT_URLCONF = "test_urlconf_meta"
    clear_url_caches()
    client = APIClient()
    client.force_authenticate(user=admin_user)
    yield client
    sys.modules.pop("test_urlconf_meta", None)
    clear_url_caches()


@pytest.mark.django_db
def test_metadatos_get_returns_schema_and_values(solicitud, api_client):
    resp = api_client.get(
        f"/sinpapel/api/solicitudes-meta/{solicitud.pk}/metadatos/"
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert "schema" in body and "values" in body
    nombres = [c["nombre"] for c in body["schema"]]
    assert nombres == ["rfc", "edad", "nivel"]
    rfc_field = next(c for c in body["schema"] if c["nombre"] == "rfc")
    assert rfc_field["tipo"] == "str"
    assert rfc_field["requerido"] is True


@pytest.mark.django_db
def test_metadatos_patch_partial_updates_one_field(solicitud, api_client):
    resp = api_client.patch(
        f"/sinpapel/api/solicitudes-meta/{solicitud.pk}/metadatos/",
        data={"rfc": "ABCD010101ABC"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    solicitud.refresh_from_db()
    assert solicitud.datos_capturados["rfc"] == "ABCD010101ABC"


@pytest.mark.django_db
def test_metadatos_patch_invalid_choice_rejected(solicitud, api_client):
    resp = api_client.patch(
        f"/sinpapel/api/solicitudes-meta/{solicitud.pk}/metadatos/",
        data={"nivel": "Z"},
        format="json",
    )
    assert resp.status_code == 400
    assert "nivel" in resp.json()


@pytest.mark.django_db
def test_metadatos_patch_wrong_type_rejected(solicitud, api_client):
    resp = api_client.patch(
        f"/sinpapel/api/solicitudes-meta/{solicitud.pk}/metadatos/",
        data={"edad": "not-an-int"},
        format="json",
    )
    assert resp.status_code == 400
    assert "edad" in resp.json()


@pytest.mark.django_db
def test_metadatos_patch_unknown_key_rejected(solicitud, api_client):
    resp = api_client.patch(
        f"/sinpapel/api/solicitudes-meta/{solicitud.pk}/metadatos/",
        data={"campo_inventado": "x"},
        format="json",
    )
    assert resp.status_code == 400
    assert "campo_inventado" in resp.json()


@pytest.mark.django_db
def test_metadatos_patch_isolation_between_instances(solicitud, api_client):
    from creditos.models import Solicitud

    other = Solicitud.objects.create(
        producto=solicitud.producto, estado=solicitud.estado, monto_solicitado=2000,
    )
    api_client.patch(
        f"/sinpapel/api/solicitudes-meta/{solicitud.pk}/metadatos/",
        data={"rfc": "AAAA010101AAA"}, format="json",
    )
    other.refresh_from_db()
    assert other.datos_capturados.get("rfc") in (None, "")
