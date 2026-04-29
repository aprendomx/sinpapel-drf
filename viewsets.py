"""sinpapel-drf — WorkflowViewSet full implementation (S13.5).

3 actions completas:
- available_transitions (GET) → EstadoSerializer many=True (D5: lista plana)
- transition (POST) → TransitionRequestSerializer input + TransitionResponseSerializer output
- history (GET) → HistoryEntrySerializer + PageNumberPagination (D4)

Error mapping (D3):
- ValueError → DRF ValidationError (400)
- PermissionError → DRF PermissionDenied (403)

build_viewset_for(config) genera subclase dinámica parametrizada por modelo,
usado por SinpapelRouter para auto-routing desde WorkflowRegistry.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from sinpapel_drf.serializers import (
    EstadoSerializer,
    HistoryEntrySerializer,
    TransitionRequestSerializer,
    TransitionResponseSerializer,
)

if TYPE_CHECKING:
    from sinpapel.registry import WorkflowConfig


class HistoryPagination(PageNumberPagination):
    """Pagination para GET /history/ — D4: page_size 10/100 cap."""

    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


class WorkflowViewSet(GenericViewSet):
    """Auto-instantiated ViewSet via SinpapelRouter.

    S13.5: full implementation. Permission stub IsAuthenticated;
    GruposPermitidosPermission llega en S13.6.
    """

    permission_classes = [IsAuthenticated]
    pagination_class = HistoryPagination

    @action(detail=True, methods=["get"], url_path="available-transitions")
    def available_transitions(self, request, pk=None):
        """GET .../available-transitions/ → lista de Estado destino válidos (D5)."""
        instance = self.get_object()
        states = instance.available_transitions(request.user)
        serializer = EstadoSerializer(states, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        """POST .../transition/ → ejecuta transición + retorna info en 201."""
        instance = self.get_object()

        req_serializer = TransitionRequestSerializer(data=request.data)
        req_serializer.is_valid(raise_exception=True)

        try:
            result_dict = instance.transition(
                target_state_name=req_serializer.validated_data["target_state"],
                user=request.user,
                comentarios=req_serializer.validated_data.get("comentarios", ""),
                monto_aprobado=req_serializer.validated_data.get("monto_aprobado"),
                condiciones=req_serializer.validated_data.get("condiciones"),
            )
        except PermissionError as e:
            # D3: engine raises PermissionError para target inexistente,
            # transición no válida, grupos no permitidos. Cubrimos con 403.
            raise PermissionDenied(detail=str(e))
        except ValueError as e:
            # Defensive: race condition entre puede_cambiar_estado y resolve.
            raise ValidationError({"target_state": [str(e)]})

        resp_serializer = TransitionResponseSerializer(result_dict)
        return Response(resp_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        """GET .../history/ → audit trail paginated (D4: 10/100)."""
        instance = self.get_object()
        try:
            queryset = list(instance.history.all())
        except AttributeError:
            queryset = []

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = HistoryEntrySerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = HistoryEntrySerializer(queryset, many=True)
        return Response(serializer.data)


def build_viewset_for(config: "WorkflowConfig") -> type[WorkflowViewSet]:
    """Construye subclase dinámica de WorkflowViewSet parametrizada por modelo.

    queryset se resuelve lazy via get_queryset() para soportar tests con
    mock models (sin Django manager) y delay de DB access hasta request time.
    """
    config_ref = config

    def get_queryset(self):
        return config_ref.model.objects.all()

    return type(
        f"{config.model.__name__}WorkflowViewSet",
        (WorkflowViewSet,),
        {
            "_workflow_config": config,
            "get_queryset": get_queryset,
            "queryset": None,
        },
    )
