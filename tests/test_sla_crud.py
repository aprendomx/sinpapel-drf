"""v0.2.0 — E2E tests for SLAConfiguracion CRUD + verificar action.

NOT runnable in this workspace. Exercised when sinpapel-drf v0.2.0 is
installed in the mossc (creditos) project.
"""
from __future__ import annotations

import importlib
import sys
from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.urls import clear_url_caches, include, path
from rest_framework.test import APIClient

from sinpapel.registry import WorkflowConfig, WorkflowRegistry


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(
        username="sla_admin", password="x", email="sa@example.com"
    )


@pytest.fixture
def regular_user(db):
    return User.objects.create_user(
        username="sla_user", password="x", email="su@example.com"
    )


@pytest.fixture
def estado(db):
    from sinpapel.models import Estado
    return Estado.objects.create(nombre="SLA_ESTADO_TEST")


@pytest.fixture
def api_admin(admin_user, settings):
    import sinpapel_drf.urls
    importlib.reload(sinpapel_drf.urls)
    mod = type("TestURLConfSLA", (), {
        "urlpatterns": [path("sinpapel/api/", include(sinpapel_drf.urls.urlpatterns))],
    })
    sys.modules["test_urlconf_sla"] = mod
    settings.ROOT_URLCONF = "test_urlconf_sla"
    clear_url_caches()
    client = APIClient()
    client.force_authenticate(user=admin_user)
    yield client
    sys.modules.pop("test_urlconf_sla", None)
    clear_url_caches()


@pytest.fixture
def api_user(regular_user, settings):
    import sinpapel_drf.urls
    importlib.reload(sinpapel_drf.urls)
    mod = type("TestURLConfSLAU", (), {
        "urlpatterns": [path("sinpapel/api/", include(sinpapel_drf.urls.urlpatterns))],
    })
    sys.modules["test_urlconf_sla_u"] = mod
    settings.ROOT_URLCONF = "test_urlconf_sla_u"
    clear_url_caches()
    client = APIClient()
    client.force_authenticate(user=regular_user)
    yield client
    sys.modules.pop("test_urlconf_sla_u", None)
    clear_url_caches()


def _results(body):
    if isinstance(body, dict) and "results" in body:
        return body["results"]
    return body


@pytest.mark.django_db
def test_sla_list_filters_by_estado(estado, api_admin):
    from sinpapel.models import Estado, SLAConfiguracion

    other_estado = Estado.objects.create(nombre="SLA_OTRO")
    SLAConfiguracion.objects.create(
        estado=estado, dias_maximos=3, accion_vencimiento="notificar",
    )
    SLAConfiguracion.objects.create(
        estado=other_estado, dias_maximos=5, accion_vencimiento="notificar",
    )
    resp = api_admin.get(f"/sinpapel/api/slas/?estado={estado.id}")
    assert resp.status_code == 200
    results = _results(resp.json())
    assert len(results) == 1
    assert results[0]["estado"] == estado.id


@pytest.mark.django_db
def test_sla_create(estado, api_admin):
    resp = api_admin.post(
        "/sinpapel/api/slas/",
        data={
            "estado": estado.id, "dias_maximos": 7,
            "accion_vencimiento": "notificar",
            "configuracion_accion": {"grupo_id": 1, "template": "vence.html"},
            "activo": True,
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    assert resp.json()["dias_maximos"] == 7


@pytest.mark.django_db
def test_sla_update(estado, api_admin):
    from sinpapel.models import SLAConfiguracion

    sla = SLAConfiguracion.objects.create(
        estado=estado, dias_maximos=3, accion_vencimiento="notificar",
    )
    resp = api_admin.patch(
        f"/sinpapel/api/slas/{sla.id}/", data={"dias_maximos": 10}, format="json",
    )
    assert resp.status_code == 200
    sla.refresh_from_db()
    assert sla.dias_maximos == 10


@pytest.mark.django_db
def test_sla_delete(estado, api_admin):
    from sinpapel.models import SLAConfiguracion

    sla = SLAConfiguracion.objects.create(
        estado=estado, dias_maximos=3, accion_vencimiento="alertar",
    )
    resp = api_admin.delete(f"/sinpapel/api/slas/{sla.id}/")
    assert resp.status_code == 204
    assert not SLAConfiguracion.objects.filter(id=sla.id).exists()


@pytest.mark.django_db
def test_sla_unique_together_violation_returns_400(estado, api_admin):
    from sinpapel.models import SLAConfiguracion

    SLAConfiguracion.objects.create(
        estado=estado, dias_maximos=3, accion_vencimiento="notificar",
    )
    resp = api_admin.post(
        "/sinpapel/api/slas/",
        data={"estado": estado.id, "dias_maximos": 5, "accion_vencimiento": "notificar"},
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_sla_non_admin_forbidden(estado, api_user):
    resp = api_user.get("/sinpapel/api/slas/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_sla_verificar_returns_counts(estado, api_admin):
    resp = api_admin.post("/sinpapel/api/slas/verificar/")
    assert resp.status_code == 200
    body = resp.json()
    assert "ejecutadas" in body
    assert isinstance(body["ejecutadas"], dict)


@pytest.mark.django_db
def test_sla_verificar_non_admin_forbidden(estado, api_user):
    resp = api_user.post("/sinpapel/api/slas/verificar/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_sla_retrieve(estado, api_admin):
    from sinpapel.models import SLAConfiguracion

    sla = SLAConfiguracion.objects.create(
        estado=estado, dias_maximos=14, accion_vencimiento="escalar",
    )
    resp = api_admin.get(f"/sinpapel/api/slas/{sla.id}/")
    assert resp.status_code == 200
    assert resp.json()["accion_vencimiento"] == "escalar"


# ── Task 7: per-instance sla_status action ─────────────────────────────────


@pytest.fixture
def expose_sla_config(cleanup_registry):
    from tests.models import SolicitudPrueba as Solicitud

    config = WorkflowConfig(
        model=Solicitud,
        state_field="estado",
        workflow_key="solicitud_sla_t",
        expose_endpoints=True,
        endpoint_slug="solicitudes-sla",
    )
    WorkflowRegistry.register("solicitud_sla_t", config)
    yield config


@pytest.fixture
def solicitud_for_sla(estado, db):
    from tests.models import ProductoPrueba as ProductoCreditoFOVISSSTE, SolicitudPrueba as Solicitud

    producto = ProductoCreditoFOVISSSTE.objects.create(
        nombre="P_SLA", clave="P-SLA", identificador="SL",
        marca="TEST", monto_minimo=0, monto_maximo=0,
        tasa_interes=0, tasa_interes_moratorio=0,
    )
    return Solicitud.objects.create(
        producto=producto, estado=estado, monto_solicitado=100,
    )


@pytest.fixture
def api_admin_sla(expose_sla_config, admin_user, settings):
    import sinpapel_drf.urls
    importlib.reload(sinpapel_drf.urls)
    mod = type("TestURLConfSLAStatus", (), {
        "urlpatterns": [path("sinpapel/api/", include(sinpapel_drf.urls.urlpatterns))],
    })
    sys.modules["test_urlconf_sla_status"] = mod
    settings.ROOT_URLCONF = "test_urlconf_sla_status"
    clear_url_caches()
    client = APIClient()
    client.force_authenticate(user=admin_user)
    yield client
    sys.modules.pop("test_urlconf_sla_status", None)
    clear_url_caches()


@pytest.mark.django_db
def test_sla_status_no_sla_returns_empty_list(solicitud_for_sla, api_admin_sla):
    resp = api_admin_sla.post(
        f"/sinpapel/api/solicitudes-sla/{solicitud_for_sla.pk}/sla-status/"
    )
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.django_db
def test_sla_status_not_expired_returns_empty_list(
    solicitud_for_sla, estado, api_admin_sla,
):
    from sinpapel.models import SLAConfiguracion

    SLAConfiguracion.objects.create(
        estado=estado, dias_maximos=99,  # not yet expired
        accion_vencimiento="notificar",
    )
    resp = api_admin_sla.post(
        f"/sinpapel/api/solicitudes-sla/{solicitud_for_sla.pk}/sla-status/"
    )
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.django_db
def test_sla_status_expired_executes_action(
    solicitud_for_sla, estado, api_admin_sla,
):
    from django.utils import timezone

    from sinpapel.models import SLAConfiguracion

    SLAConfiguracion.objects.create(
        estado=estado, dias_maximos=1, accion_vencimiento="notificar",
        configuracion_accion={"template": "vencido.html"},
    )
    # Backdate so SLA is expired
    solicitud_for_sla.creado = timezone.now() - timedelta(days=5)
    solicitud_for_sla.save(update_fields=["creado"])

    resp = api_admin_sla.post(
        f"/sinpapel/api/solicitudes-sla/{solicitud_for_sla.pk}/sla-status/"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["accion"] == "notificar"
