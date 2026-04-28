"""sinpapel-drf — DRF HTTP layer for sinpapel.

Auto-routing desde @workflow_enabled decorator + ViewSets + serializers
polimórficos para signature backends + permission classes integradas con
ConfiguracionTransicion.grupos_permitidos.

Las re-exports públicas (WorkflowViewSet, SinpapelRouter, SignatureRequestSerializer,
GruposPermitidosPermission) se agregarán en stories S13.4-S13.6.
"""
__version__ = "0.1.0"

__all__ = ["__version__"]
