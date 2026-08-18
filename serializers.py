"""sinpapel-drf — Serializers para WorkflowViewSet endpoints.

S13.5: serializers básicos.
S13.6: SignatureRequestSerializer polimórfico (FIEL dual mode + manual + fake).

D1: TransitionResponseSerializer mapea dict que retorna
WorkflowEngine.cambiar_estado() (no es un Model).
D2 (resuelto S13.6): TransitionRequestSerializer ahora incluye signature
nested polimórfico opcional.
D9: HistoryEntrySerializer.history_user nullable (mutaciones sin
HistoryRequestMiddleware retornan None).
D10: serializers.Serializer (no ModelSerializer) — inputs/outputs son
shapes, no Models. HistoricalRecord es runtime-generated class.

S13.6 D-discr: SignatureRequestSerializer dispatch via to_internal_value()
por (backend, mode). Sub-serializers internos definen campos required
por modo. Schema OpenAPI auto-generated puede no ser perfecto pero KISS.

S13.6 D-perm: NO custom DRF permission class — engine puede_cambiar_estado
enforces grupos_permitidos vía PermissionError → S13.5 D3 mapping → 403.
"""
from __future__ import annotations

from rest_framework import serializers


class EstadoSerializer(serializers.Serializer):
    """Estado destino para available_transitions response."""

    id = serializers.IntegerField()
    nombre = serializers.CharField()
    color = serializers.CharField(default="", allow_blank=True, required=False)


class FielClientSideSerializer(serializers.Serializer):
    """Modo A — backend=fiel + mode=client-side. JSON body."""

    backend = serializers.CharField(required=True)  # "fiel"
    mode = serializers.CharField(required=False, default="client-side")
    firma_b64 = serializers.CharField(required=True, allow_blank=False)
    certificado_cer_b64 = serializers.CharField(required=True, allow_blank=False)


class FielServerSideSerializer(serializers.Serializer):
    """Modo B — backend=fiel + mode=server-side. multipart/form-data body.

    Gated por SINPAPEL_ALLOW_SERVER_SIGNING=True (ADR-012). password y
    key_file/cer_file marcados write_only=True (no leakean en response).
    """

    backend = serializers.CharField(required=True)
    mode = serializers.CharField(required=True)  # "server-side"
    cer_file = serializers.FileField(required=True, write_only=True)
    key_file = serializers.FileField(required=True, write_only=True)
    password = serializers.CharField(
        required=True, write_only=True, allow_blank=False
    )


class ManualSignatureSerializer(serializers.Serializer):
    """Manual — escaneo + testigo."""

    backend = serializers.CharField(required=True)  # "manual"
    scanned_image_path = serializers.CharField(required=True, allow_blank=False)
    witness_name = serializers.CharField(required=True, allow_blank=False)


class FakeSignatureSerializer(serializers.Serializer):
    """Fake — tests only, no kwargs."""

    backend = serializers.CharField(required=True)  # "fake"


class SignatureRequestSerializer(serializers.Serializer):
    """Polimórfico discriminated union por (backend, mode).

    Dispatch en to_internal_value(): selecciona sub-serializer apropiado y
    delega validation. Modo B (fiel + server-side) gated por
    SINPAPEL_ALLOW_SERVER_SIGNING=True.
    """

    backend = serializers.ChoiceField(
        choices=[("fiel", "fiel"), ("manual", "manual"), ("fake", "fake")],
        required=True,
    )

    def to_internal_value(self, data):
        # Dispatch sub-serializer por (backend, mode)
        backend = data.get("backend")
        mode = data.get("mode", "client-side")  # default modo A

        if backend not in ("fiel", "manual", "fake"):
            raise serializers.ValidationError({
                "backend": [f"'{backend}' is not a valid choice."]
            })

        if backend == "fiel":
            if mode == "server-side":
                from django.conf import settings
                if not getattr(settings, "SINPAPEL_ALLOW_SERVER_SIGNING", False):
                    raise serializers.ValidationError({
                        "mode": [
                            "Server-side signing is disabled. Set "
                            "SINPAPEL_ALLOW_SERVER_SIGNING=True (with legal review)."
                        ]
                    })
                sub_cls = FielServerSideSerializer
            else:
                sub_cls = FielClientSideSerializer
        elif backend == "manual":
            sub_cls = ManualSignatureSerializer
        else:  # fake
            sub_cls = FakeSignatureSerializer

        sub = sub_cls(data=data)
        sub.is_valid(raise_exception=True)
        return dict(sub.validated_data)


class TransitionRequestSerializer(serializers.Serializer):
    """Request body para POST /transition/.

    S13.6: extendido con `signature` nested polimórfico opcional.
    """

    target_state = serializers.CharField(required=True, allow_blank=False)
    comentarios = serializers.CharField(
        required=False, allow_blank=True, default=""
    )
    condiciones = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, default=None
    )
    signature = SignatureRequestSerializer(required=False, allow_null=True)


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


# ── v0.2.0: Preview transition serializers ─────────────────────────────────


class PreviewTransitionRequestSerializer(serializers.Serializer):
    """Request body para POST /<res>/<pk>/preview-transition/."""

    target_state = serializers.CharField(required=True, allow_blank=False)


class PreviewTransitionResponseSerializer(serializers.Serializer):
    """Response shape de WorkflowEngine.preview_transition().

    Mapea el dict retornado por engine.preview_transition() — no es un Model.
    """

    permitido = serializers.BooleanField()
    razones_bloqueo = serializers.ListField(child=serializers.DictField())
    documentos_faltantes = serializers.ListField(child=serializers.DictField())
    predicados_fallidos = serializers.ListField(child=serializers.DictField())
    aprobadores_requeridos = serializers.ListField(child=serializers.DictField())
    side_effects = serializers.ListField(child=serializers.CharField())
    historial_reciente = serializers.ListField(child=serializers.DictField())
    # sinpapel 0.8.0: la transición exigirá firma_payload (la UI debe pedir
    # firma antes de ejecutar). Default False para engines pre-0.8.
    firma_requerida = serializers.BooleanField(default=False)


# ── v0.2.0: Metadatos schema serializer ────────────────────────────────────


class CampoMetadatoSerializer(serializers.Serializer):
    """Readonly serializer for one CampoMetadato — used in GET /metadatos/ schema."""

    nombre = serializers.CharField()
    tipo = serializers.CharField()  # "str" | "int" | "bool" | "Decimal" | "date"
    requerido = serializers.BooleanField()
    default = serializers.JSONField(allow_null=True)
    choices = serializers.ListField(
        child=serializers.CharField(), allow_null=True, required=False,
    )
    etiqueta = serializers.CharField(allow_blank=True)
    ayuda = serializers.CharField(allow_blank=True)


# ── v0.2.0: CondicionTransicion ModelSerializer ────────────────────────────


class CondicionTransicionSerializer(serializers.ModelSerializer):
    """Serializer para CRUD de CondicionTransicion (predicados de transición)."""

    class Meta:
        from sinpapel.models import CondicionTransicion as _Model
        model = _Model
        fields = "__all__"


# ── v0.2.0: SLAConfiguracion ModelSerializer ────────────────────────────────


class SLAConfiguracionSerializer(serializers.ModelSerializer):
    """Serializer para CRUD de SLAConfiguracion (timers / SLA por estado)."""

    class Meta:
        from sinpapel.models import SLAConfiguracion as _Model
        model = _Model
        fields = "__all__"


# ── v0.3.0: carga + validación de documentos (InstanciaDocumento) ───────────


class InstanciaDocumentoSerializer(serializers.Serializer):
    """Read serializer para InstanciaDocumento (listado + respuesta de carga)."""

    id = serializers.IntegerField(read_only=True)
    documento = serializers.IntegerField(source="documento_id", allow_null=True)
    tipo_documento = serializers.CharField(
        source="documento.tipo_documento.nombre",
        allow_null=True,
        required=False,
    )
    archivo = serializers.FileField(allow_null=True, required=False)
    porcentaje = serializers.IntegerField()
    creado = serializers.DateTimeField(allow_null=True)


class InstanciaDocumentoUploadSerializer(serializers.Serializer):
    """Write serializer para POST /documentos/.

    Acepta `documento` (PK) o `tipo_documento` (PK). Resuelve el Documento y lo
    deja en validated_data["documento_obj"]. Regla por tipo: exactamente 1
    Documento del tipo → se usa; 0 o >1 → error (pedir `documento` explícito).
    """

    archivo = serializers.FileField(required=True)
    documento = serializers.IntegerField(required=False, allow_null=True)
    tipo_documento = serializers.IntegerField(required=False, allow_null=True)
    porcentaje = serializers.IntegerField(
        required=False, default=100, min_value=0, max_value=100
    )
    metadatos = serializers.JSONField(required=False, default=dict)

    def validate(self, attrs):
        from sinpapel.models import Documento

        doc_pk = attrs.get("documento")
        tipo_pk = attrs.get("tipo_documento")
        if not doc_pk and not tipo_pk:
            raise serializers.ValidationError(
                "Debe enviar 'documento' o 'tipo_documento'."
            )
        if doc_pk:
            try:
                documento = Documento.objects.get(pk=doc_pk)
            except Documento.DoesNotExist:
                raise serializers.ValidationError(
                    {"documento": "Documento inexistente."}
                )
        else:
            qs = Documento.objects.filter(tipo_documento_id=tipo_pk)
            n = qs.count()
            if n == 0:
                raise serializers.ValidationError(
                    {"tipo_documento": "No hay Documento de ese tipo; envíe 'documento'."}
                )
            if n > 1:
                raise serializers.ValidationError(
                    {"tipo_documento": "Hay varios Documento de ese tipo; envíe 'documento'."}
                )
            documento = qs.first()
        attrs["documento_obj"] = documento
        return attrs


class RequisitoStatusSerializer(serializers.Serializer):
    """Mapea la forma de WorkflowEngine.evaluar_requisitos_documentales()."""

    nivel = serializers.CharField()
    tipo_documento = serializers.CharField(allow_null=True, required=False)
    tipo_documento_id = serializers.IntegerField(allow_null=True, required=False)
    porcentaje_requerido = serializers.IntegerField(allow_null=True, required=False)
    porcentaje_actual = serializers.IntegerField(allow_null=True, required=False)
    satisfecho = serializers.BooleanField()
    auto_carga = serializers.BooleanField(required=False, default=False)
    mensaje = serializers.CharField(allow_blank=True, required=False)
    # v0.4.0: opciones de Documento (id + nombre) del tipo del requisito, para
    # poblar un <select> dependiente en el cliente (ej. tipo "Identificación" →
    # ["Pasaporte", "INE"]). El engine no lo provee; lo adjunta el viewset.
    documentos_disponibles = serializers.ListField(
        child=serializers.DictField(), required=False, default=list,
    )
