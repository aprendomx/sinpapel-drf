# Changelog

All notable changes to `sinpapel-drf` will be documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/jadrians/creditos/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/jadrians/creditos/releases/tag/sinpapel-drf-v0.1.0
