"""sinpapel-drf — Serializers para WorkflowViewSet endpoints.

S13.5: serializers básicos. SignatureRequestSerializer polimórfico
llega en S13.6 (FIEL dual mode).

D1: TransitionResponseSerializer mapea dict que retorna
WorkflowEngine.cambiar_estado() (no es un Model).
D2: TransitionRequestSerializer NO incluye signature field — S13.6 lo
agregará polimórfico (Mode A client-side default + Mode B server-side opt-in).
D9: HistoryEntrySerializer.history_user nullable (mutaciones sin
HistoryRequestMiddleware retornan None).
D10: serializers.Serializer (no ModelSerializer) — inputs/outputs son
shapes, no Models. HistoricalRecord es runtime-generated class.
"""
from __future__ import annotations

from rest_framework import serializers


class EstadoSerializer(serializers.Serializer):
    """Estado destino para available_transitions response."""

    id = serializers.IntegerField()
    nombre = serializers.CharField()
    color = serializers.CharField(default="", allow_blank=True, required=False)


class TransitionRequestSerializer(serializers.Serializer):
    """Request body para POST /transition/.

    D2: sin signature field — S13.6 lo agregará polimórfico.
    """

    target_state = serializers.CharField(required=True, allow_blank=False)
    comentarios = serializers.CharField(
        required=False, allow_blank=True, default=""
    )
    monto_aprobado = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
    condiciones = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, default=None
    )


class TransitionResponseSerializer(serializers.Serializer):
    """Response para POST /transition/.

    D1: mapea dict que retorna WorkflowEngine.cambiar_estado() —
    success, instance_id, estado_anterior, estado_nuevo, seguimiento_id.
    """

    success = serializers.BooleanField()
    instance_id = serializers.IntegerField()
    estado_anterior = serializers.CharField(allow_null=True)
    estado_nuevo = serializers.CharField()
    seguimiento_id = serializers.IntegerField()


class HistoryEntrySerializer(serializers.Serializer):
    """Entry de django-simple-history para GET /history/.

    D9: history_user nullable (allow_null=True) cuando la mutación
    ocurre fuera de request lifecycle (management commands, etc.).
    """

    history_id = serializers.IntegerField()
    history_type = serializers.CharField()
    history_date = serializers.DateTimeField()
    history_user = serializers.CharField(
        source="history_user.username", allow_null=True, required=False
    )
    history_change_reason = serializers.CharField(
        allow_null=True, allow_blank=True, required=False
    )
