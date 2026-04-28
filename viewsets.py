"""sinpapel-drf — WorkflowViewSet base + factory.

S13.4 stub: 3 actions (available_transitions, transition, history) retornan
respuestas mínimas. Full implementation (serializers polimórficos, signature
dispatch, validation) llega en S13.5 + S13.6.

build_viewset_for(config) genera subclase dinámica parametrizada por modelo,
usado por SinpapelRouter para auto-routing desde WorkflowRegistry.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

if TYPE_CHECKING:
    from sinpapel.registry import WorkflowConfig


class WorkflowViewSet(GenericViewSet):
    """Base ViewSet para modelos workflow-enabled.

    Stub S13.4 — actions retornan respuestas mínimas:
    - available_transitions: queries instance.available_transitions(user)
    - transition: stub que retorna 200 con {"status": "stub", "todo": "S13.5"}
    - history: queries instance.history (django-simple-history)

    Permission stub IsAuthenticated; GruposPermitidosPermission llega en S13.6.
    """

    permission_classes = [IsAuthenticated]

    @action(detail=True, methods=["get"], url_path="available-transitions")
    def available_transitions(self, request, pk=None):
        """GET /sinpapel/api/<slug>/<pk>/available-transitions/

        Retorna lista de Estado destino válidos para el user actual.
        """
        instance = self.get_object()
        states = instance.available_transitions(request.user)
        return Response([
            {"id": s.id, "nombre": s.nombre} for s in states
        ])

    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        """POST /sinpapel/api/<slug>/<pk>/transition/

        Stub S13.4 — full impl en S13.5 con serializers polimórficos +
        signature dispatch (S13.6).
        """
        return Response(
            {"status": "stub", "todo": "S13.5 full implementation"},
            status=200,
        )

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        """GET /sinpapel/api/<slug>/<pk>/history/

        Retorna audit trail vía django-simple-history (instance.history).
        Limit 10 entries en stub; pagination llega en S13.5.
        """
        instance = self.get_object()
        try:
            entries = instance.history.all()[:10]
        except AttributeError:
            # Modelo sin HistoricalRecords (no debería pasar en producción)
            entries = []
        return Response([
            {
                "history_id": e.history_id,
                "history_type": e.history_type,
                "history_date": e.history_date.isoformat() if e.history_date else None,
            }
            for e in entries
        ])


def build_viewset_for(config: "WorkflowConfig") -> type[WorkflowViewSet]:
    """Construye subclase dinámica de WorkflowViewSet parametrizada por modelo.

    Usado por SinpapelRouter para registrar un ViewSet por workflow_key.
    Adjunta el WorkflowConfig al class para uso en serializers/permissions
    futuras (S13.5 + S13.6).

    queryset se resuelve lazy via get_queryset() para soportar tests con
    mock models (sin Django manager) y delay de DB access hasta request time.
    """
    config_ref = config  # closure capture

    def get_queryset(self):
        return config_ref.model.objects.all()

    return type(
        f"{config.model.__name__}WorkflowViewSet",
        (WorkflowViewSet,),
        {
            "_workflow_config": config,
            "get_queryset": get_queryset,
            # queryset attr placeholder None — get_queryset() lo override en runtime
            "queryset": None,
        },
    )
