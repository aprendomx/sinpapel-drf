"""v0.2.0 — E2E tests para WorkflowViewSet.preview_transition action.

Reusa el patrón de fixtures de test_viewset_full.py (Solicitud + Estado +
flujo) con expose_endpoints=True + APIClient override URLConf.

Estos tests NO corren en este workspace (no hay venv con sinpapel/creditos).
Se ejercitan al instalar sinpapel-drf v0.2.0 en el host creditos.
"""
from __future__ import annotations

import importlib
import sys

import pytest
from django.contrib.auth.models import User
from django.urls import clear_url_caches, include, path
from rest_framework.test import APIClient

from sinpapel.registry import WorkflowConfig, WorkflowRegistry


@pytest.fixture
def expose_config(cleanup_registry):
    from tests.models import SolicitudPrueba as Solicitud

    config = WorkflowConfig(
        model=Solicitud,
        state_field="estado",
        workflow_key="solicitud_preview_t",
        expose_endpoints=True,
        endpoint_slug="solicitudes-preview",
    )
    WorkflowRegistry.register("solicitud_preview_t", config)
    yield config


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(
        username="preview_admin", password="x", email="p@example.com"
    )


@pytest.fixture
def transition_setup(db):
    from tests.models import ProductoPrueba as ProductoCreditoFOVISSSTE, ProductoVersionFlujoPrueba as ProductoVersionFlujo
    from sinpapel.models import ConfiguracionTransicion, Estado, VersionFlujo

    eo = Estado.objects.create(nombre="PV_ORIGEN")
    ed = Estado.objects.create(nombre="PV_DESTINO")
    flujo = VersionFlujo.objects.create(nombre="PV_FLUJO", activo=True)
    ConfiguracionTransicion.objects.create(
        flujo=flujo, estado_origen=eo, estado_destino=ed,
    )
    producto = ProductoCreditoFOVISSSTE.objects.create(
        nombre="P_PV", clave="P-PV", identificador="PV",
        marca="TEST", monto_minimo=0, monto_maximo=0,
        tasa_interes=0, tasa_interes_moratorio=0,
    )
    ProductoVersionFlujo.objects.create(producto=producto, flujo=flujo)
    return {"estado_origen": eo, "estado_destino": ed,
            "producto": producto, "flujo": flujo}


@pytest.fixture
def solicitud_with_flujo(transition_setup, db):
    from tests.models import SolicitudPrueba as Solicitud

    return Solicitud.objects.create(
        producto=transition_setup["producto"],
        estado=transition_setup["estado_origen"],
        monto_solicitado=1000,
    )


@pytest.fixture
def api_client(expose_config, admin_user, settings):
    import sinpapel_drf.urls
    importlib.reload(sinpapel_drf.urls)
    mod = type("TestURLConfPreview", (), {
        "urlpatterns": [path("sinpapel/api/", include(sinpapel_drf.urls.urlpatterns))],
    })
    sys.modules["test_urlconf_preview"] = mod
    settings.ROOT_URLCONF = "test_urlconf_preview"
    clear_url_caches()
    client = APIClient()
    client.force_authenticate(user=admin_user)
    yield client
    sys.modules.pop("test_urlconf_preview", None)
    clear_url_caches()


@pytest.mark.django_db
def test_preview_transition_happy_path(
    transition_setup, solicitud_with_flujo, api_client,
):
    resp = api_client.post(
        f"/sinpapel/api/solicitudes-preview/{solicitud_with_flujo.pk}/preview-transition/",
        data={"target_state": "PV_DESTINO"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["permitido"] is True
    assert body["razones_bloqueo"] == []


@pytest.mark.django_db
def test_preview_transition_target_state_required(
    transition_setup, solicitud_with_flujo, api_client,
):
    resp = api_client.post(
        f"/sinpapel/api/solicitudes-preview/{solicitud_with_flujo.pk}/preview-transition/",
        data={},
        format="json",
    )
    assert resp.status_code == 400
    assert "target_state" in resp.json()


@pytest.mark.django_db
def test_preview_transition_invalid_target_blocked(
    transition_setup, solicitud_with_flujo, api_client,
):
    resp = api_client.post(
        f"/sinpapel/api/solicitudes-preview/{solicitud_with_flujo.pk}/preview-transition/",
        data={"target_state": "ESTADO_INEXISTENTE"},
        format="json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["permitido"] is False
    assert any(r["tipo"] == "estado" for r in body["razones_bloqueo"])


@pytest.mark.django_db
def test_preview_transition_does_not_mutate(
    transition_setup, solicitud_with_flujo, api_client,
):
    from sinpapel.models import SeguimientoWorkflow

    seg_before = SeguimientoWorkflow.objects.count()
    estado_before = solicitud_with_flujo.estado.nombre

    api_client.post(
        f"/sinpapel/api/solicitudes-preview/{solicitud_with_flujo.pk}/preview-transition/",
        data={"target_state": "PV_DESTINO"},
        format="json",
    )

    assert SeguimientoWorkflow.objects.count() == seg_before
    solicitud_with_flujo.refresh_from_db()
    assert solicitud_with_flujo.estado.nombre == estado_before


@pytest.mark.django_db
def test_preview_transition_requires_authentication(
    transition_setup, solicitud_with_flujo, expose_config, settings,
):
    import sinpapel_drf.urls
    importlib.reload(sinpapel_drf.urls)
    mod = type("TestURLConfNoAuth", (), {
        "urlpatterns": [path("sinpapel/api/", include(sinpapel_drf.urls.urlpatterns))],
    })
    sys.modules["test_urlconf_preview_noauth"] = mod
    settings.ROOT_URLCONF = "test_urlconf_preview_noauth"
    clear_url_caches()
    client = APIClient()  # no force_authenticate

    resp = client.post(
        f"/sinpapel/api/solicitudes-preview/{solicitud_with_flujo.pk}/preview-transition/",
        data={"target_state": "PV_DESTINO"},
        format="json",
    )
    assert resp.status_code == 401

    sys.modules.pop("test_urlconf_preview_noauth", None)
    clear_url_caches()
