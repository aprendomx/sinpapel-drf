# sinpapel-drf

> **v0.2.1** — Capa HTTP DRF para [sinpapel](https://github.com/aprendomx/sinpapel).
>
> Endpoints REST auto-generados (workflow + firma + metadatos + predicados + SLA + preview + portabilidad de flujos) sobre modelos Django decorados con `@workflow_enabled`. Reutilizable en SEP, FONDESO y cualquier consumidor de sinpapel que necesite **una API HTTP funcional sin escribir ViewSets, serializers, URLs ni permission classes a mano**.
>
> [🇺🇸 Read in English](README.md)

---

## Tabla de Contenidos

1. [¿Qué es sinpapel-drf?](#1-qué-es-sinpapel-drf)
2. [Instalación](#2-instalación)
3. [Settings](#3-settings)
4. [Quickstart](#4-quickstart)
5. [Endpoints de workflow](#5-endpoints-de-workflow)
6. [Backends de firma + modo dual FIEL](#6-backends-de-firma--modo-dual-fiel)
7. [Endpoints admin (predicados + SLAs)](#7-endpoints-admin-predicados--slas)
8. [Endpoints de portabilidad de flujos](#8-endpoints-de-portabilidad-de-flujos)
9. [Permisos](#9-permisos)
10. [Checklist de seguridad](#10-checklist-de-seguridad)
11. [Testing](#11-testing)
12. [Limitaciones conocidas y Roadmap](#12-limitaciones-conocidas-y-roadmap)
13. [Licencia y Contribuir](#13-licencia-y-contribuir)

---

## 1. ¿Qué es sinpapel-drf?

`sinpapel-drf` es la **capa HTTP** de [sinpapel](https://github.com/aprendomx/sinpapel) (motor de workflow + auditoría + firma).

Para cada modelo Django decorado con `@workflow_enabled(expose_endpoints=True)`, sinpapel-drf publica automáticamente:

| Endpoint | Verbo | Propósito |
|---|---|---|
| `/<slug>/<pk>/available-transitions/` | GET | Lista los Estado destino válidos desde el estado actual |
| `/<slug>/<pk>/transition/` | POST | Ejecuta una transición (con firma opcional) |
| `/<slug>/<pk>/history/` | GET | Audit trail paginado (`django-simple-history`) |
| `/<slug>/<pk>/preview-transition/` | POST | **v0.2.0** — Reporte de impacto sin mutación |
| `/<slug>/<pk>/metadatos/` | GET / PATCH | **v0.2.0** — Schema de metadatos estructurados + update parcial |
| `/<slug>/<pk>/sla-status/` | POST | **v0.2.0** — Evalúa SLA por instancia |

Más recursos top-level admin:

| Endpoint | Verbo | Propósito |
|---|---|---|
| `/condiciones/` | CRUD | **v0.2.0** — Predicados de transición (`CondicionTransicion`) |
| `/slas/` | CRUD | **v0.2.0** — Timers de estado (`SLAConfiguracion`) |
| `/slas/verificar/` | POST | **v0.2.0** — Evaluación masiva de SLAs |
| `/flujos/<pk>/export/` | GET | Flujo como JSON portable |
| `/flujos/import/` | POST | Importa un JSON de flujo a un nuevo `VersionFlujo` |

**Pilares de diseño:**

- **Cero boilerplate en el consumidor.** No hay ViewSets, ni serializers, ni URL definitions. Solo decora el modelo.
- **Dispatch polimórfico de firma.** Un solo endpoint `POST /transition/` acepta FIEL client-side (recomendado), FIEL server-side (gated), manual o fake.
- **Serializers dinámicos para metadatos.** `MetaFormFactory.build_serializer()` construye serializers DRF en runtime a partir de `SCHEMA_METADATOS`; cacheado por modelo con `functools.lru_cache`.
- **Mapeo de errores consistente.** `PermissionError → 403`, `ValueError → 400`, `SignatureValidationError → 400`, `DjangoValidationError → 400`.

---

## 2. Instalación

```bash
pip install "sinpapel-drf @ git+ssh://git@github.com/aprendomx/sinpapel-drf.git@v0.2.1"
```

O vía `pyproject.toml`:

```toml
dependencies = [
    "sinpapel-drf @ git+ssh://git@github.com/aprendomx/sinpapel-drf.git@v0.2.1",
]
```

Arrastra transitivamente `sinpapel @v0.5.1`. Requiere Python 3.10+, Django 5.0+, DRF 3.14+.

### Agregar a `INSTALLED_APPS`

```python
# settings.py
INSTALLED_APPS = [
    # ...
    "sinpapel",
    "sinpapel_drf",
    # ...
]
```

### Montar las URLs

```python
# project/urls.py
from django.urls import include, path

urlpatterns = [
    path("sinpapel/api/", include("sinpapel_drf.urls")),
]
```

`sinpapel_drf.urls` expone:

- El `SinpapelRouter` dinámico (acciones per-modelo) para cada modelo registrado con `@workflow_enabled(expose_endpoints=True)`.
- Un `DefaultRouter` para los recursos admin `/condiciones/` y `/slas/`.
- Los endpoints `/flujos/<pk>/export/` y `/flujos/import/`.

---

## 3. Settings

| Setting | Default | Propósito |
|---|---|---|
| `SINPAPEL_ALLOW_SERVER_SIGNING` | `False` | Habilita el modo FIEL server-side (`.key` + password subidos). **Requiere revisión legal** — ver ADR-012. |
| `REST_FRAMEWORK.DEFAULT_AUTHENTICATION_CLASSES` | — | Auth estándar de DRF (Token, JWT, Session, etc.) |

El paquete no impone autenticación. El consumidor elige (Session, Token, JWT, etc.) vía el setting estándar de DRF.

---

## 4. Quickstart

### 1. Decorar el modelo

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

### 2. Sembrar `Estado` + `ConfiguracionTransicion` (Django admin, fixture o migration)

### 3. Llamar los endpoints

```bash
# Listar transiciones disponibles
curl -H "Authorization: Token <…>" \
     https://host/sinpapel/api/tramites/42/available-transitions/

# Preview de una transición sin mutar
curl -X POST -H "Authorization: Token <…>" \
     -H "Content-Type: application/json" \
     -d '{"target_state": "Aprobado"}' \
     https://host/sinpapel/api/tramites/42/preview-transition/

# Ejecutar la transición
curl -X POST -H "Authorization: Token <…>" \
     -H "Content-Type: application/json" \
     -d '{"target_state": "Aprobado", "comentarios": "OK"}' \
     https://host/sinpapel/api/tramites/42/transition/
```

---

## 5. Endpoints de workflow

Per-instancia, auto-registrados vía `SinpapelRouter`. Todos requieren `IsAuthenticated` por defecto.

### `GET .../available-transitions/`

Retorna la lista de objetos `Estado` destino válidos desde el estado actual.

```json
[
  {"id": 5, "nombre": "Aprobado", "color": "#4DEFE2"},
  {"id": 7, "nombre": "Rechazado", "color": "#FF0000"}
]
```

### `POST .../transition/`

Ejecuta una transición. Body validado por `TransitionRequestSerializer`:

```json
{
  "target_state": "Aprobado",
  "comentarios": "Documentación completa",
  "monto_aprobado": "150000.00",
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

Audit trail paginado (`page_size=10`, máx `100`):

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

Simula una transición y retorna un reporte de impacto. **NO muta estado, NO ejecuta side-effects, NO firma nada.**

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

Si `permitido` es `false`, `razones_bloqueo` contiene al menos un objeto `{tipo, mensaje}` con `tipo ∈ {estado, transicion, documento, permiso, predicado}`.

### `GET / PATCH .../metadatos/` *(v0.2.0)*

Para modelos que heredan `MetadatosCapturables`:

**GET** retorna el schema + values actuales:

```json
{
  "schema": [
    {"nombre": "rfc", "tipo": "str", "requerido": true, "default": null,
     "choices": null, "etiqueta": "RFC", "ayuda": ""}
  ],
  "values": {"rfc": "ABCD010101ABC"}
}
```

**PATCH** valida el update parcial vía un serializer DRF construido dinámicamente con `MetaFormFactory.build_serializer()` (cacheado por modelo). Keys fuera del `SCHEMA_METADATOS` se rechazan con 400.

```bash
curl -X PATCH -d '{"rfc": "ABCD010101ABC"}' .../metadatos/
```

### `POST .../sla-status/` *(v0.2.0)*

Evalúa el SLA para una instancia específica vía `SLAEngine.evaluar_instancia()`. **POST** porque la acción `alertar` puede mutar campos de la instancia. Retorna la lista de acciones ejecutadas (o `[]` si no hay SLA activo o ninguno venció).

Requiere `IsAdminUser`.

---

## 6. Backends de firma + modo dual FIEL

`POST /transition/` acepta un body opcional `signature` discriminado por `(backend, mode)`. Cuatro variantes, validadas por `SignatureRequestSerializer.to_internal_value()`.

### Modo A — FIEL client-side (recomendado, default)

El cliente firma localmente con las herramientas provistas por el SAT (`firma.gob.mx` o librerías locales). El servidor **nunca ve** la llave privada.

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

### Modo B — FIEL server-side (gated)

El servidor recibe `.cer` + `.key` + `password` vía multipart y firma internamente. **Requiere `SINPAPEL_ALLOW_SERVER_SIGNING=True`** y revisión legal (ADR-012).

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

Tras firmar, los bytes de la key se borran vía `_with_secure_key_buffer` (`del` + `gc.collect()` en `finally`).

### Manual

Workflow con firma escaneada + testigo.

```json
{
  "signature": {
    "backend": "manual",
    "scanned_image_path": "/media/firmas/123.png",
    "witness_name": "Juan Pérez"
  }
}
```

### Fake (solo tests)

```json
{ "signature": { "backend": "fake" } }
```

---

## 7. Endpoints admin (predicados + SLAs)

Ambos ModelViewSets. **Todas las rutas requieren `IsAdminUser`** (`is_staff=True`).

### CRUD `CondicionTransicion` — predicados de transición

Un predicado se evalúa antes de permitir la transición. Tres backends soportados: `python_path`, `json_logic`, `django_orm`.

```bash
# Listar + filtrar
curl ".../condiciones/?transicion=7&activo=true"

# Crear
curl -X POST -H "Content-Type: application/json" \
     -d '{
       "transicion": 7,
       "tipo": "json_logic",
       "configuracion": {"logic": {">": [{"var": "monto"}, 0]}},
       "mensaje_error": "El monto debe ser positivo",
       "orden": 1,
       "activo": true
     }' \
     .../condiciones/

# Update / Delete
curl -X PATCH -d '{"activo": false}' .../condiciones/123/
curl -X DELETE .../condiciones/123/
```

### CRUD `SLAConfiguracion` — timers de estado

Un SLA define un límite máximo de días en un estado y la acción a ejecutar al vencer. Acciones: `notificar`, `escalar`, `rechazar`, `alertar`.

```bash
# Listar + filtrar
curl ".../slas/?estado=3"

# Crear
curl -X POST -H "Content-Type: application/json" \
     -d '{
       "estado": 3,
       "dias_maximos": 7,
       "accion_vencimiento": "notificar",
       "configuracion_accion": {"grupo_id": 1, "template": "vencimiento.html"},
       "activo": true
     }' \
     .../slas/

# Evaluación masiva (equivalente al management command sinpapel_verificar_slas)
curl -X POST .../slas/verificar/
# → 200 {"ejecutadas": {"notificar": 3, "escalar": 1}}
```

Un POST que cree un duplicado `(estado, accion_vencimiento)` (viola `unique_together`) se mapea desde `IntegrityError → 400`.

---

## 8. Endpoints de portabilidad de flujos

Gated por `IsAdminUser`. Útil para mover definiciones de flujo entre entornos sin tocar la DB directo.

### `GET /flujos/<pk>/export/`

Descarga el flujo como JSON v0.2 (`Content-Disposition: attachment`). El schema v0.2 incluye `condiciones` + `slas` (agregados en sinpapel v0.4.x).

### `POST /flujos/import/[?dry_run=true][&activo=true]`

Importa un JSON de flujo. Atómico, rechaza referencias faltantes, valida versión de schema.

- `?dry_run=true` — valida sin persistir; retorna `{"dry_run": true, "would_create": {...}}`.
- `?activo=true` — override del safe default `activo=False` en import.

---

## 9. Permisos

| Endpoint | Permission | Notas |
|---|---|---|
| `available-transitions`, `transition`, `history` | `IsAuthenticated` | Filtrado por grupo lo maneja `ConfiguracionTransicion.grupos_permitidos` dentro del engine. El engine lanza `PermissionError → 403`. |
| `preview-transition`, `metadatos` | `IsAuthenticated` | |
| `sla-status` | `IsAdminUser` | Mutación posible (acción `alertar`). |
| `/condiciones/*`, `/slas/*`, `/slas/verificar/` | `IsAdminUser` | Todos los recursos admin. |
| `/flujos/<pk>/export/`, `/flujos/import/` | `IsAdminUser` | |

El filtrado por grupo per-transición **NO** es una permission class custom de DRF. Vive en `WorkflowEngine.puede_cambiar_estado`, que lanza `PermissionError`. El viewset lo mapea a `403` (ADR-007).

---

## 10. Checklist de seguridad

Referencia: ADR-012 (firma dual-mode FIEL).

| Item | Status | Notas |
|---|:---:|---|
| `SINPAPEL_ALLOW_SERVER_SIGNING=False` default | ✅ | Modo server-side opt-in only |
| `key_file` + `password` `write_only=True` | ✅ | No leakean en responses |
| `del key_bytes; del password; gc.collect()` en `finally` | ✅ | `_with_secure_key_buffer` garantiza cleanup |
| Logging conservador | ✅ | Tests con `caplog` verifican que no aparezcan key/password en log capture |
| Audit `RegistroFirma.backend_metadata.mode="server-side"` | ✅ | Para forensics post-incidente |
| Tests E2E ambos modos + setting on/off | ✅ | 28+ tests |
| Rate limiting modo B (`UserRateThrottle`) | ⏸️ | **Diferido** — el consumer debe habilitarlo en producción |
| Enforcement HTTPS-only | 📄 | Documentado; responsabilidad del consumer |

---

## 11. Testing

```bash
# Instalar dev deps
pip install -e ".[dev]"

# Correr la suite
pytest

# Solo install-smoke tests (lento, skip por default)
pytest -m install_smoke
```

El paquete trae 90+ tests unit + E2E que cubren routers, viewsets, serializers, signature dispatch, metadata factory, predicate viewsets, SLA viewsets y endpoints de portabilidad. La smoke suite verifica que pip-install funcione en un venv fresco.

---

## 12. Limitaciones conocidas y Roadmap

**Limitaciones:**

- `drf-spectacular` genera warnings en el `SignatureRequestSerializer` polimórfico (discriminated union). Funcional, pero el shape OpenAPI no es perfecto.
- Rate limiting para modo FIEL server-side es responsabilidad del consumer.
- Sin API versioning (`/v1/`) hasta 1.0.

**Roadmap:**

- Pulir `drf-spectacular` (post-1.0).
- Built-in `UserRateThrottle` opt-in vía setting.
- Release público en PyPI tras adopción estable en SEP + FONDESO.

---

## 13. Licencia y Contribuir

GPL-3.0-or-later — ver [LICENSE](LICENSE).

Issues + PRs en https://github.com/aprendomx/sinpapel-drf/issues. Tag con `area/sinpapel-drf`.

**Decisiones de arquitectura:**

- ADR-010 — Split en dos paquetes sinpapel + sinpapel-drf
- ADR-011 — Cache layer en sinpapel core
- ADR-012 — Firma dual-mode FIEL

**Proyectos relacionados:**

- [sinpapel](https://github.com/aprendomx/sinpapel) — engine core (workflow + firma + audit + predicados + SLA + metadatos)
- [sinpapel-webhooks](https://github.com/aprendomx/sinpapel-webhooks) — comunicación HTTP event-driven
- [sinpapel-designer](https://github.com/aprendomx/sinpapel-designer) — editor visual de workflows
