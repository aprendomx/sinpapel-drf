# Changelog

All notable changes to `sinpapel-drf` will be documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-06-26

### Added

- Endpoints de carga y validación de documentos en `WorkflowViewSet`:
  `POST/GET /<slug>/<pk>/documentos/` (crea/lista `InstanciaDocumento` typed,
  acepta `documento` o `tipo_documento`), `DELETE /<slug>/<pk>/documentos/<doc_id>/`
  y `GET /<slug>/<pk>/requisitos/` (cumplimiento documental del estado actual).
  `/requisitos/` consume `WorkflowEngine.evaluar_requisitos_documentales` —
  mecanismo público compartido con el engine, sin duplicar lógica.

### Changed

- Pin de `sinpapel` a `@v0.6.0` (requiere `InstanciaDocumento.archivo` y
  `WorkflowEngine.evaluar_requisitos_documentales`).

## [0.2.2] - 2026-06-18

Corrige un crash de arranque en proyectos consumidores y cambia el protocolo de
la dependencia del core a HTTPS.

### Fixed

- **`Converter 'drf_format_suffix' is already registered.`** al importar
  `sinpapel_drf.urls` en proyectos con Django ≥ 5.1 y DRF 3.16.0 (versión sin
  guarda en `register_converter`). `SinpapelRouter` y el `admin_router` llamaban
  ambos a `format_suffix_patterns`, registrando dos veces el converter global de
  DRF. Ahora ambos routers usan `include_format_suffixes = False`: la librería ya
  no registra ningún converter de proceso. El content negotiation por header
  `Accept` y `?format=json` sigue funcionando; solo se retira el sufijo `.json`
  en la URL (que ningún test ni endpoint del framework usaba).

### Dependencies

- `sinpapel @ git+https://github.com/aprendomx/sinpapel.git@v0.5.1` — protocolo
  cambiado de `git+ssh` a `git+https` para instalación sin clave SSH (CI / runners).

## [0.2.1] - 2026-05-19

Actualiza dependencia del core y metadatos del paquete.

### Dependencies

- `sinpapel @ git+https://github.com/aprendomx/sinpapel.git@v0.5.1` (era `@v0.4.2`).

### Changed

- Relicencia de MIT a `GPL-3.0-or-later` (SPDX).
- `requires-python` bajado de `>=3.13` a `>=3.10` para alinearse con el soporte real de sinpapel.
- Classifiers actualizados: añadidos Django 5.1, Python 3.10, 3.11, 3.12.
- `build-system` requiere `setuptools>=77` (PEP 639).

## [0.2.0] - 2026-05-15

Expone sinpapel v0.4.0 features sobre HTTP. Dep bump: `sinpapel @ v0.1.1 → @v0.4.0`.

### Added

- **`POST /<slug>/<pk>/preview-transition/`** — simula transición y retorna reporte de impacto (`permitido`, `razones_bloqueo`, `documentos_faltantes`, `predicados_fallidos`, `aprobadores_requeridos`, `side_effects`, `historial_reciente`). NO muta. Reusa `WorkflowEngine.preview_transition()`. `IsAuthenticated`.
- **`GET /<slug>/<pk>/metadatos/`** — retorna `{schema, values}` para modelos que heredan `MetadatosCapturables`. Schema construido desde `SCHEMA_METADATOS`. `IsAuthenticated`.
- **`PATCH /<slug>/<pk>/metadatos/`** — update parcial validado por serializer DRF construido dinámicamente vía `MetaFormFactory.build_serializer()` y cacheado por modelo (`functools.lru_cache`). Rechaza keys fuera de schema con 400. Mapea `TypeError`/`ValueError`/`DjangoValidationError` a 400.
- **`POST /<slug>/<pk>/sla-status/`** — evalúa SLA per-instance via `SLAEngine.evaluar_instancia()`. POST porque la acción `alertar` puede mutar campos. `IsAdminUser`.
- **`GET/POST /condiciones/` + detail CRUD** — ModelViewSet sobre `CondicionTransicion` (predicados de transición). Filtros: `?transicion=<id>`, `?activo=<bool>`. `IsAdminUser`.
- **`GET/POST /slas/` + detail CRUD** — ModelViewSet sobre `SLAConfiguracion`. Filtros: `?estado=<id>`, `?activo=<bool>`. `IsAdminUser`. `IntegrityError` (unique_together violation) → 400.
- **`POST /slas/verificar/`** — dispara `SLAEngine.verificar_todos()`. Retorna `{ejecutadas: {...}}`. `IsAdminUser`.
- **`metadata_views.py`** — helpers internos: `get_meta_serializer_class(model_cls)` con cache y `campo_to_dict(campo)` para serializar `CampoMetadato`.
- **5 nuevos serializers** en `serializers.py`: `PreviewTransitionRequestSerializer`, `PreviewTransitionResponseSerializer`, `CampoMetadatoSerializer`, `CondicionTransicionSerializer`, `SLAConfiguracionSerializer`.
- **28 tests E2E nuevos** distribuidos en 5 archivos (`test_preview_transition.py`, `test_metadatos_endpoint.py`, `test_metadata_helpers.py`, `test_condicion_crud.py`, `test_sla_crud.py`).

### Changed

- `urls.py` ahora monta un `DefaultRouter` adicional (`admin_router`) para los recursos top-level `condiciones` y `slas`, alongside del `SinpapelRouter` dinámico per-modelo.
- `WorkflowViewSet` ahora expone 6 acciones (antes 3): se suman `preview_transition`, `metadatos` (GET+PATCH), `sla_status`. Permisos override por acción (`sla_status` requiere `IsAdminUser`).

### Dependencies

- `sinpapel @ git+ssh://git@github.com/aprendomx/sinpapel.git@v0.4.0` (era `@v0.1.1`).

## [0.1.0] - 2026-04-29

Initial alpha release. DRF HTTP layer for [sinpapel](https://github.com/jadrians/creditos/tree/main/sinpapel) workflow + signature engine. Released with `sinpapel >=0.1.0,<0.2`.

### Added

- **Auto-routing** (S13.4) — `@workflow_enabled(expose_endpoints=True)` decorator extension + `SinpapelRouter` consume `WorkflowRegistry` to register URLs lazy post-`apps.ready()`.
- **3 workflow endpoints per registered model** (S13.5):
  - `GET /<slug>/<pk>/available-transitions/` — lista `Estado` destino válidos.
  - `POST /<slug>/<pk>/transition/` — ejecuta transición + signature dispatch.
  - `GET /<slug>/<pk>/history/` — audit trail paginado (`PageNumberPagination` 10/100).
- **`SignatureRequestSerializer` polimórfico** (S13.6) — discriminated union via `to_internal_value()` dispatch para 4 backends:
  - `fiel/client-side` (default seguro, JSON body).
  - `fiel/server-side` (gated `SINPAPEL_ALLOW_SERVER_SIGNING=True`, multipart body).
  - `manual` (escaneo + testigo).
  - `fake` (tests only).
- **`FielBackend.sign_server_side()`** (S13.6) en sinpapel core — descifra `.key` PKCS#8 DER + firma RSA-SHA256 + descarta key vía `_with_secure_key_buffer` (del + gc.collect en finally).
- **2 flow portability endpoints** (S13.9) — `IsAdminUser`-gated:
  - `GET /flujos/<pk>/export/` — descarga JSON v0.1 con `Content-Disposition` attachment.
  - `POST /flujos/import/[?dry_run=true][&activo=true]` — atomic + reject-on-missing.
- **Cache layer integration** (S13.1+S13.2) — engine consume `get_estado_by_name`, `get_transitions_for`, `get_active_version_flujo`, `get_requisitos_for` con signal-based invalidation (post_save/post_delete/m2m_changed).
- **Error mapping consistency**:
  - `PermissionError → 403` (engine grupos_permitidos enforce, ADR-007).
  - `ValueError → 400` (validation, schema mismatch, race conditions).
  - `SignatureValidationError → 400`, `SignatureBackendNotConfiguredError → 400`.
  - `Http404` para `VersionFlujo.DoesNotExist` en export endpoint.

### Architecture decisions

- [ADR-010 — Two-package split sinpapel + sinpapel-drf](../dev/decisions/adr-010-two-package-split-sinpapel-drf.md)
- [ADR-011 — Cache layer en sinpapel core](../dev/decisions/adr-011-cache-layer-sinpapel-core.md)
- [ADR-012 — FIEL dual mode signing](../dev/decisions/adr-012-fiel-dual-mode-signing.md)

### Security

- Security checklist ADR-012 — 6/8 items implementados (rate limiting + HTTPS-only enforcement DEFERRED a story sucesora; documentados como user responsibility en README §9).
- `caplog` tests verifican que `password` y `key_bytes` NO aparecen en log capture durante request modo B.

### Known limitations

- drf-spectacular schema con discriminated union genera warnings esperados (schema funcional, shape no perfecto).
- Rate limiting modo B sin implementar — user habilita `UserRateThrottle` en producción.
- API versioning (`/v1/`) llega post-1.0.
- Migration de 12 callers `WorkflowService` legacy en `creditos/views.py` — story sucesora post-E13.

[Unreleased]: https://github.com/aprendomx/sinpapel-drf/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/aprendomx/sinpapel-drf/releases/tag/v0.2.1
[0.2.0]: https://github.com/aprendomx/sinpapel-drf/releases/tag/v0.2.0
[0.1.0]: https://github.com/aprendomx/sinpapel-drf/releases/tag/v0.1.0
