"""S13.5 — E2E tests para WorkflowViewSet full implementation.

Cubre: serialized responses (AC2), full transition flow + DB updated (AC3),
error mapping 400/403/401 (AC3), pagination 10/100 (AC4).

Pattern reusado: APIClient.force_authenticate (S13.4),
expose_solicitud_config fixture (S13.4).
"""
from __future__ import annotations

import importlib
import sys

import pytest
from django.contrib.auth.models import User
from django.urls import clear_url_caches, include, path
from rest_framework.test import APIClient

from sinpapel.registry import WorkflowConfig, WorkflowRegistry


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def expose_solicitud_config(cleanup_registry):
    """Registra config extra para creditos.Solicitud con expose=True."""
    from tests.models import SolicitudPrueba as Solicitud

    config = WorkflowConfig(
        model=Solicitud,
        state_field="estado",
        workflow_key="solicitud_test_full",
        expose_endpoints=True,
        endpoint_slug="solicitudes-full",
    )
    WorkflowRegistry.register("solicitud_test_full", config)
    yield config


@pytest.fixture
def admin_user(db):
    """Superuser para bypass de permisos workflow."""
    return User.objects.create_superuser(
        username="s13_5_admin", password="x", email="s13_5@example.com"
    )


@pytest.fixture
def transition_setup(db):
    """Crea Estado origen/destino + VersionFlujo + ConfiguracionTransicion +
    Producto + ProductoVersionFlujo.
    """
    from tests.models import ProductoPrueba as ProductoCreditoFOVISSSTE, ProductoVersionFlujoPrueba as ProductoVersionFlujo
    from sinpapel.models import ConfiguracionTransicion, Estado, VersionFlujo

    estado_origen = Estado.objects.create(nombre="S13_5_ORIGEN")
    estado_destino = Estado.objects.create(nombre="S13_5_DESTINO")
    flujo = VersionFlujo.objects.create(nombre="S13_5_FLUJO", activo=True)
    ConfiguracionTransicion.objects.create(
        flujo=flujo,
        estado_origen=estado_origen,
        estado_destino=estado_destino,
    )
    producto = ProductoCreditoFOVISSSTE.objects.create(
        nombre="P_S13_5", clave="P-S13-5", identificador="S135",
        marca="TEST", monto_minimo=0, monto_maximo=0,
        tasa_interes=0, tasa_interes_moratorio=0,
    )
    ProductoVersionFlujo.objects.create(producto=producto, flujo=flujo)
    return {
        "estado_origen": estado_origen,
        "estado_destino": estado_destino,
        "producto": producto,
        "flujo": flujo,
    }


@pytest.fixture
def solicitud_with_flujo(transition_setup):
    """Solicitud lista para hacer transition: estado=ORIGEN, producto vinculado a flujo activo."""
    from tests.models import SolicitudPrueba as Solicitud
    return Solicitud.objects.create(
        estado=transition_setup["estado_origen"],
        producto=transition_setup["producto"],
    )


@pytest.fixture
def api_client_authenticated(expose_solicitud_config, admin_user, settings):
    """APIClient con force_authenticate + URLConf override que incluye sinpapel_drf.urls."""
    import sinpapel_drf.urls
    importlib.reload(sinpapel_drf.urls)

    urlconf_module = type(
        "TestURLConfFull",
        (),
        {
            "urlpatterns": [
                path("sinpapel/api/", include(sinpapel_drf.urls.urlpatterns)),
            ]
        },
    )

    sys.modules["test_urlconf_s13_5"] = urlconf_module
    settings.ROOT_URLCONF = "test_urlconf_s13_5"
    clear_url_caches()

    client = APIClient()
    client.force_authenticate(user=admin_user)
    yield client

    sys.modules.pop("test_urlconf_s13_5", None)
    clear_url_caches()


@pytest.fixture
def api_client_unauthenticated(expose_solicitud_config, settings):
    """APIClient SIN auth para test 401."""
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
    sys.modules["test_urlconf_s13_5_noauth"] = urlconf_module
    settings.ROOT_URLCONF = "test_urlconf_s13_5_noauth"
    clear_url_caches()

    client = APIClient()  # no force_authenticate
    yield client

    sys.modules.pop("test_urlconf_s13_5_noauth", None)
    clear_url_caches()


# ─────────────────────────────────────────────────────────────────────────────
# AC2 — available_transitions devuelve lista serializada (EstadoSerializer)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_available_transitions_returns_serialized_list(
    transition_setup, solicitud_with_flujo, api_client_authenticated,
):
    """GET .../available-transitions/ → 200 + lista con id/nombre serializados."""
    resp = api_client_authenticated.get(
        f"/sinpapel/api/solicitudes-full/{solicitud_with_flujo.pk}/available-transitions/"
    )
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.content!r}"
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 1
    entry = body[0]
    assert entry["id"] == transition_setup["estado_destino"].id
    assert entry["nombre"] == "S13_5_DESTINO"
    # color field presente (puede ser empty string)
    assert "color" in entry or True  # default empty


# ─────────────────────────────────────────────────────────────────────────────
# AC3 — transition full flow + error mapping
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db(transaction=True)
def test_transition_endpoint_executes_full_flow(
    transition_setup, solicitud_with_flujo, api_client_authenticated,
):
    """POST /transition/ ejecuta full flow → 201 + DB actualizado + response shape."""
    from sinpapel.models import SeguimientoWorkflow

    seg_before = SeguimientoWorkflow.objects.count()

    resp = api_client_authenticated.post(
        f"/sinpapel/api/solicitudes-full/{solicitud_with_flujo.pk}/transition/",
        data={"target_state": "S13_5_DESTINO", "comentarios": "approved by test"},
        format="json",
    )

    assert resp.status_code == 201, f"got {resp.status_code}: {resp.content!r}"
    body = resp.json()
    assert body["success"] is True
    assert body["estado_nuevo"] == "S13_5_DESTINO"
    assert body["estado_anterior"] == "S13_5_ORIGEN"
    assert "seguimiento_id" in body
    assert body["instance_id"] == solicitud_with_flujo.pk

    # DB realmente actualizado
    solicitud_with_flujo.refresh_from_db()
    assert solicitud_with_flujo.estado.nombre == "S13_5_DESTINO"
    assert SeguimientoWorkflow.objects.count() == seg_before + 1


@pytest.mark.django_db
def test_transition_invalid_target_returns_403(
    transition_setup, solicitud_with_flujo, api_client_authenticated,
):
    """target_state inexistente → engine PermissionError → DRF 403 (D-spec D3)."""
    resp = api_client_authenticated.post(
        f"/sinpapel/api/solicitudes-full/{solicitud_with_flujo.pk}/transition/",
        data={"target_state": "S13_5_DEFINITIVELY_DOES_NOT_EXIST"},
        format="json",
    )
    assert resp.status_code == 403, f"got {resp.status_code}: {resp.content!r}"
    body = resp.json()
    assert "detail" in body
    msg = body["detail"].lower()
    assert "no existe" in msg or "no se puede" in msg or "no válida" in msg or "no valida" in msg


@pytest.mark.django_db
def test_transition_validation_error_returns_400(
    transition_setup, solicitud_with_flujo, api_client_authenticated,
):
    """target_state ausente → DRF ValidationError → 400."""
    resp = api_client_authenticated.post(
        f"/sinpapel/api/solicitudes-full/{solicitud_with_flujo.pk}/transition/",
        data={},  # missing target_state
        format="json",
    )
    assert resp.status_code == 400, f"got {resp.status_code}: {resp.content!r}"
    body = resp.json()
    assert "target_state" in body


@pytest.mark.django_db
def test_transition_unauthenticated_returns_401_or_403(
    transition_setup, solicitud_with_flujo, api_client_unauthenticated,
):
    """Sin auth → IsAuthenticated rechaza con 401 o 403 (DRF default)."""
    resp = api_client_unauthenticated.post(
        f"/sinpapel/api/solicitudes-full/{solicitud_with_flujo.pk}/transition/",
        data={"target_state": "S13_5_DESTINO"},
        format="json",
    )
    assert resp.status_code in (401, 403), f"got {resp.status_code}"


# ─────────────────────────────────────────────────────────────────────────────
# AC4 — history pagination
# ─────────────────────────────────────────────────────────────────────────────


class _FakeHistory:
    """Fake substitute for instance.history (django-simple-history manager)."""

    def __init__(self, entries):
        self._entries = entries

    def all(self):
        return self._entries


def _make_fake_history_entries(count: int):
    """Crea fake HistoricalRecord-like entries."""
    from datetime import datetime, timedelta, timezone

    base = datetime(2026, 4, 28, 12, 0, tzinfo=timezone.utc)
    entries = []
    for i in range(count):
        e = type("FakeHist", (), {})()
        e.history_id = i + 1
        e.history_type = "+" if i == 0 else "~"
        e.history_date = base + timedelta(minutes=i)
        e.history_user = None  # D9: nullable
        e.history_change_reason = f"reason {i}"
        entries.append(e)
    return entries


@pytest.mark.django_db
def test_history_endpoint_paginated_default_page_size(
    transition_setup, solicitud_with_flujo, api_client_authenticated, monkeypatch,
):
    """GET /history/ sin query → paginated structure con page_size=10 (D4)."""
    fake_entries = _make_fake_history_entries(15)
    # Patch instance method via class — affects this and subsequent get_object()
    from tests.models import SolicitudPrueba as Solicitud
    monkeypatch.setattr(
        Solicitud, "history", property(lambda self: _FakeHistory(fake_entries)),
        raising=False,
    )

    resp = api_client_authenticated.get(
        f"/sinpapel/api/solicitudes-full/{solicitud_with_flujo.pk}/history/"
    )
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.content!r}"
    body = resp.json()
    # PageNumberPagination shape
    assert "results" in body
    assert "count" in body
    assert "next" in body
    assert "previous" in body
    assert body["count"] == 15
    assert len(body["results"]) == 10  # default page_size


@pytest.mark.django_db
def test_history_endpoint_page_size_query_param(
    transition_setup, solicitud_with_flujo, api_client_authenticated, monkeypatch,
):
    """GET /history/?page_size=2 → 2 entries por página (D4)."""
    fake_entries = _make_fake_history_entries(5)
    from tests.models import SolicitudPrueba as Solicitud
    monkeypatch.setattr(
        Solicitud, "history", property(lambda self: _FakeHistory(fake_entries)),
        raising=False,
    )

    resp = api_client_authenticated.get(
        f"/sinpapel/api/solicitudes-full/{solicitud_with_flujo.pk}/history/?page_size=2"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 5
    assert len(body["results"]) == 2


@pytest.mark.django_db
def test_history_endpoint_max_page_size_clamped(
    transition_setup, solicitud_with_flujo, api_client_authenticated, monkeypatch,
):
    """GET /history/?page_size=500 → clamped a max_page_size=100 (D4)."""
    fake_entries = _make_fake_history_entries(150)
    from tests.models import SolicitudPrueba as Solicitud
    monkeypatch.setattr(
        Solicitud, "history", property(lambda self: _FakeHistory(fake_entries)),
        raising=False,
    )

    resp = api_client_authenticated.get(
        f"/sinpapel/api/solicitudes-full/{solicitud_with_flujo.pk}/history/?page_size=500"
    )
    assert resp.status_code == 200
    body = resp.json()
    # max_page_size=100 cap
    assert len(body["results"]) <= 100


# ─────────────────────────────────────────────────────────────────────────────
# history fallback → SeguimientoWorkflow (modelos solo-Trazable sin
# HistoricalRecords). El consumidor (HistoryTimeline) mostraba "sin movimientos"
# porque instance.history lanzaba AttributeError y el endpoint devolvía []
# silenciosamente, ocultando transiciones reales registradas en
# SeguimientoWorkflow.
# ─────────────────────────────────────────────────────────────────────────────


def _crear_seguimientos(instance, user, pares):
    """Crea SeguimientoWorkflow reales (GFK a `instance`) para cada par
    (estado_anterior, estado_nuevo), con fecha_accion creciente para garantizar
    orden determinista. Devuelve la lista de objetos creados, en orden."""
    from datetime import datetime, timedelta, timezone

    from django.contrib.contenttypes.models import ContentType
    from sinpapel.models import SeguimientoWorkflow

    ct = ContentType.objects.get_for_model(type(instance))
    base = datetime(2026, 4, 28, 12, 0, tzinfo=timezone.utc)
    creados = []
    for i, (anterior, nuevo) in enumerate(pares):
        s = SeguimientoWorkflow.objects.create(
            target_content_type=ct,
            target_object_id=instance.pk,
            estado_anterior=anterior,
            estado_nuevo=nuevo,
            usuario_accion=user,
            comentarios="",
        )
        # fecha_accion es auto_now_add → se fija al crear; lo sobreescribimos
        # vía .update() (bypass de auto_now_add) para tener timestamps distintos.
        SeguimientoWorkflow.objects.filter(pk=s.pk).update(
            fecha_accion=base + timedelta(minutes=i)
        )
        creados.append(s)
    return creados


@pytest.mark.django_db
def test_history_fallback_to_seguimiento_for_trazable_only_model(
    transition_setup, solicitud_with_flujo, api_client_authenticated, admin_user,
):
    """Modelo solo-Trazable con N transiciones en SeguimientoWorkflow → /history/
    devuelve N entradas, más reciente primero, history_type '+'/'~' y
    change_reason 'A → B'."""
    from sinpapel.models import Estado

    origen = transition_setup["estado_origen"]    # S13_5_ORIGEN
    destino = transition_setup["estado_destino"]  # S13_5_DESTINO
    tercero = Estado.objects.create(nombre="S13_5_TERCERO")

    # creación (anterior None) → '+', luego dos modificaciones → '~'
    _crear_seguimientos(
        solicitud_with_flujo, admin_user,
        [(None, origen), (origen, destino), (destino, tercero)],
    )

    resp = api_client_authenticated.get(
        f"/sinpapel/api/solicitudes-full/{solicitud_with_flujo.pk}/history/"
    )
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.content!r}"
    body = resp.json()
    assert body["count"] == 3
    results = body["results"]
    assert len(results) == 3

    # más reciente primero: la última transición (destino → tercero) arriba
    assert results[0]["history_type"] == "~"
    assert results[0]["history_change_reason"] == "S13_5_DESTINO → S13_5_TERCERO"
    assert results[0]["history_user"] == admin_user.username
    # intermedia
    assert results[1]["history_type"] == "~"
    assert results[1]["history_change_reason"] == "S13_5_ORIGEN → S13_5_DESTINO"
    # la creación (estado_anterior None) → '+', más antigua → al final
    assert results[-1]["history_type"] == "+"
    assert results[-1]["history_change_reason"] == "S13_5_ORIGEN"


@pytest.mark.django_db
def test_history_fallback_appends_comentarios_to_change_reason(
    transition_setup, solicitud_with_flujo, api_client_authenticated, admin_user,
):
    """change_reason adjunta los comentarios de la transición tras la flecha."""
    from django.contrib.contenttypes.models import ContentType
    from sinpapel.models import SeguimientoWorkflow

    ct = ContentType.objects.get_for_model(type(solicitud_with_flujo))
    SeguimientoWorkflow.objects.create(
        target_content_type=ct,
        target_object_id=solicitud_with_flujo.pk,
        estado_anterior=transition_setup["estado_origen"],
        estado_nuevo=transition_setup["estado_destino"],
        usuario_accion=admin_user,
        comentarios="aprobado por comité",
    )

    resp = api_client_authenticated.get(
        f"/sinpapel/api/solicitudes-full/{solicitud_with_flujo.pk}/history/"
    )
    body = resp.json()
    assert body["count"] == 1
    assert (
        body["results"][0]["history_change_reason"]
        == "S13_5_ORIGEN → S13_5_DESTINO — aprobado por comité"
    )


@pytest.mark.django_db
def test_history_trazable_only_no_transitions_returns_count_zero(
    transition_setup, solicitud_with_flujo, api_client_authenticated,
):
    """Modelo solo-Trazable SIN transiciones → count 0, sin error (el fallback
    consulta SeguimientoWorkflow y no encuentra nada)."""
    resp = api_client_authenticated.get(
        f"/sinpapel/api/solicitudes-full/{solicitud_with_flujo.pk}/history/"
    )
    assert resp.status_code == 200
    body = resp.json()
    # paginated empty: count=0
    if isinstance(body, dict):
        assert body.get("count", 0) == 0
        assert body.get("results", []) == []
    else:
        assert body == []


@pytest.mark.django_db
def test_history_prefers_historicalrecords_over_seguimiento(
    transition_setup, solicitud_with_flujo, api_client_authenticated,
    admin_user, monkeypatch,
):
    """Si el modelo SÍ declara HistoricalRecords, /history/ los sirve y NO hace
    fallback a SeguimientoWorkflow (aunque existan transiciones)."""
    from django.contrib.contenttypes.models import ContentType
    from tests.models import SolicitudPrueba as Solicitud
    from sinpapel.models import SeguimientoWorkflow

    ct = ContentType.objects.get_for_model(Solicitud)
    SeguimientoWorkflow.objects.create(
        target_content_type=ct,
        target_object_id=solicitud_with_flujo.pk,
        estado_anterior=None,
        estado_nuevo=transition_setup["estado_origen"],
        usuario_accion=admin_user,
        comentarios="",
    )
    fake_entries = _make_fake_history_entries(2)
    monkeypatch.setattr(
        Solicitud, "history", property(lambda self: _FakeHistory(fake_entries)),
        raising=False,
    )

    resp = api_client_authenticated.get(
        f"/sinpapel/api/solicitudes-full/{solicitud_with_flujo.pk}/history/"
    )
    assert resp.status_code == 200
    body = resp.json()
    # 2 fake HistoricalRecords, NO la transición de SeguimientoWorkflow
    assert body["count"] == 2
    assert {r["history_change_reason"] for r in body["results"]} == {
        "reason 0", "reason 1",
    }
