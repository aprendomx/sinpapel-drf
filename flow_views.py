"""sinpapel-drf — Flow portability REST endpoints (S13.9).

2 APIView que reusan 100% schema funciones de sinpapel.schemas.flujo_export
(S13.8). Permission: IsAdminUser (is_staff=True). Sub-epic E13c final.

S13.6 D-perm spirit: skip duplicate logic. Schema funciones son single source
of truth — endpoints son thin wrappers para HTTP semantic mapping.
"""
from __future__ import annotations

import datetime
import re

from django.http import Http404
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from sinpapel.models import VersionFlujo
from sinpapel.schemas.flujo_export import deserialize_flujo, serialize_flujo


def _slugify(name: str) -> str:
    """Slug determinístico para Content-Disposition filename."""
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", name).strip("_")
    return slug or "flujo"


class FlujoExportView(APIView):
    """GET /sinpapel/api/flujos/<pk>/export/ → JSON descargable (schema v0.1).

    Permission: IsAdminUser (is_staff=True).
    Response 200 con `Content-Disposition: attachment; filename=...` para
    forzar download en browsers (D-content-disposition).
    """

    permission_classes = [IsAdminUser]

    def get(self, request, pk: int):
        try:
            flujo = VersionFlujo.objects.get(pk=pk)
        except VersionFlujo.DoesNotExist as exc:
            raise Http404(f"VersionFlujo with id={pk} does not exist") from exc

        data = serialize_flujo(flujo)
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y%m%dT%H%M%SZ"
        )
        filename = f"flujo_{_slugify(flujo.nombre)}_{timestamp}.json"
        return Response(
            data,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )


class FlujoImportView(APIView):
    """POST /sinpapel/api/flujos/import/ → create new VersionFlujo from JSON.

    Permission: IsAdminUser (is_staff=True).
    Query params:
        ?dry_run=true — validate sin persistir (returns 200 + dry_run flag).
        ?activo=true — override safe default activo=False.

    Error mapping (D-error-mapping reuse S13.5/S13.6 D3):
        ValueError (missing/duplicate/ambiguity/schema) → ValidationError (400).
    """

    permission_classes = [IsAdminUser]

    def post(self, request):
        data = request.data
        if not isinstance(data, dict):
            raise ValidationError({"detail": "Body must be a JSON object"})

        # D-dry-run-detection: query param strict lowercase
        dry_run = request.query_params.get("dry_run") == "true"
        activo = request.query_params.get("activo") == "true"

        try:
            flujo = deserialize_flujo(data, dry_run=dry_run, activo=activo)
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc

        flujo_data = data.get("flujo", {})
        n_transiciones = len(flujo_data.get("transiciones", []))
        n_requisitos = len(flujo_data.get("requisitos", []))

        if dry_run:
            return Response({
                "dry_run": True,
                "would_create": {
                    "nombre": flujo_data.get("nombre"),
                    "transiciones_count": n_transiciones,
                    "requisitos_count": n_requisitos,
                },
            }, status=200)

        return Response({
            "id": flujo.pk,
            "nombre": flujo.nombre,
            "activo": flujo.activo,
            "transiciones_count": n_transiciones,
            "requisitos_count": n_requisitos,
        }, status=201)
