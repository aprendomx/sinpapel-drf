"""sinpapel-drf — SinpapelRouter auto-routing desde WorkflowRegistry.

S13.4: itera WorkflowRegistry.list_exposed() en __init__ y registra ViewSets
dinámicos via build_viewset_for(config). Eager pero safe — Django evalúa
urls.py LAZY post-startup (durante URL resolution, no al boot), por lo que
cuando SinpapelRouter() itera el registry, todas las apps ya completaron
apps.ready() y registraron sus modelos workflow-enabled.

Si el registry está vacío al instantiation, urlpatterns queda vacío (válido)
y se emite warning log para diagnóstico.
"""
from __future__ import annotations

import logging

from rest_framework.routers import DefaultRouter

from sinpapel.registry import WorkflowRegistry
from sinpapel_drf.viewsets import build_viewset_for

logger = logging.getLogger(__name__)


class SinpapelRouter(DefaultRouter):
    """Auto-registra ViewSets para todos los modelos con expose_endpoints=True.

    Usage en consumer:

        # mossc/urls.py
        urlpatterns = [
            path("sinpapel/api/", include("sinpapel_drf.urls")),
        ]

    Para cada WorkflowConfig con expose_endpoints=True, registra:
        /<effective_slug>/<pk>/available-transitions/
        /<effective_slug>/<pk>/transition/
        /<effective_slug>/<pk>/history/

    No registra el converter global ``drf_format_suffix`` de DRF
    (``include_format_suffixes = False``): hacerlo colisiona con cualquier
    otro DefaultRouter del proyecto consumidor cuando Django >= 5.1 hace que
    ``register_converter`` falle al re-registrar un nombre ya existente
    ("Converter 'drf_format_suffix' is already registered."). El content
    negotiation por header ``Accept`` y ``?format=json`` sigue funcionando.
    """

    include_format_suffixes = False

    def __init__(self) -> None:
        super().__init__()
        exposed = WorkflowRegistry.list_exposed()
        if not exposed:
            logger.warning(
                "SinpapelRouter: WorkflowRegistry has no models with "
                "expose_endpoints=True. Ensure your @workflow_enabled "
                "decorator includes expose_endpoints=True and that your "
                "apps are loaded before sinpapel_drf.urls is imported."
            )
        for config in exposed:
            viewset = build_viewset_for(config)
            self.register(
                config.effective_slug,
                viewset,
                basename=config.workflow_key,
            )
