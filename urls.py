"""URL config for sinpapel-drf.

Consumer must include this in their root urls.py:

    urlpatterns = [
        path("sinpapel/api/", include("sinpapel_drf.urls")),
    ]

v0.2.0: admin_router publishes /condiciones/ + /slas/. SinpapelRouter
continues to publish per-workflow-enabled-model resources dynamically.
"""
from django.urls import path
from rest_framework.routers import DefaultRouter

from sinpapel_drf.condicion_viewset import CondicionTransicionViewSet
from sinpapel_drf.flow_views import FlujoExportView, FlujoImportView
from sinpapel_drf.routers import SinpapelRouter
from sinpapel_drf.sla_viewset import SLAConfiguracionViewSet

router = SinpapelRouter()

admin_router = DefaultRouter()
# No registrar el converter global drf_format_suffix: dos routers en el mismo
# proceso (o un router del proyecto consumidor) provocan que Django >= 5.1 lance
# "Converter 'drf_format_suffix' is already registered.". Ver SinpapelRouter.
admin_router.include_format_suffixes = False
admin_router.register("condiciones", CondicionTransicionViewSet, basename="condicion")
admin_router.register("slas", SLAConfiguracionViewSet, basename="sla")

urlpatterns = router.urls + admin_router.urls + [
    path(
        "flujos/<int:pk>/export/",
        FlujoExportView.as_view(),
        name="flujo-export",
    ),
    path(
        "flujos/import/",
        FlujoImportView.as_view(),
        name="flujo-import",
    ),
]
