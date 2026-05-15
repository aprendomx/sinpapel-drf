"""sinpapel-drf — CondicionTransicion CRUD ViewSet (v0.2.0)."""
from __future__ import annotations

from rest_framework import viewsets
from rest_framework.permissions import IsAdminUser

from sinpapel.models import CondicionTransicion
from sinpapel_drf.serializers import CondicionTransicionSerializer


class CondicionTransicionViewSet(viewsets.ModelViewSet):
    """ModelViewSet para CondicionTransicion (predicados).

    Filtros via query params:
        ?transicion=<id>
        ?activo=<bool>  (acepta "true" / "false", case-insensitive)
    """

    serializer_class = CondicionTransicionSerializer
    permission_classes = [IsAdminUser]
    queryset = CondicionTransicion.objects.all().order_by("transicion_id", "orden")

    def get_queryset(self):
        qs = super().get_queryset()
        transicion_id = self.request.query_params.get("transicion")
        if transicion_id:
            qs = qs.filter(transicion_id=transicion_id)
        activo = self.request.query_params.get("activo")
        if activo is not None:
            qs = qs.filter(activo=(activo.lower() == "true"))
        return qs
