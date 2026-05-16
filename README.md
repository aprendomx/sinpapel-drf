# sinpapel-drf

> **alpha v0.1.0** — DRF HTTP layer for [sinpapel](../sinpapel/README.md).
>
> Auto-generated REST endpoints (workflow + signature + flow portability) on top of `@workflow_enabled` Django models. Reusable across SEP, FONDESO y cualquier consumer de sinpapel que necesite **HTTP API funcional sin escribir ViewSets, serializers, URLs ni permission classes a mano**.

---

## Table of Contents

1. [What is sinpapel-drf?](#1-what-is-sinpapel-drf)
2. [Installation](#2-installation)
3. [Settings](#3-settings)
4. [Quickstart (5 min)](#4-quickstart-5-min)
5. [Workflow endpoints](#5-workflow-endpoints)
6. [Signature backends + dual mode FIEL](#6-signature-backends--dual-mode-fiel)
7. [Permissions](#7-permissions)
8. [Flow portability endpoints](#8-flow-portability-endpoints)
9. [Security checklist (ADR-012)](#9-security-checklist-adr-012)
10. [Testing](#10-testing)
11. [Known limitations + Roadmap](#11-known-limitations--roadmap)
12. [License](#12-license)
13. [Contributing](#13-contributing)

---

## 1. What is sinpapel-drf?

`sinpapel-drf` es la capa HTTP **opt-in** sobre `sinpapel` core. Provee tres capacidades:

- **Auto-generated workflow endpoints**: `@workflow_enabled(expose_endpoints=True)` registra el modelo en `SinpapelRouter` — 3 endpoints REST por modelo decorado (`available-transitions`, `transition`, `history`).
- **Polymorphic signature dispatch**: `SignatureRequestSerializer` discrimina por `(backend, mode)` — soporte para FIEL dual mode (client-side default + server-side opt-in), Manual y Fake backends desde el mismo endpoint `POST /transition/`.
- **Flow portability**: 2 endpoints admin-only (`GET /flujos/<pk>/export/` + `POST /flujos/import/`) que serializan/deserializan `VersionFlujo` con sus transiciones + requisitos (schema v0.1) — útil para deploy de configuración cross-environment.

**Cero acoplamiento `sinpapel` core → DRF**: futuros HTTP adapters (`sinpapel-graphene`, `sinpapel-fastapi`) son opcionales. Ver [ADR-010](../dev/decisions/adr-010-two-package-split-sinpapel-drf.md).

---

## 2. Installation

`sinpapel-drf` aún no está en PyPI público. Instala desde Git mientras la API se estabiliza. **Requires `sinpapel >=0.1.0,<0.2`** + `djangorestframework>=3.14` ya instalados:

```bash
# Install sinpapel core first (see ../sinpapel/README.md)
pip install "git+ssh://git@github.com/jadrians/creditos.git#subdirectory=sinpapel"

# Then sinpapel-drf
pip install "git+ssh://git@github.com/jadrians/creditos.git#subdirectory=sinpapel_drf"
```

**Optional extras:**

```bash
pip install "sinpapel-drf[openapi]"   # adds drf-spectacular for schema generation
pip install "sinpapel-drf[dev]"       # pytest, pytest-django for testing
```

**Python:** `>=3.13`. **Django:** `>=5.0`. **DRF:** `>=3.14`.

---

## 3. Settings

Agrega `rest_framework` y `sinpapel_drf` a `INSTALLED_APPS` **después de** `sinpapel` y tu app de dominio (orden importa para `WorkflowRegistry` discovery):

```python
# settings.py
INSTALLED_APPS = [
    # ... django.contrib.* ...
    "simple_history",
    "trazable",
    "sinpapel",
    "tu_app",            # tu app con @workflow_enabled models
    "rest_framework",
    "sinpapel_drf",      # debe cargar DESPUÉS de tu app
]
```

Configura DRF auth + permissions globales (sinpapel-drf reusa los defaults DRF):

```python
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}
```

**Cache layer settings** (heredados de `sinpapel`):

```python
SINPAPEL_CACHE_ALIAS = "default"   # default django.core.cache alias
SINPAPEL_CACHE_TIMEOUT = 300       # seconds, default 300
```

**Server-side signing setting** (gated, see §9):

```python
# DEFAULT False — modo B requires legal review
SINPAPEL_ALLOW_SERVER_SIGNING = False
```

**Optional drf-spectacular config** (para `[openapi]` extra):

```python
INSTALLED_APPS += ["drf_spectacular"]
REST_FRAMEWORK["DEFAULT_SCHEMA_CLASS"] = "drf_spectacular.openapi.AutoSchema"

SPECTACULAR_SETTINGS = {
    "TITLE": "sinpapel-drf API",
    "VERSION": "0.1.0",
}
```

Incluye los URLs de `sinpapel_drf` en tu `urls.py` raíz:

```python
# urls.py
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("sinpapel/api/", include("sinpapel_drf.urls")),
    # ... your other urls ...
]
```

---

## 4. Quickstart (5 min)

Decora tu modelo de dominio con `expose_endpoints=True`:

```python
# tu_app/models.py
from django.db import models
from sinpapel.decorators import workflow_enabled


@workflow_enabled(
    state_field="estado",
    workflow_key="tramite",
    expose_endpoints=True,           # ← activa los endpoints REST
    endpoint_slug="tramites",        # ← opcional; default = workflow_key
)
class Tramite(models.Model):
    folio = models.CharField(max_length=100, unique=True)
    estado = models.ForeignKey(
        "sinpapel.Estado",
        on_delete=models.CASCADE,
        null=True,
    )
```

Después de migrations + admin setup (ver `sinpapel/README.md` §4-§7), tres endpoints están disponibles automáticamente:

```
GET  /sinpapel/api/tramites/<pk>/available-transitions/
POST /sinpapel/api/tramites/<pk>/transition/
GET  /sinpapel/api/tramites/<pk>/history/
```

Plus 2 endpoints admin-only para portabilidad de flujos:

```
GET  /sinpapel/api/flujos/<pk>/export/
POST /sinpapel/api/flujos/import/
```

Verificación rápida en shell:

```python
>>> from django.urls import reverse
>>> reverse("tramite-available-transitions", args=[42])
'/sinpapel/api/tramites/42/available-transitions/'
```

---

## 5. Workflow endpoints

### `GET /<slug>/<pk>/available-transitions/`

Lista los `Estado` destino válidos desde el estado actual del modelo. Devuelve `[]` si no hay estado o no hay transiciones configuradas.

**Request:**

```bash
curl https://api.example.com/sinpapel/api/tramites/42/available-transitions/ \
  -H "Authorization: Bearer <token>"
```

**Response 200:**

```json
[
  {"id": 5, "nombre": "EN_REVISION", "color": "#abc123"},
  {"id": 6, "nombre": "RECHAZADO", "color": "#fcc"}
]
```

**Auth:** `IsAuthenticated` (default). El motor `puede_cambiar_estado` filtra granularmente por `grupos_permitidos` per-transition (ver §7).

### `POST /<slug>/<pk>/transition/`

Ejecuta la transición al `target_state` indicado. Soporta firma electrónica polimórfica (ver §6). Atomic: side-effects se ejecutan post-commit.

**Request (modo A, JSON):**

```bash
curl -X POST https://api.example.com/sinpapel/api/tramites/42/transition/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "target_state": "EN_REVISION",
    "comentarios": "Documentación completa",
    "monto_aprobado": "150000.00"
  }'
```

**Response 201:**

```json
{
  "success": true,
  "instance_id": 42,
  "estado_anterior": "CAPTURA",
  "estado_nuevo": "EN_REVISION",
  "seguimiento_id": 99
}
```

**Errores:**

- `400 Bad Request` — validation falla (target_state ausente, signature inválida).
- `403 Forbidden` — `PermissionError` del engine (target inexistente, transición no permitida, usuario sin grupo permitido).
- `401 Unauthorized` — sin auth.

### `GET /<slug>/<pk>/history/`

Audit trail del modelo vía [django-simple-history](https://django-simple-history.readthedocs.io/). Paginado con `PageNumberPagination` (default 10 por página, max 100).

**Request:**

```bash
curl "https://api.example.com/sinpapel/api/tramites/42/history/?page=1&page_size=20" \
  -H "Authorization: Bearer <token>"
```

**Response 200:**

```json
{
  "count": 45,
  "next": "https://.../history/?page=2&page_size=20",
  "previous": null,
  "results": [
    {
      "history_id": 12,
      "history_type": "+",
      "history_date": "2026-04-29T18:00:00Z",
      "history_user": "admin@example.com",
      "history_change_reason": "Initial creation"
    }
  ]
}
```

---

## 6. Signature backends + dual mode FIEL

`sinpapel-drf` soporta cuatro backends desde el mismo endpoint `POST /transition/` vía `SignatureRequestSerializer` polimórfico:

| Backend | Mode | Body shape |
|---------|------|------------|
| `fiel` | `client-side` (default) | JSON con `firma_b64` + `certificado_cer_b64` |
| `fiel` | `server-side` (gated) | multipart con `cer_file` + `key_file` + `password` |
| `manual` | n/a | JSON con `scanned_image_path` + `witness_name` |
| `fake` | n/a | JSON sin kwargs (tests only) |

### Modo A — FIEL client-side (default seguro, recommended SAT)

El cliente firma localmente (browser via Web Crypto API o app nativa) y envía solo la firma + certificado. La clave privada **NUNCA** cruza la red.

```bash
curl -X POST https://api.example.com/sinpapel/api/tramites/42/transition/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "target_state": "FIRMADO",
    "comentarios": "Aprobado por jefatura",
    "signature": {
      "backend": "fiel",
      "mode": "client-side",
      "firma_b64": "<base64 de firma RSA-SHA256>",
      "certificado_cer_b64": "<base64 del .cer X.509 DER>"
    }
  }'
```

### Modo B — FIEL server-side (opt-in, requires legal review)

⚠️ **Solo válido si `SINPAPEL_ALLOW_SERVER_SIGNING=True`** (ver §9 Security Checklist).

Cliente sube `cer_file` + `key_file` + `password` vía `multipart/form-data`. Servidor descifra `.key` con password en memoria, firma RSA-SHA256, y descarta la key vía `del + gc.collect()` en `finally`.

```bash
curl -X POST https://api.example.com/sinpapel/api/tramites/42/transition/ \
  -H "Authorization: Bearer <token>" \
  -F "target_state=FIRMADO" \
  -F "comentarios=Firma institucional" \
  -F "signature.backend=fiel" \
  -F "signature.mode=server-side" \
  -F "signature.cer_file=@/path/to/cert.cer" \
  -F "signature.key_file=@/path/to/cert.key" \
  -F "signature.password=mi-password-fiel"
```

Si `SINPAPEL_ALLOW_SERVER_SIGNING=False` (default), el endpoint retorna 400:

```json
{
  "signature": {
    "mode": [
      "Server-side signing is disabled. Set SINPAPEL_ALLOW_SERVER_SIGNING=True (with legal review)."
    ]
  }
}
```

### Modo Manual

Para flujos donde la firma se captura en papel y se digitaliza:

```json
{
  "target_state": "FIRMADO",
  "signature": {
    "backend": "manual",
    "scanned_image_path": "/uploads/firmas/2026-04-29-tramite-42.png",
    "witness_name": "Lic. Pérez"
  }
}
```

### Modo Fake

Solo para tests:

```json
{
  "target_state": "FIRMADO",
  "signature": {"backend": "fake"}
}
```

Ver [ADR-012](../dev/decisions/adr-012-fiel-dual-mode-signing.md) para discusión completa de trade-offs y security checklist.

---

## 7. Permissions

`sinpapel-drf` adopta una postura **engine-driven** para permisos, no DRF permission classes custom:

- **`IsAuthenticated`** es el único permission class default — DRF rechaza unauthenticated requests con 401/403.
- **`grupos_permitidos`** se enforce dentro de `WorkflowEngine.puede_cambiar_estado()` per-transition. Si el user no pertenece a ningún grupo en `ConfiguracionTransicion.grupos_permitidos`, el engine raise `PermissionError`.
- **`PermissionError → 403`** mapping en el ViewSet (S13.5 D3 pattern).

```python
# sinpapel/services/workflow_engine.py
def puede_cambiar_estado(instance, target_state_name, user):
    # ... validations ...
    grupos_requeridos = config_transicion.grupos_permitidos.values_list("name", flat=True)
    if grupos_requeridos and not user.groups.filter(name__in=grupos_requeridos).exists():
        return False, "No tiene permisos para realizar esta acción"
    return True, "OK"
```

**Why no custom DRF permission?** KISS + single source of truth. Engine ya consume `get_transitions_for` cache helper (S13.1+S13.2). Duplicar lógica en una `GruposPermitidosPermission` class violaría el Value Preservation Gate (PAT-E-572).

**Para flow portability endpoints** (§8): permission distinto — `IsAdminUser` (`is_staff=True`).

---

## 8. Flow portability endpoints

Endpoints admin-only para deploy de configuración cross-environment. Reusan el schema v0.1 de [sinpapel core management commands](../sinpapel/README.md) (`sinpapel_export_flujo`, `sinpapel_import_flujo`).

### `GET /sinpapel/api/flujos/<pk>/export/`

Descarga JSON portable de un `VersionFlujo` (incluye transiciones + grupos + requisitos por nombre, NO PKs).

**Request:**

```bash
curl https://api.example.com/sinpapel/api/flujos/42/export/ \
  -H "Authorization: Bearer <admin-token>" \
  -o flujo_42.json
```

**Response 200:** `Content-Disposition: attachment; filename="flujo_<nombre>_<timestamp>.json"`

```json
{
  "schema_version": "0.1",
  "exported_at": "2026-04-29T18:00:00Z",
  "flujo": {
    "nombre": "REQUISITOS_FOVISSSTE_v3",
    "descripcion": "Flujo principal FOVISSSTE",
    "activo": true,
    "metadatos": {"positions": {"1": {"x": 100, "y": 200}}},
    "transiciones": [
      {
        "estado_origen": "CAPTURA",
        "estado_destino": "EN_REVISION",
        "grupos_permitidos": ["Asistente_Tecnico", "Jefe_Modulo"]
      }
    ],
    "requisitos": [
      {
        "estado": "CAPTURA",
        "tipo_documento": "INE",
        "porcentaje": 100,
        "auto_carga": false
      }
    ]
  }
}
```

### `POST /sinpapel/api/flujos/import/`

Crea un nuevo `VersionFlujo` desde JSON. Atomic + reject-on-missing (PAT-E-523):

```bash
curl -X POST https://api.example.com/sinpapel/api/flujos/import/ \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d @flujo.json
```

**Response 201 (success):**

```json
{
  "id": 99,
  "nombre": "FLUJO_NEW",
  "activo": false,
  "transiciones_count": 5,
  "requisitos_count": 8
}
```

**Response 400 (missing entities):**

```json
{
  "detail": "Missing entities in destination:\n  - Estado: ['EN_VALIDACION_X']\n  - TipoDocumento: ['CONSTANCIA_CURP']\n\nTotal missing: 2 entities\nAction required: create them in destination, then retry import."
}
```

**Query params opcionales:**

- `?dry_run=true` — valida sin persistir, retorna 200 con `{"dry_run": true, "would_create": {...}}`.
- `?activo=true` — override safe default `activo=False`.

**Defensive defaults:**

- `activo=False` — evita activación accidental en producción.
- PKs siempre auto-generados — no preservación cross-environment.
- Reject explícito si missing entities, duplicate flujo nombre, schema version mismatch, ambiguity (`Catalogo.nombre` NOT unique).

Ver `sinpapel/schemas/flujo_export.py` (schema v0.1).

---

## 8b. Endpoints v0.2.0

Adicionales que expone v0.2.0 sobre las 5 features nuevas de `sinpapel` v0.4.0
(predicados de transición, captura de metadatos, Serializer Factory, SLAs, preview).

### Preview transition (no mutation)

`POST /<slug>/<pk>/preview-transition/` — simula la transición y retorna un reporte
de impacto. NO ejecuta side-effects, NO firma, NO muta la instancia ni el historial.

```bash
curl -X POST -H "Authorization: Token ..." \
     -H "Content-Type: application/json" \
     -d '{"target_state": "Aprobado"}' \
     https://host/sinpapel/api/solicitudes/42/preview-transition/
```

Response 200:

```json
{
  "permitido": true,
  "razones_bloqueo": [],
  "documentos_faltantes": [],
  "predicados_fallidos": [],
  "aprobadores_requeridos": [],
  "side_effects": [],
  "historial_reciente": [{"fecha": "...", "transicion": "Borrador → Revisión",
                          "usuario": "alice", "comentarios": "..."}]
}
```

Si `permitido=false`, `razones_bloqueo` incluye al menos un objeto `{tipo, mensaje}`
con `tipo ∈ {estado, transicion, documento, permiso, predicado}`. Permission:
`IsAuthenticated`.

### Metadatos (read + partial update)

`GET /<slug>/<pk>/metadatos/` — retorna `{schema, values}` para modelos que heredan
`MetadatosCapturables`. El schema se construye desde `SCHEMA_METADATOS`.

```bash
curl https://host/sinpapel/api/solicitudes/42/metadatos/
```

```json
{
  "schema": [
    {"nombre": "rfc", "tipo": "str", "requerido": true,
     "default": null, "choices": null, "etiqueta": "RFC", "ayuda": ""}
  ],
  "values": {"rfc": "ABCD010101ABC"}
}
```

`PATCH /<slug>/<pk>/metadatos/` — update parcial. Valida con un Serializer DRF
construido dinámicamente vía `MetaFormFactory.build_serializer()`, cacheado por
modelo. Rechaza keys fuera del schema con 400.

```bash
curl -X PATCH -H "Content-Type: application/json" \
     -d '{"rfc": "ABCD010101ABC"}' \
     https://host/sinpapel/api/solicitudes/42/metadatos/
```

Permission: `IsAuthenticated`.

### Predicados de transición (admin CRUD)

`CondicionTransicion` se gestiona como ModelViewSet:

```bash
# List + filter
curl https://host/sinpapel/api/condiciones/?transicion=7&activo=true

# Create
curl -X POST -H "Content-Type: application/json" \
     -d '{"transicion": 7, "tipo": "json_logic",
          "configuracion": {"logic": {">": [{"var": "monto"}, 0]}},
          "mensaje_error": "Monto inválido", "orden": 1, "activo": true}' \
     https://host/sinpapel/api/condiciones/

# Update / Delete
curl -X PATCH -d '{"activo": false}' https://host/sinpapel/api/condiciones/123/
curl -X DELETE https://host/sinpapel/api/condiciones/123/
```

`tipo` admite `python_path`, `json_logic`, `django_orm`. Permission: `IsAdminUser`.

### SLAs (admin CRUD + verificación)

`SLAConfiguracion` (timers por estado) se gestiona como ModelViewSet:

```bash
# List + filter
curl https://host/sinpapel/api/slas/?estado=3

# Create
curl -X POST -H "Content-Type: application/json" \
     -d '{"estado": 3, "dias_maximos": 7,
          "accion_vencimiento": "notificar",
          "configuracion_accion": {"grupo_id": 1, "template": "vence.html"}}' \
     https://host/sinpapel/api/slas/

# Mass verification (equiv. management command)
curl -X POST https://host/sinpapel/api/slas/verificar/
# → 200 {"ejecutadas": {"notificar": 3, "escalar": 1}}

# Per-instance evaluation (may mutate via 'alertar' action)
curl -X POST https://host/sinpapel/api/solicitudes/42/sla-status/
# → 200 [] | 200 [{"accion": "notificar", ...}]
```

`accion_vencimiento` admite `notificar`, `escalar`, `rechazar`, `alertar`.
Permission: `IsAdminUser` (CRUD + verificar + sla-status).

### Resumen de permisos v0.2.0

| Endpoint | Permission |
|---|---|
| `preview-transition` | `IsAuthenticated` |
| `metadatos` (GET/PATCH) | `IsAuthenticated` |
| `sla-status` | `IsAdminUser` (puede mutar) |
| `condiciones/*` | `IsAdminUser` |
| `slas/*` + `slas/verificar/` | `IsAdminUser` |

---

## 9. Security checklist (ADR-012)

Implementation status del checklist completo de [ADR-012](../dev/decisions/adr-012-fiel-dual-mode-signing.md):

| Item | Status | Notas |
|------|:------:|-------|
| `SINPAPEL_ALLOW_SERVER_SIGNING=False` default | ✅ | Modo B opt-in only via setting explícito |
| `key_file` + `password` `write_only=True` | ✅ | No leakean en response (DRF serializer field config) |
| `del key_bytes; del password; gc.collect()` en finally | ✅ | `_with_secure_key_buffer` context manager garantiza cleanup en exception paths |
| Logging conservador (no leak password/key) | ✅ | Tests con `caplog` verifican no aparición de passwords/key bytes |
| Audit `RegistroFirma.backend_metadata.mode="server-side"` | ✅ | Para reporting/forensics post-incidente |
| Tests E2E ambos modos + setting on/off | ✅ | 28+ tests E2E en S13.6 |
| Rate limiting modo B (`UserRateThrottle`) | ⏸️ | **DEFER a story sucesora** — requires throttle config dedicado |
| HTTPS-only producción | ⚠️ | **User responsibility** — configura `SECURE_SSL_REDIRECT=True` + `SECURE_PROXY_SSL_HEADER` en Django settings |

⚠️ **Antes de habilitar modo B en producción:**

1. **Revisión legal** — el server gestiona claves privadas; incumple SAT best practice "client-side only" del firmante.
2. **Logging filter** — verifica que tu pipeline (Sentry, ELK, etc.) NO capture request bodies de modo B endpoints.
3. **Rate limiting** — implementa throttle agresivo (`UserRateThrottle("10/min")` recomendado).
4. **Audit trail** — confirma que `RegistroFirma.backend_metadata.mode` está incluido en exports auditables.
5. **HTTPS strict** — `SECURE_SSL_REDIRECT=True`, HSTS header, `SECURE_PROXY_SSL_HEADER` para detrás de proxy.

---

## 10. Testing

`sinpapel-drf` viene con `[dev]` extra para testing:

```bash
pip install "sinpapel-drf[dev]"
```

**Ejecutar suite default** (excluye smoke tests slow):

```bash
DJANGO_SETTINGS_MODULE=mossc.settings pytest sinpapel_drf/
```

**Ejecutar smoke E2E install** (manual only, requires `uv` en PATH):

```bash
DJANGO_SETTINGS_MODULE=mossc.settings pytest sinpapel_drf/tests/test_install_smoke.py -m install_smoke -v
```

**Test patterns establecidos:**

```python
from rest_framework.test import APIClient

@pytest.fixture
def api_client_authenticated(admin_user, settings):
    client = APIClient()
    client.force_authenticate(user=admin_user)  # works con JWT + Session auth
    yield client


@pytest.mark.django_db(transaction=True)   # required para signal/on_commit flow
def test_transition_flow(api_client_authenticated, solicitud):
    resp = api_client_authenticated.post(
        f"/sinpapel/api/tramites/{solicitud.pk}/transition/",
        data={"target_state": "EN_REVISION"},
        format="json",
    )
    assert resp.status_code == 201
```

`sinpapel-drf` provee 80+ tests cubriendo: workflow endpoints, signature dispatch (4 backends + dual mode), permission flows, flow portability, security caplog (no leak), atomic rollback.

---

## 11. Known limitations + Roadmap

### Known limitations

- **drf-spectacular schema con discriminated union**: warnings esperados al generar OpenAPI con `SignatureRequestSerializer` polimórfico. Schema funcional pero shape no perfecto. Defer fix a story sucesora.
- **Rate limiting modo B**: no implementado. **User responsibility** habilitar `UserRateThrottle` agresivo en producción si activa `SINPAPEL_ALLOW_SERVER_SIGNING=True`.
- **No API versioning** (`/v1/`, `/v2/`): pre-1.0 path único `/sinpapel/api/`. Versioning llega post-1.0.
- **HTTPS-only enforcement**: solo documentado, no code-level. User responsibility.
- **Migration desde `WorkflowService` legacy**: 12 callers en `creditos/views.py` no migrados aún. Story sucesora post-E13.
- **No deployment guide**: Docker/K8s setup es consumer-specific.

### Roadmap

- **drf-spectacular polish** (post-E13): fix discriminated union schema warnings.
- **Rate limiting modo B**: built-in `UserRateThrottle` config opcional via setting.
- **API versioning**: `/sinpapel/api/v1/` path una vez API estabilizada (1.0).
- **PyPI público**: post-1.0 con tag stable + traducción del README a inglés.
- **Adapter graphene/fastapi**: solo si surge demanda real.

---

## 12. License

MIT — see [LICENSE](LICENSE).

`sinpapel-drf` se desarrolla en el monorepo [creditos](https://github.com/jadrians/creditos) y es distribuido como subdirectory hasta PyPI público.

---

## 13. Contributing

Issues + PRs welcome en https://github.com/jadrians/creditos/issues. Tag con `area/sinpapel-drf`.

**Architecture decisions:**

- [ADR-010 — Two-package split sinpapel + sinpapel-drf](../dev/decisions/adr-010-two-package-split-sinpapel-drf.md)
- [ADR-011 — Cache layer en sinpapel core](../dev/decisions/adr-011-cache-layer-sinpapel-core.md)
- [ADR-012 — FIEL dual mode signing](../dev/decisions/adr-012-fiel-dual-mode-signing.md)

**Related docs:**

- `sinpapel/README.md` — engine core (workflow + signature + audit)
- `sinpapel/schemas/flujo_export.py` — flow portability schema v0.1
- `work/epics/e13-sinpapel-http/scope.md` — E13 epic scope + retrospective patterns
