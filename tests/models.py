"""Modelos espejo para correr la suite sin el proyecto host creditos.

Replican la superficie que los tests usaban de creditos.models:
- SolicitudPrueba  ≈ creditos.Solicitud (workflow-enabled, metadatos, expedientes)
- ProductoPrueba   ≈ creditos.ProductoCreditoFOVISSSTE (solo los campos usados)
- ProductoVersionFlujoPrueba ≈ creditos.ProductoVersionFlujo
"""
from django.contrib.contenttypes.fields import GenericRelation
from django.db import models

from sinpapel import workflow_enabled
from sinpapel.mixins import MetadatosCapturables, Trazable


class ProductoPrueba(models.Model):
    nombre = models.CharField(max_length=100)
    clave = models.CharField(max_length=30, blank=True, default="")
    identificador = models.CharField(max_length=30, blank=True, default="")
    marca = models.CharField(max_length=50, blank=True, default="")
    monto_minimo = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    monto_maximo = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tasa_interes = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    tasa_interes_moratorio = models.DecimalField(
        max_digits=6, decimal_places=2, default=0
    )

    class Meta:
        app_label = "tests"


class ProductoVersionFlujoPrueba(models.Model):
    producto = models.ForeignKey(ProductoPrueba, on_delete=models.CASCADE)
    flujo = models.ForeignKey("sinpapel.VersionFlujo", on_delete=models.CASCADE)

    class Meta:
        app_label = "tests"


@workflow_enabled(state_field="estado", workflow_key="drf_solicitud_prueba")
class SolicitudPrueba(MetadatosCapturables, Trazable):
    SCHEMA_METADATOS = []  # los tests lo inyectan vía monkeypatch

    estado = models.ForeignKey(
        "sinpapel.Estado", on_delete=models.PROTECT, null=True
    )
    producto = models.ForeignKey(ProductoPrueba, on_delete=models.CASCADE, null=True)
    monto_solicitado = models.DecimalField(
        max_digits=12, decimal_places=2, null=True
    )

    expedientes = GenericRelation(
        "sinpapel.ExpedienteAdjunto",
        content_type_field="target_content_type",
        object_id_field="target_object_id",
    )

    def save(self, *args, **kwargs):
        # Espejo del host: Solicitud NO valida metadatos en save() — la
        # validación vive en el endpoint PATCH /metadatos/. Bypass del
        # save() estricto de MetadatosCapturables.
        models.Model.save(self, *args, **kwargs)

    def resolve_workflow_version(self):
        if self.producto_id:
            pvf = (
                ProductoVersionFlujoPrueba.objects.filter(producto=self.producto)
                .select_related("flujo")
                .first()
            )
            if pvf:
                return pvf.flujo
        from sinpapel.models import VersionFlujo

        return VersionFlujo.objects.filter(activo=True).first()

    class Meta:
        app_label = "tests"
