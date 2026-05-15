"""sinpapel-drf — SLAConfiguracion CRUD ViewSet (v0.2.0)."""
from __future__ import annotations

from django.db import IntegrityError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from sinpapel.models import SLAConfiguracion
from sinpapel.services.sla_engine import SLAEngine
from sinpapel_drf.serializers import SLAConfiguracionSerializer


class SLAConfiguracionViewSet(viewsets.ModelViewSet):
    """ModelViewSet para SLAConfiguracion (timers de estado).

    Filtros via query params:
        ?estado=<id>
        ?activo=<bool>
    Acción extra:
        POST /slas/verificar/ → SLAEngine.verificar_todos()
    """

    serializer_class = SLAConfiguracionSerializer
    permission_classes = [IsAdminUser]
    queryset = SLAConfiguracion.objects.all().order_by("estado_id")

    def get_queryset(self):
        qs = super().get_queryset()
        estado_id = self.request.query_params.get("estado")
        if estado_id:
            qs = qs.filter(estado_id=estado_id)
        activo = self.request.query_params.get("activo")
        if activo is not None:
            qs = qs.filter(activo=(activo.lower() == "true"))
        return qs

    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except IntegrityError as exc:
            raise ValidationError({"detail": [str(exc)]})

    @action(detail=False, methods=["post"], url_path="verificar")
    def verificar(self, request):
        """POST /slas/verificar/ → dispara SLAEngine.verificar_todos()."""
        ejecutadas = SLAEngine.verificar_todos()
        return Response({"ejecutadas": ejecutadas}, status=status.HTTP_200_OK)
