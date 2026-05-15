"""v0.2.0 — E2E tests for CondicionTransicion CRUD endpoints.

NOT runnable in this workspace. Exercised when sinpapel-drf v0.2.0 is
installed in the mossc (creditos) project.
"""
from __future__ import annotations

import importlib
import sys

import pytest
from django.contrib.auth.models import User
from django.urls import clear_url_caches, include, path
from rest_framework.test import APIClient


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(
        username="cond_admin", password="x", email="ca@example.com"
    )


@pytest.fixture
def regular_user(db):
    return User.objects.create_user(
        username="cond_user", password="x", email="cu@example.com"
    )


@pytest.fixture
def transition_db(db):
    from sinpapel.models import ConfiguracionTransicion, Estado, VersionFlujo

    eo = Estado.objects.create(nombre="C_ORIGEN")
    ed = Estado.objects.create(nombre="C_DESTINO")
    flujo = VersionFlujo.objects.create(nombre="C_FLUJO", activo=True)
    return ConfiguracionTransicion.objects.create(
        flujo=flujo, estado_origen=eo, estado_destino=ed,
    )


@pytest.fixture
def api_admin(admin_user, settings):
    import sinpapel_drf.urls
    importlib.reload(sinpapel_drf.urls)
    mod = type("TestURLConfCond", (), {
        "urlpatterns": [path("sinpapel/api/", include(sinpapel_drf.urls.urlpatterns))],
    })
    sys.modules["test_urlconf_cond"] = mod
    settings.ROOT_URLCONF = "test_urlconf_cond"
    clear_url_caches()
    client = APIClient()
    client.force_authenticate(user=admin_user)
    yield client
    sys.modules.pop("test_urlconf_cond", None)
    clear_url_caches()


@pytest.fixture
def api_user(regular_user, settings):
    import sinpapel_drf.urls
    importlib.reload(sinpapel_drf.urls)
    mod = type("TestURLConfCondU", (), {
        "urlpatterns": [path("sinpapel/api/", include(sinpapel_drf.urls.urlpatterns))],
    })
    sys.modules["test_urlconf_cond_u"] = mod
    settings.ROOT_URLCONF = "test_urlconf_cond_u"
    clear_url_caches()
    client = APIClient()
    client.force_authenticate(user=regular_user)
    yield client
    sys.modules.pop("test_urlconf_cond_u", None)
    clear_url_caches()


def _results(body):
    if isinstance(body, dict) and "results" in body:
        return body["results"]
    return body


@pytest.mark.django_db
def test_condicion_list_filters_by_transicion(transition_db, api_admin):
    from sinpapel.models import CondicionTransicion, ConfiguracionTransicion

    CondicionTransicion.objects.create(
        transicion=transition_db, tipo="python_path",
        configuracion={"path": "x.y"}, orden=1,
    )
    other_t = ConfiguracionTransicion.objects.create(
        flujo=transition_db.flujo,
        estado_origen=transition_db.estado_origen,
        estado_destino=transition_db.estado_destino,
    )
    CondicionTransicion.objects.create(
        transicion=other_t, tipo="json_logic",
        configuracion={"logic": {">": [1, 0]}}, orden=1,
    )

    resp = api_admin.get(f"/sinpapel/api/condiciones/?transicion={transition_db.id}")
    assert resp.status_code == 200
    results = _results(resp.json())
    assert len(results) == 1
    assert results[0]["tipo"] == "python_path"


@pytest.mark.django_db
def test_condicion_list_filters_by_activo(transition_db, api_admin):
    from sinpapel.models import CondicionTransicion

    CondicionTransicion.objects.create(
        transicion=transition_db, tipo="python_path",
        configuracion={"path": "x"}, activo=True,
    )
    CondicionTransicion.objects.create(
        transicion=transition_db, tipo="json_logic",
        configuracion={"logic": True}, activo=False,
    )
    resp = api_admin.get("/sinpapel/api/condiciones/?activo=false")
    assert resp.status_code == 200
    results = _results(resp.json())
    assert all(r["activo"] is False for r in results)


@pytest.mark.django_db
def test_condicion_create(transition_db, api_admin):
    resp = api_admin.post(
        "/sinpapel/api/condiciones/",
        data={
            "transicion": transition_db.id, "tipo": "json_logic",
            "configuracion": {"logic": {">": [{"var": "monto"}, 0]}},
            "mensaje_error": "Monto inválido", "orden": 5, "activo": True,
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["tipo"] == "json_logic"
    assert body["orden"] == 5


@pytest.mark.django_db
def test_condicion_update_toggles_activo(transition_db, api_admin):
    from sinpapel.models import CondicionTransicion

    c = CondicionTransicion.objects.create(
        transicion=transition_db, tipo="python_path",
        configuracion={"path": "x"}, activo=True,
    )
    resp = api_admin.patch(
        f"/sinpapel/api/condiciones/{c.id}/", data={"activo": False}, format="json",
    )
    assert resp.status_code == 200
    c.refresh_from_db()
    assert c.activo is False


@pytest.mark.django_db
def test_condicion_delete(transition_db, api_admin):
    from sinpapel.models import CondicionTransicion

    c = CondicionTransicion.objects.create(
        transicion=transition_db, tipo="python_path", configuracion={},
    )
    resp = api_admin.delete(f"/sinpapel/api/condiciones/{c.id}/")
    assert resp.status_code == 204
    assert not CondicionTransicion.objects.filter(id=c.id).exists()


@pytest.mark.django_db
def test_condicion_non_admin_forbidden(transition_db, api_user):
    resp = api_user.get("/sinpapel/api/condiciones/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_condicion_retrieve(transition_db, api_admin):
    from sinpapel.models import CondicionTransicion

    c = CondicionTransicion.objects.create(
        transicion=transition_db, tipo="json_logic",
        configuracion={"logic": True}, orden=7,
    )
    resp = api_admin.get(f"/sinpapel/api/condiciones/{c.id}/")
    assert resp.status_code == 200
    assert resp.json()["orden"] == 7
