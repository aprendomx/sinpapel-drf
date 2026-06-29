# sinpapel-drf

> **v0.4.0** — DRF HTTP layer for [sinpapel](https://github.com/aprendomx/sinpapel).
>
> Auto-generated REST endpoints (workflow + signature + metadata + predicates + SLA + preview + flow portability) on top of `@workflow_enabled` Django models. Reusable across SEP, FONDESO, and any sinpapel consumer that needs **a functional HTTP API without hand-writing ViewSets, serializers, URLs, or permission classes**.
>
> [🇪🇸 Leer en Español](README.es.md)

---

## Table of Contents

1. [What is sinpapel-drf?](#1-what-is-sinpapel-drf)
2. [Installation](#2-installation)
3. [Settings](#3-settings)
4. [Quickstart](#4-quickstart)
5. [Workflow endpoints](#5-workflow-endpoints)
6. [Signature backends + dual FIEL mode](#6-signature-backends--dual-fiel-mode)
7. [Admin endpoints (predicates + SLAs)](#7-admin-endpoints-predicates--slas)
8. [Flow portability endpoints](#8-flow-portability-endpoints)
9. [Permissions](#9-permissions)
10. [Security checklist](#10-security-checklist)
11. [Testing](#11-testing)
12. [Known limitations & Roadmap](#12-known-limitations--roadmap)
13. [License & Contributing](#13-license--contributing)

---

## 1. What is sinpapel-drf?

`sinpapel-drf` is the **HTTP layer** of [sinpapel](https://github.com/aprendomx/sinpapel) (workflow + audit + signature engine).

For every Django model decorated with `@workflow_enabled(expose_endpoints=True)`, sinpapel-drf auto-publishes:

| Endpoint | Verb | Purpose |
|---|---|---|
| `/<slug>/<pk>/available-transitions/` | GET | List valid target states from current state |
| `/<slug>/<pk>/transition/` | POST | Execute a transition (with optional signature) |
| `/<slug>/<pk>/history/` | GET | Paginated audit trail (`django-simple-history`) |
| `/<slug>/<pk>/preview-transition/` | POST | **v0.2.0** — Impact report without mutation |
| `/<slug>/<pk>/metadatos/` | GET / PATCH | **v0.2.0** — Structured metadata schema + partial update |
| `/<slug>/<pk>/sla-status/` | POST | **v0.2.0** — Evaluate SLA per instance |
| `/<slug>/<pk>/documentos/` | GET / POST | **v0.3.0** — List / upload documents (`InstanciaDocumento`, multipart) |
| `/<slug>/<pk>/documentos/<doc_id>/` | DELETE | **v0.3.0** — Remove a document from the instance |
| `/<slug>/<pk>/requisitos/` | GET | **v0.3.0** — Document requirements of the current state + fulfillment. **v0.4.0**: each `requisito_documento` also carries `tipo_documento_id` + `documentos_disponibles` (`[{id, nombre}]`) for dependent client selects |

Plus admin-scoped top-level resources:

| Endpoint | Verb | Purpose |
|---|---|---|
| `/condiciones/` | CRUD | **v0.2.0** — Transition predicates (`CondicionTransicion`) |
| `/slas/` | CRUD | **v0.2.0** — State timers (`SLAConfiguracion`) |
| `/slas/verificar/` | POST | **v0.2.0** — Bulk SLA evaluation across instances |
| `/flujos/<pk>/export/` | GET | Flow as portable JSON |
| `/flujos/import/` | POST | Import a flow JSON into a new `VersionFlujo` |

**Design pillars:**

- **Zero boilerplate in the consumer.** No ViewSets, no serializers, no URL definitions. Just decorate the model.
- **Polymorphic signature dispatch.** A single `POST /transition/` endpoint accepts FIEL client-side (recommended), FIEL server-side (gated), manual, or fake signatures.
- **Dynamic serializers for metadata.** `MetaFormFactory.build_serializer()` constructs DRF serializers at request time from `SCHEMA_METADATOS`; cached per model with `functools.lru_cache`.
- **Error mapping consistency.** `PermissionError → 403`, `ValueError → 400`, `SignatureValidationError → 400`, `DjangoValidationError → 400`.

---

## 2. Installation

```bash
pip install "sinpapel-drf @ git+ssh://git@github.com/aprendomx/sinpapel-drf.git@v0.4.0"
```

Or via `pyproject.toml`:

```toml
dependencies = [
    "sinpapel-drf @ git+ssh://git@github.com/aprendomx/sinpapel-drf.git@v0.4.0",
]
```

Transitively pulls `sinpapel @v0.7.0`. Requires Python 3.10+, Django 5.0+, DRF 3.14+.

### Add to `INSTALLED_APPS`

```python
# settings.py
INSTALLED_APPS = [
    # ...
    "sinpapel",
    "sinpapel_drf",
    # ...
]
```

### Mount the URLs

```python
# project/urls.py
from django.urls import include, path

urlpatterns = [
    path("sinpapel/api/", include("sinpapel_drf.urls")),
]
```

`sinpapel_drf.urls` exposes:

- The dynamic `SinpapelRouter` (per-model actions) for every `@workflow_enabled(expose_endpoints=True)` registered model.
- A `DefaultRouter` for the admin resources `/condiciones/` and `/slas/`.
- The `/flujos/<pk>/export/` and `/flujos/import/` endpoints.

---

## 3. Settings

| Setting | Default | Purpose |
|---|---|---|
| `SINPAPEL_ALLOW_SERVER_SIGNING` | `False` | Enable FIEL server-side mode (uploaded `.key` + password). **Requires legal review** — see ADR-012. |
| `REST_FRAMEWORK.DEFAULT_AUTHENTICATION_CLASSES` | — | Standard DRF auth (Token, JWT, Session, etc.) |

The package does not impose authentication. The consumer chooses (Session, Token, JWT, etc.) via the standard DRF setting.

---

## 4. Quickstart

### 1. Decorate the model

```python
# myapp/models.py
from django.db import models
from sinpapel import workflow_enabled
from sinpapel.mixins import CampoMetadato, MetadatosCapturables

@workflow_enabled(
    state_field="estado",
    expose_endpoints=True,
    endpoint_slug="tramites",
)
class Tramite(MetadatosCapturables, models.Model):
    estado = models.ForeignKey("sinpapel.Estado", on_delete=models.PROTECT)
    monto = models.DecimalField(max_digits=12, decimal_places=2)

    SCHEMA_METADATOS = [
        CampoMetadato(nombre="rfc", tipo=str, requerido=True, etiqueta="RFC"),
        CampoMetadato(nombre="nivel", tipo=str, choices=["A", "B", "C"]),
    ]
```

### 2. Seed `Estado` + `ConfiguracionTransicion` (Django admin, fixture, or migration)

### 3. Call the endpoints

```bash
# List available transitions
curl -H "Authorization: Token <…>" \
     https://host/sinpapel/api/tramites/42/available-transitions/

# Preview a transition without mutating
curl -X POST -H "Authorization: Token <…>" \
     -H "Content-Type: application/json" \
     -d '{"target_state": "Aprobado"}' \
     https://host/sinpapel/api/tramites/42/preview-transition/

# Execute the transition
curl -X POST -H "Authorization: Token <…>" \
     -H "Content-Type: application/json" \
     -d '{"target_state": "Aprobado", "comentarios": "OK"}' \
     https://host/sinpapel/api/tramites/42/transition/
```

---

## 5. Workflow endpoints

Per-instance, auto-registered via `SinpapelRouter`. All require `IsAuthenticated` by default.

### `GET .../available-transitions/`

Returns the list of valid target `Estado` objects from the current state.

```json
[
  {"id": 5, "nombre": "Aprobado", "color": "#4DEFE2"},
  {"id": 7, "nombre": "Rechazado", "color": "#FF0000"}
]
```

### `POST .../transition/`

Executes a transition. Request body validated by `TransitionRequestSerializer`:

```json
{
  "target_state": "Aprobado",
  "comentarios": "Documentation complete",
  "condiciones": null,
  "signature": { "backend": "fiel", "mode": "client-side", "firma_b64": "...", "certificado_cer_b64": "..." }
}
```

Response 201:

```json
{
  "success": true,
  "instance_id": 42,
  "estado_anterior": "Revisión",
  "estado_nuevo": "Aprobado",
  "seguimiento_id": 1834
}
```

### `GET .../history/`

Paginated audit trail (`page_size=10`, max `100`):

```json
{
  "count": 12,
  "next": "...page=2",
  "previous": null,
  "results": [
    {"history_id": 1834, "history_type": "~", "history_date": "...", "history_user": "alice", "history_change_reason": "..."}
  ]
}
```

### `POST .../preview-transition/` *(v0.2.0)*

Simulates a transition and returns an impact report. **Does not mutate state, does not execute side-effects, does not sign anything.**

```bash
curl -X POST -d '{"target_state": "Aprobado"}' .../preview-transition/
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
  "historial_reciente": [{"fecha": "...", "transicion": "Borrador → Revisión", "usuario": "alice", "comentarios": "..."}]
}
```

If `permitido` is `false`, `razones_bloqueo` contains at least one `{tipo, mensaje}` object with `tipo ∈ {estado, transicion, documento, permiso, predicado}`.

### `GET / PATCH .../metadatos/` *(v0.2.0)*

For models inheriting `MetadatosCapturables`:

**GET** returns the schema + current values:

```json
{
  "schema": [
    {"nombre": "rfc", "tipo": "str", "requerido": true, "default": null,
     "choices": null, "etiqueta": "RFC", "ayuda": ""}
  ],
  "values": {"rfc": "ABCD010101ABC"}
}
```

**PATCH** validates the partial update through a DRF serializer built dynamically with `MetaFormFactory.build_serializer()` (cached per model). Keys outside `SCHEMA_METADATOS` are rejected with 400.

```bash
curl -X PATCH -d '{"rfc": "ABCD010101ABC"}' .../metadatos/
```

### `POST .../sla-status/` *(v0.2.0)*

Evaluates SLA for a specific instance via `SLAEngine.evaluar_instancia()`. **POST** because the `alertar` action can mutate instance fields. Returns the list of actions executed (or `[]` if no SLA is active or none have expired).

Requires `IsAdminUser`.

---

## 6. Signature backends + dual FIEL mode

`POST /transition/` accepts an optional `signature` body discriminated by `(backend, mode)`. Four variants, validated by `SignatureRequestSerializer.to_internal_value()`.

### Mode A — FIEL client-side (recommended, default)

Client signs locally with the SAT-supplied tools (e.g. `firma.gob.mx` or local libraries). The server **never sees** the private key.

```json
{
  "signature": {
    "backend": "fiel",
    "mode": "client-side",
    "firma_b64": "...",
    "certificado_cer_b64": "..."
  }
}
```

### Mode B — FIEL server-side (gated)

Server receives `.cer` + `.key` + `password` via multipart and signs internally. **Requires `SINPAPEL_ALLOW_SERVER_SIGNING=True`** and legal review (ADR-012).

```bash
curl -X POST \
     -F "target_state=Aprobado" \
     -F "signature[backend]=fiel" \
     -F "signature[mode]=server-side" \
     -F "signature[cer_file]=@firma.cer" \
     -F "signature[key_file]=@firma.key" \
     -F "signature[password]=••••" \
     .../transition/
```

After signing, the key bytes are scrubbed via `_with_secure_key_buffer` (`del` + `gc.collect()` in `finally`).

### Manual

Scanned-signature workflow with witness.

```json
{
  "signature": {
    "backend": "manual",
    "scanned_image_path": "/media/firmas/123.png",
    "witness_name": "Juan Pérez"
  }
}
```

### Fake (tests only)

```json
{ "signature": { "backend": "fake" } }
```

---

## 7. Admin endpoints (predicates + SLAs)

Both ModelViewSets. **All routes require `IsAdminUser`** (`is_staff=True`).

### `CondicionTransicion` CRUD — transition predicates

A predicate runs before the transition is permitted. Three backends are supported: `python_path`, `json_logic`, `django_orm`.

```bash
# List + filter
curl ".../condiciones/?transicion=7&activo=true"

# Create
curl -X POST -H "Content-Type: application/json" \
     -d '{
       "transicion": 7,
       "tipo": "json_logic",
       "configuracion": {"logic": {">": [{"var": "monto"}, 0]}},
       "mensaje_error": "Amount must be positive",
       "orden": 1,
       "activo": true
     }' \
     .../condiciones/

# Update / Delete
curl -X PATCH -d '{"activo": false}' .../condiciones/123/
curl -X DELETE .../condiciones/123/
```

### `SLAConfiguracion` CRUD — state timers

A SLA defines a max-days-in-state limit and the action to execute on expiry. Actions: `notificar`, `escalar`, `rechazar`, `alertar`.

```bash
# List + filter
curl ".../slas/?estado=3"

# Create
curl -X POST -H "Content-Type: application/json" \
     -d '{
       "estado": 3,
       "dias_maximos": 7,
       "accion_vencimiento": "notificar",
       "configuracion_accion": {"grupo_id": 1, "template": "expiration.html"},
       "activo": true
     }' \
     .../slas/

# Bulk evaluation (equivalent to the sinpapel_verificar_slas management command)
curl -X POST .../slas/verificar/
# → 200 {"ejecutadas": {"notificar": 3, "escalar": 1}}
```

A POST that creates a duplicate `(estado, accion_vencimiento)` (violating `unique_together`) is mapped from `IntegrityError → 400`.

---

## 8. Flow portability endpoints

Admin-gated (`IsAdminUser`). Useful to move flow definitions across environments without touching the DB directly.

### `GET /flujos/<pk>/export/`

Downloads the flow as JSON v0.2 (`Content-Disposition: attachment`). Schema v0.2 includes `condiciones` + `slas` (added in sinpapel v0.4.x).

### `POST /flujos/import/[?dry_run=true][&activo=true]`

Imports a flow JSON. Atomic, rejects missing references, validates the schema version.

- `?dry_run=true` — validates without persisting; returns `{"dry_run": true, "would_create": {...}}`.
- `?activo=true` — overrides the safe default `activo=False` on import.

---

## 9. Permissions

| Endpoint | Permission | Notes |
|---|---|---|
| `available-transitions`, `transition`, `history` | `IsAuthenticated` | Group-level filtering handled by `ConfiguracionTransicion.grupos_permitidos` inside the engine. Engine raises `PermissionError → 403`. |
| `preview-transition`, `metadatos` | `IsAuthenticated` | |
| `documentos`, `requisitos` | `IsAuthenticated` | Upload/list/delete documents; read current-state requirements. |
| `sla-status` | `IsAdminUser` | Mutation possible (`alertar` action). |
| `/condiciones/*`, `/slas/*`, `/slas/verificar/` | `IsAdminUser` | All admin resources. |
| `/flujos/<pk>/export/`, `/flujos/import/` | `IsAdminUser` | |

Per-transition group filtering is **not** a custom DRF permission class. It lives in `WorkflowEngine.puede_cambiar_estado`, which raises `PermissionError`. The viewset maps it to `403` (ADR-007).

---

## 10. Security checklist

Reference: ADR-012 (FIEL dual-mode signing).

| Item | Status | Notes |
|---|:---:|---|
| `SINPAPEL_ALLOW_SERVER_SIGNING=False` default | ✅ | Server-side mode is opt-in only |
| `key_file` + `password` `write_only=True` | ✅ | Never leaked in responses |
| `del key_bytes; del password; gc.collect()` in `finally` | ✅ | `_with_secure_key_buffer` ensures cleanup |
| Conservative logging | ✅ | `caplog` tests verify no key/password material in log capture |
| Audit `RegistroFirma.backend_metadata.mode="server-side"` | ✅ | For post-incident forensics |
| E2E tests both modes + setting on/off | ✅ | 28+ tests |
| Rate limiting mode B (`UserRateThrottle`) | ⏸️ | **Deferred** — user must enable in production |
| HTTPS-only enforcement | 📄 | Documented; user responsibility |

---

## 11. Testing

```bash
# Install dev deps
pip install -e ".[dev]"

# Run the suite
pytest

# Run only install-smoke tests (slow, skipped by default)
pytest -m install_smoke
```

The package ships 90+ unit + E2E tests covering routers, viewsets, serializers, signature dispatch, metadata factory, predicate viewsets, SLA viewsets, and flow portability endpoints. The smoke suite verifies pip-installability into a fresh venv.

---

## 12. Known limitations & Roadmap

**Limitations:**

- `drf-spectacular` schema generation produces warnings for the polymorphic `SignatureRequestSerializer` (discriminated union). Functional but the OpenAPI shape is not perfect.
- Rate limiting for FIEL server-side mode is the consumer's responsibility.
- No API versioning (`/v1/`) until 1.0.

**Roadmap:**

- `drf-spectacular` polish (post-1.0).
- Built-in `UserRateThrottle` opt-in via setting.
- Public PyPI release after stable adoption in SEP + FONDESO.

---

## 13. License & Contributing

GPL-3.0-or-later — see [LICENSE](LICENSE).

Issues + PRs at https://github.com/aprendomx/sinpapel-drf/issues. Tag with `area/sinpapel-drf`.

**Architecture decisions:**

- ADR-010 — Two-package split sinpapel + sinpapel-drf
- ADR-011 — Cache layer in sinpapel core
- ADR-012 — FIEL dual-mode signing

**Related projects:**

- [sinpapel](https://github.com/aprendomx/sinpapel) — engine core (workflow + signature + audit + predicates + SLA + metadata)
- [sinpapel-webhooks](https://github.com/aprendomx/sinpapel-webhooks) — event-driven HTTP communication
- [sinpapel-designer](https://github.com/aprendomx/sinpapel-designer) — visual workflow editor
