"""E2E de los endpoints de documentos. Corre en el host creditos.

NOT runnable in this workspace (no creditos host). Verificado además vía harness
autocontenido (/tmp/sp_verify/run_verify_endpoints.py).
"""
from __future__ import annotations

import importlib
import sys

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import clear_url_caches, include, path
from rest_framework.test import APIClient

from sinpapel.registry import WorkflowConfig, WorkflowRegistry


@pytest.fixture
def expose_config(cleanup_registry):
    from tests.models import SolicitudPrueba as Solicitud
    config = WorkflowConfig(
        model=Solicitud, state_field="estado", workflow_key="solicitud_docs_t",
        expose_endpoints=True, endpoint_slug="solicitudes-docs",
    )
    WorkflowRegistry.register("solicitud_docs_t", config)
    yield config


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser("docs_admin", "d@example.com", "x")


@pytest.fixture
def catalogo(db):
    from sinpapel.models import Documento, TipoDocumento
    td = TipoDocumento.objects.create(nombre="INE")
    doc = Documento.objects.create(nombre="INE", tipo_documento=td, valor="INE")
    return {"tipo": td, "documento": doc}


@pytest.fixture
def solicitud(db):
    from tests.models import ProductoPrueba as ProductoCreditoFOVISSSTE, SolicitudPrueba as Solicitud
    from sinpapel.models import Estado
    estado = Estado.objects.create(nombre="DOCS_ORIGEN")
    producto = ProductoCreditoFOVISSSTE.objects.create(
        nombre="P_DOCS", clave="P-DOCS", identificador="DC",
        marca="TEST", monto_minimo=0, monto_maximo=0,
        tasa_interes=0, tasa_interes_moratorio=0,
    )
    return Solicitud.objects.create(
        producto=producto, estado=estado, monto_solicitado=1000,
    )


@pytest.fixture
def api_client(expose_config, admin_user, settings):
    import sinpapel_drf.urls
    importlib.reload(sinpapel_drf.urls)
    mod = type("TestURLConfDocs", (), {
        "urlpatterns": [path("sinpapel/api/", include(sinpapel_drf.urls.urlpatterns))],
    })
    sys.modules["test_urlconf_docs"] = mod
    settings.ROOT_URLCONF = "test_urlconf_docs"
    clear_url_caches()
    client = APIClient()
    client.force_authenticate(user=admin_user)
    yield client
    sys.modules.pop("test_urlconf_docs", None)
    clear_url_caches()


def _archivo():
    return SimpleUploadedFile("ine.pdf", b"%PDF-fake", content_type="application/pdf")


@pytest.mark.django_db
def test_post_documento_crea_instancia(solicitud, catalogo, api_client):
    resp = api_client.post(
        f"/sinpapel/api/solicitudes-docs/{solicitud.pk}/documentos/",
        data={"archivo": _archivo(), "documento": catalogo["documento"].pk,
              "porcentaje": 100},
        format="multipart",
    )
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["porcentaje"] == 100
    assert body["tipo_documento"] == "INE"

    from sinpapel.models import InstanciaDocumento
    from django.contrib.contenttypes.models import ContentType
    ct = ContentType.objects.get_for_model(type(solicitud))
    assert InstanciaDocumento.objects.filter(
        target_content_type=ct, target_object_id=solicitud.pk
    ).count() == 1


@pytest.mark.django_db
def test_get_documentos_lista_solo_del_tramite(solicitud, catalogo, api_client):
    api_client.post(
        f"/sinpapel/api/solicitudes-docs/{solicitud.pk}/documentos/",
        data={"archivo": _archivo(), "documento": catalogo["documento"].pk},
        format="multipart",
    )
    resp = api_client.get(
        f"/sinpapel/api/solicitudes-docs/{solicitud.pk}/documentos/"
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert len(body) == 1
    assert body[0]["documento"] == catalogo["documento"].pk


@pytest.mark.django_db
def test_delete_documento_propio(solicitud, catalogo, api_client):
    post = api_client.post(
        f"/sinpapel/api/solicitudes-docs/{solicitud.pk}/documentos/",
        data={"archivo": _archivo(), "documento": catalogo["documento"].pk},
        format="multipart",
    )
    doc_id = post.json()["id"]
    resp = api_client.delete(
        f"/sinpapel/api/solicitudes-docs/{solicitud.pk}/documentos/{doc_id}/"
    )
    assert resp.status_code == 204, resp.content
    from sinpapel.models import InstanciaDocumento
    assert not InstanciaDocumento.objects.filter(pk=doc_id).exists()


@pytest.mark.django_db
def test_delete_documento_de_otro_tramite_da_404(solicitud, catalogo, api_client):
    from tests.models import SolicitudPrueba as Solicitud
    from sinpapel.models import InstanciaDocumento
    otro = Solicitud.objects.create(
        producto=solicitud.producto, estado=solicitud.estado, monto_solicitado=2000,
    )
    inst = InstanciaDocumento.objects.create(
        documento=catalogo["documento"], target=otro, porcentaje=100,
    )
    resp = api_client.delete(
        f"/sinpapel/api/solicitudes-docs/{solicitud.pk}/documentos/{inst.pk}/"
    )
    assert resp.status_code == 404


@pytest.mark.django_db
def test_requisitos_refleja_satisfecho(solicitud, catalogo, api_client):
    from sinpapel.models import RequisitoEstadoDocumento
    RequisitoEstadoDocumento.objects.create(
        estado=solicitud.estado, tipo_documento=catalogo["tipo"],
        porcentaje=100, auto_carga=False,
    )
    resp = api_client.get(
        f"/sinpapel/api/solicitudes-docs/{solicitud.pk}/requisitos/"
    )
    assert resp.status_code == 200, resp.content
    ine = next(r for r in resp.json() if r.get("tipo_documento") == "INE")
    assert ine["satisfecho"] is False
    assert ine["porcentaje_requerido"] == 100

    api_client.post(
        f"/sinpapel/api/solicitudes-docs/{solicitud.pk}/documentos/",
        data={"archivo": _archivo(), "documento": catalogo["documento"].pk,
              "porcentaje": 100},
        format="multipart",
    )
    resp2 = api_client.get(
        f"/sinpapel/api/solicitudes-docs/{solicitud.pk}/requisitos/"
    )
    ine2 = next(r for r in resp2.json() if r.get("tipo_documento") == "INE")
    assert ine2["satisfecho"] is True
    assert ine2["porcentaje_actual"] == 100
