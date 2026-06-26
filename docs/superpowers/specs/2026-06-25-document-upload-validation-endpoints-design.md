# Diseño: endpoints de carga + validación de documentos (sinpapel-drf)

**Fecha:** 2026-06-25
**Estado:** Aprobado (diseño) — implementación bloqueada por prerrequisitos upstream
**Repo:** `aprendomx/sinpapel-drf`

## Contexto

Al verificar `sinpapel-drf` contra `sinpapel`, se confirmó que el endpoint
`POST /<slug>/<pk>/transition/` ya tolera transiciones de estado y las bloquea
(HTTP 403) cuando faltan documentos. Con `sinpapel==0.6.0` (rama
`feat/requisito-documental-enforce`) el motor además hace enforce de las reglas
finas `RequisitoEstadoDocumento` (tipo de documento + porcentaje mínimo), medidas
sobre `InstanciaDocumento.porcentaje`.

Sin embargo, `sinpapel-drf` **no expone ningún endpoint para cargar documentos**:
el cliente puede ver qué falta (`preview-transition` → `documentos_faltantes`) pero
no puede subir el documento que satisface el requisito. Este diseño cubre esa
brecha: endpoints de **carga, listado, borrado y consulta de requisitos**.

### Contrato del enforcement (sinpapel 0.6.0)

- La satisfacción *typed* de un `RequisitoEstadoDocumento(estado, tipo_documento,
  porcentaje, auto_carga)` se mide así: `porcentaje_actual =
  max(InstanciaDocumento.porcentaje)` para las instancias cuyo
  `documento.tipo_documento` coincide y cuya GFK `target` apunta al trámite.
- `auto_carga=True` ⇒ el requisito **no bloquea** (documento generado por el sistema).
- El flag coarse `Estado.expediente_obligatorio` se mide aparte, sobre
  `ExpedienteAdjunto` (GenericRelation `expedientes`). **Fuera de alcance** de este
  endpoint.

## Decisiones de diseño

| # | Decisión | Elección |
|---|---|---|
| 1 | Modelo que crea la carga | `InstanciaDocumento` (typed) |
| 2 | Cómo identifica el cliente el tipo | Acepta `documento` (PK) **o** `tipo_documento` (PK) |
| 3 | Dónde se guarda el archivo subido | Nuevo campo `InstanciaDocumento.archivo` (upstream) |

## Endpoints

Acciones nuevas en `WorkflowViewSet` (auto-enrutadas por `SinpapelRouter` para
cada modelo con `expose_endpoints=True`):

| Método + URL | Acción | Permiso |
|---|---|---|
| `POST /<slug>/<pk>/documentos/` | Sube un documento → crea `InstanciaDocumento` (multipart). | `IsAuthenticated` |
| `GET /<slug>/<pk>/documentos/` | Lista los `InstanciaDocumento` del trámite. | `IsAuthenticated` |
| `DELETE /<slug>/<pk>/documentos/<doc_id>/` | Elimina uno, solo si pertenece al trámite. | `IsAuthenticated` |
| `GET /<slug>/<pk>/requisitos/` | Requisitos del **estado actual** + cumplimiento por tipo. | `IsAuthenticated` |

`transition` **no cambia**: el engine ya devuelve 403 cuando un requisito no se
satisface.

### Routing

`POST`/`GET` comparten `url_path="documentos"` (detail=True). El `DELETE` usa una
acción con `url_path=r"documentos/(?P<doc_id>[0-9]+)"`. DRF `@action` soporta
regex en `url_path`.

## Payload de carga (`POST /documentos/`, multipart)

| Campo | Tipo | Req. | Notas |
|---|---|---|---|
| `archivo` | file | sí | El documento subido. |
| `documento` | int (PK) | uno de los dos | Documento del catálogo (ya trae `tipo_documento`). |
| `tipo_documento` | int (PK) | uno de los dos | Si no se manda `documento`, se resuelve el Documento del tipo. |
| `porcentaje` | int 0-100 | no | Default `100`. |
| `metadatos` | JSON | no | Se guarda en `InstanciaDocumento.metadatos`. |

- `target` (GFK) se fija desde el `<pk>` de la URL; el cliente **no** lo envía.
- Si llegan ambos `documento` y `tipo_documento`, **gana `documento`**.
- **Regla de resolución por `tipo_documento`:** exactamente 1 `Documento` de ese
  tipo → se usa; **0 o >1 → HTTP 400** pidiendo enviar `documento` explícito. No se
  auto-crean entradas de catálogo.

Respuesta `201` con el `InstanciaDocumentoSerializer` del objeto creado.

## Serializers

- **`InstanciaDocumentoUploadSerializer`** (write): valida que venga `documento` o
  `tipo_documento`, `archivo` requerido, `porcentaje` 0-100 (default 100); resuelve
  el `Documento` aplicando la regla de resolución; setea la GFK `target`.
- **`InstanciaDocumentoSerializer`** (read): `id, documento, tipo_documento`
  (nombre), `archivo` (url), `porcentaje`, `creado`.
- **`RequisitoStatusSerializer`** (read, para `/requisitos/`): `tipo_documento`
  (nombre), `porcentaje_requerido`, `porcentaje_actual`, `satisfecho` (bool),
  `auto_carga` (bool).

## `/requisitos/` — cumplimiento del estado actual

Lee `get_requisitos_for(estado_actual.id)` y calcula `porcentaje_actual` por tipo
con la misma fórmula del engine (`max(InstanciaDocumento.porcentaje)` por tipo).
Devuelve la lista de requisitos con su estado de cumplimiento. A diferencia de
`preview-transition`, **no requiere un `target_state`**: responde "qué necesita el
estado actual".

**Nota de duplicación:** esto replica la lógica de
`WorkflowEngine._validar_documentos` (privada). Riesgo de drift. Alternativa
futura: pedir a upstream un helper público `evaluar_requisitos_documentales(
instance)` y consumirlo (DRY). Por ahora se computa localmente y se deja anotado.

## Errores

| Caso | HTTP |
|---|---|
| Falta `archivo` / falta `documento`+`tipo_documento` / `porcentaje` fuera de rango | 400 |
| `tipo_documento` resuelve a 0 o >1 Documento | 400 (mensaje pide `documento`) |
| `documento`/`tipo_documento` PK inexistente | 400 |
| `DELETE` de un `doc_id` que no pertenece al trámite | 404 |

Parsers: `MultiPartParser`/`FormParser` en la carga.

## Testing

Harness autocontenido (settings en memoria + modelo `@workflow_enabled`, sin host
`creditos`) y tests pytest:

- Carga por `documento` (PK) → 201, crea `InstanciaDocumento` con `target` correcto.
- Carga por `tipo_documento`: exactamente 1 Documento → 201; 0 → 400; >1 → 400.
- `porcentaje` < requerido no satisface (transition sigue 403); subir a ≥100 → 201.
- `GET /documentos/` lista solo los del trámite.
- `DELETE` borra el propio; 404 para uno de otro trámite.
- `GET /requisitos/` refleja `satisfecho` antes/después de cargar.
- E2E: requisito al 100% ⇒ `transition` pasa de 403 a 201.

## Prerrequisitos upstream (bloquean la implementación, no el spec/plan)

1. `sinpapel`: mergear `feat/requisito-documental-enforce` a `main` + taggear `v0.6.0`.
2. `sinpapel`: agregar `InstanciaDocumento.archivo`
   (`upload_to="instancias_documento/"`, `blank=True, null=True`) + migración reversible.
3. `sinpapel-drf`: bumpear pin `@v0.5.1` → `@v0.6.0` (o el tag que incluya `archivo`).

## Fuera de alcance

- Satisfacer el flag coarse `expediente_obligatorio` (eso es `ExpedienteAdjunto`).
- Versionado/flujo de revisión de documentos (aprobado/rechazado).
- Generación de documentos (`auto_carga`), que produce el sistema, no el usuario.
