# Document Upload + Validation Endpoints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Exponer en `sinpapel-drf` endpoints para cargar documentos (`InstanciaDocumento`), listarlos, borrarlos y consultar el cumplimiento de requisitos del estado actual.

**Architecture:** Acciones `@action` nuevas en `WorkflowViewSet` (auto-enrutadas por `SinpapelRouter`). La carga crea `InstanciaDocumento` (typed); el cumplimiento se obtiene del mecanismo público upstream `WorkflowEngine.evaluar_requisitos_documentales`, sin duplicar lógica.

**Tech Stack:** Django REST Framework, sinpapel (`@workflow_enabled`, `WorkflowEngine`, modelos `Documento`/`TipoDocumento`/`InstanciaDocumento`/`RequisitoEstadoDocumento`).

## Global Constraints

- **Depende de un tag de `sinpapel`** que incluya, además del enforce de `RequisitoEstadoDocumento` (ya en 0.6.0): (a) campo `InstanciaDocumento.archivo` (`upload_to="instancias_documento/"`, `blank=True, null=True`) + migración; (b) método público `WorkflowEngine.evaluar_requisitos_documentales(instance, estado=None) -> list[dict]`. El pin de `pyproject.toml` debe bumpearse a ese tag antes de ejecutar este plan.
- **Tests corren en el host creditos/mossc** (`DJANGO_SETTINGS_MODULE` apuntando a sus settings), igual que toda la suite existente — importan `creditos.models.Solicitud`. No son runnable en el workspace aislado de sinpapel-drf.
- Permiso de todos los endpoints nuevos: `IsAuthenticated` (consistente con `transition`).
- Serializers son `serializers.Serializer` (no `ModelSerializer`), siguiendo la convención del repo.
- Modelos siempre desde `sinpapel.models`. Imports locales dentro de los métodos, como en el resto de `viewsets.py`.
- `target` (GFK) se fija desde el `<pk>` de la URL; nunca del cliente.

---

### Task 1: Serializers de InstanciaDocumento (carga + lectura)

**Files:**
- Modify: `serializers.py` (añadir al final)
- Test: `tests/test_documentos_serializers.py`

**Interfaces:**
- Produces:
  - `InstanciaDocumentoSerializer` (read): campos `id, documento, tipo_documento, archivo, porcentaje, creado`.
  - `InstanciaDocumentoUploadSerializer` (write): valida `archivo` (req), `documento`|`tipo_documento` (uno), `porcentaje` (0-100, default 100), `metadatos` (dict). Tras `is_valid`, `validated_data["documento_obj"]` es la instancia `Documento` resuelta.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_documentos_serializers.py
"""Unit tests del serializer de carga — resolución documento/tipo_documento."""
from __future__ import annotations

import pytest

from sinpapel_drf.serializers import InstanciaDocumentoUploadSerializer


@pytest.fixture
def tipo_y_documento(db):
    from sinpapel.models import Documento, TipoDocumento
    td = TipoDocumento.objects.create(nombre="INE")
    doc = Documento.objects.create(nombre="INE", tipo_documento=td, valor="INE")
    return td, doc


def _archivo():
    from django.core.files.uploadedfile import SimpleUploadedFile
    return SimpleUploadedFile("ine.pdf", b"%PDF-fake", content_type="application/pdf")


@pytest.mark.django_db
def test_upload_resuelve_por_documento_pk(tipo_y_documento):
    _td, doc = tipo_y_documento
    s = InstanciaDocumentoUploadSerializer(
        data={"archivo": _archivo(), "documento": doc.pk}
    )
    assert s.is_valid(), s.errors
    assert s.validated_data["documento_obj"].pk == doc.pk
    assert s.validated_data["porcentaje"] == 100


@pytest.mark.django_db
def test_upload_resuelve_por_tipo_unico(tipo_y_documento):
    td, doc = tipo_y_documento
    s = InstanciaDocumentoUploadSerializer(
        data={"archivo": _archivo(), "tipo_documento": td.pk}
    )
    assert s.is_valid(), s.errors
    assert s.validated_data["documento_obj"].pk == doc.pk


@pytest.mark.django_db
def test_upload_tipo_sin_documento_da_error(db):
    from sinpapel.models import TipoDocumento
    td = TipoDocumento.objects.create(nombre="CURP")
    s = InstanciaDocumentoUploadSerializer(
        data={"archivo": _archivo(), "tipo_documento": td.pk}
    )
    assert not s.is_valid()
    assert "tipo_documento" in s.errors


@pytest.mark.django_db
def test_upload_tipo_ambiguo_da_error(db):
    from sinpapel.models import Documento, TipoDocumento
    td = TipoDocumento.objects.create(nombre="COMPROBANTE")
    Documento.objects.create(nombre="A", tipo_documento=td, valor="A")
    Documento.objects.create(nombre="B", tipo_documento=td, valor="B")
    s = InstanciaDocumentoUploadSerializer(
        data={"archivo": _archivo(), "tipo_documento": td.pk}
    )
    assert not s.is_valid()
    assert "tipo_documento" in s.errors


@pytest.mark.django_db
def test_upload_sin_tipo_ni_documento_da_error():
    s = InstanciaDocumentoUploadSerializer(data={"archivo": _archivo()})
    assert not s.is_valid()


@pytest.mark.django_db
def test_upload_porcentaje_fuera_de_rango(tipo_y_documento):
    _td, doc = tipo_y_documento
    s = InstanciaDocumentoUploadSerializer(
        data={"archivo": _archivo(), "documento": doc.pk, "porcentaje": 150}
    )
    assert not s.is_valid()
    assert "porcentaje" in s.errors
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_documentos_serializers.py -v`
Expected: FAIL — `ImportError: cannot import name 'InstanciaDocumentoUploadSerializer'`

- [ ] **Step 3: Write minimal implementation**

```python
# serializers.py — añadir al final del archivo

# ── Document upload / validation serializers ────────────────────────────────


class InstanciaDocumentoSerializer(serializers.Serializer):
    """Read serializer para InstanciaDocumento (listado + respuesta de carga)."""

    id = serializers.IntegerField(read_only=True)
    documento = serializers.IntegerField(source="documento_id", allow_null=True)
    tipo_documento = serializers.CharField(
        source="documento.tipo_documento.nombre",
        allow_null=True,
        required=False,
    )
    archivo = serializers.FileField(allow_null=True, required=False)
    porcentaje = serializers.IntegerField()
    creado = serializers.DateTimeField(allow_null=True)


class InstanciaDocumentoUploadSerializer(serializers.Serializer):
    """Write serializer para POST /documentos/.

    Acepta `documento` (PK) o `tipo_documento` (PK). Resuelve el Documento y
    lo deja en validated_data["documento_obj"]. Regla por tipo: exactamente 1
    Documento del tipo → se usa; 0 o >1 → error (pedir `documento` explícito).
    """

    archivo = serializers.FileField(required=True)
    documento = serializers.IntegerField(required=False, allow_null=True)
    tipo_documento = serializers.IntegerField(required=False, allow_null=True)
    porcentaje = serializers.IntegerField(
        required=False, default=100, min_value=0, max_value=100
    )
    metadatos = serializers.JSONField(required=False, default=dict)

    def validate(self, attrs):
        from sinpapel.models import Documento

        doc_pk = attrs.get("documento")
        tipo_pk = attrs.get("tipo_documento")
        if not doc_pk and not tipo_pk:
            raise serializers.ValidationError(
                "Debe enviar 'documento' o 'tipo_documento'."
            )
        if doc_pk:
            try:
                documento = Documento.objects.get(pk=doc_pk)
            except Documento.DoesNotExist:
                raise serializers.ValidationError(
                    {"documento": "Documento inexistente."}
                )
        else:
            qs = Documento.objects.filter(tipo_documento_id=tipo_pk)
            n = qs.count()
            if n == 0:
                raise serializers.ValidationError(
                    {"tipo_documento": "No hay Documento de ese tipo; envíe 'documento'."}
                )
            if n > 1:
                raise serializers.ValidationError(
                    {"tipo_documento": "Hay varios Documento de ese tipo; envíe 'documento'."}
                )
            documento = qs.first()
        attrs["documento_obj"] = documento
        return attrs
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_documentos_serializers.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add serializers.py tests/test_documentos_serializers.py
git commit -m "feat: serializers de carga/lectura de InstanciaDocumento"
```

---

### Task 2: Acción `documentos` (POST crear + GET listar)

**Files:**
- Modify: `viewsets.py` (nueva `@action` en `WorkflowViewSet`)
- Test: `tests/test_documentos_endpoint.py` (crear con fixtures compartidas)

**Interfaces:**
- Consumes: `InstanciaDocumentoSerializer`, `InstanciaDocumentoUploadSerializer` (Task 1).
- Produces: endpoint `GET/POST /<slug>/<pk>/documentos/`. POST → 201 con el objeto creado; GET → lista del trámite.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_documentos_endpoint.py
"""E2E de los endpoints de documentos. Corre en el host creditos."""
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
    from creditos.models import Solicitud
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
    from creditos.models import ProductoCreditoFOVISSSTE, Solicitud
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_documentos_endpoint.py -k post_documento -v`
Expected: FAIL — 404 (la ruta `documentos/` aún no existe)

- [ ] **Step 3: Write minimal implementation**

```python
# viewsets.py — nueva acción dentro de WorkflowViewSet (junto a las demás @action)

    @action(
        detail=True, methods=["get", "post"], url_path="documentos",
        parser_classes=[JSONParser, MultiPartParser, FormParser],
    )
    def documentos(self, request, pk=None):
        """GET lista / POST sube InstanciaDocumento del trámite (carga typed)."""
        from django.contrib.contenttypes.models import ContentType
        from sinpapel.models import InstanciaDocumento
        from sinpapel_drf.serializers import (
            InstanciaDocumentoSerializer,
            InstanciaDocumentoUploadSerializer,
        )

        instance = self.get_object()
        ct = ContentType.objects.get_for_model(type(instance))

        if request.method == "GET":
            qs = (
                InstanciaDocumento.objects.filter(
                    target_content_type=ct, target_object_id=instance.pk
                )
                .select_related("documento", "documento__tipo_documento")
                .order_by("-creado")
            )
            return Response(InstanciaDocumentoSerializer(qs, many=True).data)

        # POST
        s = InstanciaDocumentoUploadSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        inst = InstanciaDocumento.objects.create(
            documento=data["documento_obj"],
            target=instance,
            archivo=data["archivo"],
            porcentaje=data.get("porcentaje", 100),
            metadatos=data.get("metadatos") or {},
            autor=request.user,
            modificador=request.user,
        )
        return Response(
            InstanciaDocumentoSerializer(inst).data,
            status=status.HTTP_201_CREATED,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_documentos_endpoint.py -k "post_documento or lista" -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add viewsets.py tests/test_documentos_endpoint.py
git commit -m "feat: endpoint GET/POST /documentos/ (carga de InstanciaDocumento)"
```

---

### Task 3: Acción DELETE `documentos/<doc_id>/`

**Files:**
- Modify: `viewsets.py` (nueva `@action`)
- Test: `tests/test_documentos_endpoint.py` (añadir tests; reusa fixtures de Task 2)

**Interfaces:**
- Produces: endpoint `DELETE /<slug>/<pk>/documentos/<doc_id>/` → 204 si pertenece al trámite, 404 si no.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_documentos_endpoint.py — añadir al final

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
    from creditos.models import Solicitud
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_documentos_endpoint.py -k delete -v`
Expected: FAIL — 404 en el caso "propio" (la ruta DELETE no existe aún) o 405

- [ ] **Step 3: Write minimal implementation**

```python
# viewsets.py — nueva acción dentro de WorkflowViewSet

    @action(
        detail=True, methods=["delete"],
        url_path=r"documentos/(?P<doc_id>[0-9]+)",
    )
    def documento_detail(self, request, pk=None, doc_id=None):
        """DELETE un InstanciaDocumento, solo si pertenece al trámite."""
        from django.contrib.contenttypes.models import ContentType
        from rest_framework.exceptions import NotFound
        from sinpapel.models import InstanciaDocumento

        instance = self.get_object()
        ct = ContentType.objects.get_for_model(type(instance))
        try:
            inst = InstanciaDocumento.objects.get(
                pk=doc_id, target_content_type=ct, target_object_id=instance.pk
            )
        except InstanciaDocumento.DoesNotExist:
            raise NotFound("Documento no encontrado para este trámite.")
        inst.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_documentos_endpoint.py -k delete -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add viewsets.py tests/test_documentos_endpoint.py
git commit -m "feat: endpoint DELETE /documentos/<id>/"
```

---

### Task 4: Acción `requisitos` (cumplimiento del estado actual)

**Files:**
- Modify: `serializers.py` (`RequisitoStatusSerializer`)
- Modify: `viewsets.py` (nueva `@action`)
- Test: `tests/test_documentos_endpoint.py` (añadir tests)

**Interfaces:**
- Consumes: `WorkflowEngine.evaluar_requisitos_documentales(instance)` (upstream).
- Produces: endpoint `GET /<slug>/<pk>/requisitos/` → lista serializada con `RequisitoStatusSerializer`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_documentos_endpoint.py — añadir al final

@pytest.mark.django_db
def test_requisitos_refleja_satisfecho(solicitud, catalogo, api_client):
    from sinpapel.models import RequisitoEstadoDocumento
    RequisitoEstadoDocumento.objects.create(
        estado=solicitud.estado, tipo_documento=catalogo["tipo"],
        porcentaje=100, auto_carga=False,
    )
    # Antes de cargar: no satisfecho
    resp = api_client.get(
        f"/sinpapel/api/solicitudes-docs/{solicitud.pk}/requisitos/"
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    ine = next(r for r in body if r.get("tipo_documento") == "INE")
    assert ine["satisfecho"] is False
    assert ine["porcentaje_requerido"] == 100

    # Cargar al 100%
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_documentos_endpoint.py -k requisitos -v`
Expected: FAIL — 404 (la ruta `requisitos/` no existe aún)

- [ ] **Step 3: Write minimal implementation**

```python
# serializers.py — añadir al final

class RequisitoStatusSerializer(serializers.Serializer):
    """Mapea la forma de WorkflowEngine.evaluar_requisitos_documentales()."""

    nivel = serializers.CharField()
    tipo_documento = serializers.CharField(allow_null=True, required=False)
    porcentaje_requerido = serializers.IntegerField(allow_null=True, required=False)
    porcentaje_actual = serializers.IntegerField(allow_null=True, required=False)
    satisfecho = serializers.BooleanField()
    auto_carga = serializers.BooleanField(required=False, default=False)
    mensaje = serializers.CharField(allow_blank=True, required=False)
```

```python
# viewsets.py — nueva acción dentro de WorkflowViewSet

    @action(detail=True, methods=["get"], url_path="requisitos")
    def requisitos(self, request, pk=None):
        """GET requisitos documentales del estado actual + cumplimiento."""
        from sinpapel.services.workflow_engine import WorkflowEngine
        from sinpapel_drf.serializers import RequisitoStatusSerializer

        instance = self.get_object()
        data = WorkflowEngine().evaluar_requisitos_documentales(instance)
        return Response(RequisitoStatusSerializer(data, many=True).data)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_documentos_endpoint.py -k requisitos -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add serializers.py viewsets.py tests/test_documentos_endpoint.py
git commit -m "feat: endpoint GET /requisitos/ vía mecanismo upstream compartido"
```

---

### Task 5: Documentación (README + CHANGELOG)

**Files:**
- Modify: `README.md`, `README.es.md` (tabla de endpoints por instancia)
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Añadir las 4 filas a la tabla de endpoints en `README.md` y `README.es.md`**

```markdown
| `POST /<slug>/<pk>/documentos/` | Sube un documento (InstanciaDocumento, multipart). | `IsAuthenticated` |
| `GET /<slug>/<pk>/documentos/` | Lista documentos del trámite. | `IsAuthenticated` |
| `DELETE /<slug>/<pk>/documentos/<doc_id>/` | Elimina un documento del trámite. | `IsAuthenticated` |
| `GET /<slug>/<pk>/requisitos/` | Requisitos documentales del estado actual + cumplimiento. | `IsAuthenticated` |
```

- [ ] **Step 2: Añadir entrada al `CHANGELOG.md`**

```markdown
### Added
- Endpoints de carga y validación de documentos: `POST/GET /<slug>/<pk>/documentos/`,
  `DELETE /<slug>/<pk>/documentos/<doc_id>/` y `GET /<slug>/<pk>/requisitos/`.
  `/requisitos/` consume el mecanismo público `WorkflowEngine.evaluar_requisitos_documentales`
  (sin duplicar lógica con el engine). Requiere `sinpapel` con el campo
  `InstanciaDocumento.archivo` y dicho método (>= v0.6.0).
```

- [ ] **Step 3: Commit**

```bash
git add README.md README.es.md CHANGELOG.md
git commit -m "docs: documentar endpoints de documentos + requisitos"
```

---

## Notas de verificación local (opcional)

El workspace aislado de sinpapel-drf no corre la suite (necesita el host creditos).
Para smoke local sin creditos, reusar el patrón del harness autocontenido
(`/tmp/sp_verify/`): settings en memoria + app `verifyapp` con un modelo
`@workflow_enabled` + `APIRequestFactory`. Útil para validar el wiring de las
acciones antes de correr la suite completa en el host.
