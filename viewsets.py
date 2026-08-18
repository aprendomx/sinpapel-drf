"""sinpapel-drf — WorkflowViewSet full implementation (S13.5 + S13.6).

3 actions completas:
- available_transitions (GET) → EstadoSerializer many=True (D5: lista plana)
- transition (POST) → TransitionRequestSerializer + signature dispatch (S13.6)
- history (GET) → HistoryEntrySerializer + PageNumberPagination (D4)

S13.6 signature dispatch (D-discr + D-parser + D-engine-passthrough):
- fiel/client-side: JSON body → viewset invoca FielBackend.request_signature
  (verifica RSA + cadena) → engine recibe {"registro_firma_id": rf.id}
- fiel/server-side: multipart → viewset invoca FielBackend.sign_server_side
  → engine recibe firma_payload={"registro_firma_id": rf.id}
- manual/fake: JSON body → viewset invoca el backend correspondiente → engine
  recibe firma_payload={"registro_firma_id": rf.id}

Todas las ramas usan Modo B del engine (registro pre-creado, validado por
el core 0.8: pertenencia al usuario, estado válido, no-reuso), preservando
el polimorfismo por request con independencia de SINPAPEL_SIGNATURE_BACKEND.

Error mapping (S13.5 D3 + S13.6 extension):
- ValueError → DRF ValidationError (400)
- PermissionError → DRF PermissionDenied (403)
- SignatureValidationError → DRF ValidationError (400)
- SignatureBackendNotConfiguredError → DRF ValidationError (400)

S13.6 D-perm: NO custom GruposPermitidosPermission — engine puede_cambiar_estado
enforces grupos_permitidos vía PermissionError → 403 (mapping reuse).
"""
from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
from typing import TYPE_CHECKING

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from sinpapel.signing.exceptions import (
    SignatureBackendNotConfiguredError,
    SignatureValidationError,
)
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


def _canonicalize_for_signing(target_state: str, instance_id: int, user_id: int) -> bytes:
    """Construye contenido canónico determinista para firma.

    Algorithm: JSON sort_keys + separators sin whitespace + UTF-8 encoded.
    Mismo approach que EphemeralFirmaService canónico (PAT-J-023).
    """
    return json.dumps(
        {
            "instance_id": instance_id,
            "target_state": target_state,
            "user_id": user_id,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _build_firma_payload_for_engine(
    sig_data: dict, target_state: str, instance, user
) -> dict:
    """Despacha al backend apropiado y retorna firma_payload para engine.

    Modo A (fiel/client-side) → dict con verify-fields (engine verifica + persiste).
    Modo B (fiel/server-side) → invoca FielBackend.sign_server_side, retorna
                                {"registro_firma_id": rf.id}.
    Manual/Fake → invoca backend, retorna {"registro_firma_id": rf.id}.
    """
    backend_name = sig_data["backend"]
    mode = sig_data.get("mode", "client-side")

    if backend_name == "fiel" and mode == "server-side":
        from sinpapel.signing.backends.fiel import FielBackend
        content = _canonicalize_for_signing(target_state, instance.pk, user.id)
        # `sig_data` viene del serializer ya validado — files son UploadedFile
        cer_bytes = sig_data["cer_file"].read()
        key_bytes = sig_data["key_file"].read()
        password = sig_data["password"].encode("utf-8")
        rf = FielBackend().sign_server_side(
            content=content, signer=user,
            cer_bytes=cer_bytes, key_bytes=key_bytes, password=password,
        )
        return {"registro_firma_id": rf.id}

    elif backend_name == "fiel":  # client-side
        # 0.4.5: el viewset invoca FielBackend directamente y pasa Modo B,
        # igual que las demás ramas. Antes se pasaba Modo A (verify-fields)
        # confiando en que el engine instanciaba FielBackend hardcodeado;
        # desde sinpapel 0.8.0 el Modo A usa el backend CONFIGURADO
        # (SINPAPEL_SIGNATURE_BACKEND) — un proyecto con default manual
        # habría firmado "fiel" con ManualBackend silenciosamente.
        from sinpapel.signing.backends.fiel import FielBackend
        rf = FielBackend().request_signature(
            content=_canonicalize_for_signing(
                target_state, instance.pk, user.id
            ),
            signer=user,
            firma_b64=sig_data["firma_b64"],
            certificado_cer_b64=sig_data["certificado_cer_b64"],
        )
        return {"registro_firma_id": rf.id}

    elif backend_name == "manual":
        from sinpapel.signing.backends.manual import ManualBackend
        content = _canonicalize_for_signing(target_state, instance.pk, user.id)
        rf = ManualBackend().request_signature(
            content=content, signer=user,
            scanned_image_path=sig_data["scanned_image_path"],
            witness_name=sig_data["witness_name"],
        )
        return {"registro_firma_id": rf.id}

    else:  # fake
        from sinpapel.signing.backends.fake import FakeBackend
        content = _canonicalize_for_signing(target_state, instance.pk, user.id)
        rf = FakeBackend().request_signature(content=content, signer=user)
        return {"registro_firma_id": rf.id}


def _attach_documentos_disponibles(requisitos: list[dict]) -> list[dict]:
    """Adjunta a cada `requisito_documento` las opciones de `Documento` de su
    tipo (``[{id, nombre}]``), para poblar un ``<select>`` dependiente en el
    cliente. Un tipo (ej. "Identificación") puede tener varios Documento
    (ej. "Pasaporte", "INE") y el usuario elige cuál sube.

    No-op sobre los items que no son `requisito_documento`. Una sola query.
    """
    from sinpapel.models import Documento

    tipo_ids = [
        r["tipo_documento_id"]
        for r in requisitos
        if r.get("nivel") == "requisito_documento" and r.get("tipo_documento_id")
    ]
    if not tipo_ids:
        return requisitos

    docs_por_tipo: dict[int, list[dict]] = {}
    for d in Documento.objects.filter(tipo_documento_id__in=tipo_ids).values(
        "id", "nombre", "tipo_documento_id"
    ):
        docs_por_tipo.setdefault(d["tipo_documento_id"], []).append(
            {"id": d["id"], "nombre": d["nombre"]}
        )

    for r in requisitos:
        if r.get("nivel") == "requisito_documento":
            r["documentos_disponibles"] = docs_por_tipo.get(
                r.get("tipo_documento_id"), []
            )
    return requisitos


def _seguimiento_to_history_entry(seg) -> SimpleNamespace:
    """Mapea un `SeguimientoWorkflow` a la MISMA forma que un HistoricalRecord
    de django-simple-history, para reusar `HistoryEntrySerializer` sin cambios.

    - `history_type`: '+' si es la entrada de creación (`estado_anterior` None),
      '~' si es una transición entre estados.
    - `history_change_reason`: "ANTERIOR → NUEVO" (o solo "NUEVO" en la
      creación), con los `comentarios` de la transición adjuntos tras un guión.
    - `history_user`: el `usuario_accion` (objeto con `.username`, como espera
      el serializer vía `source="history_user.username"`).
    """
    anterior = seg.estado_anterior.nombre if seg.estado_anterior_id else None
    nuevo = seg.estado_nuevo.nombre
    reason = f"{anterior} → {nuevo}" if anterior else nuevo
    if seg.comentarios:
        reason = f"{reason} — {seg.comentarios}"
    return SimpleNamespace(
        history_id=seg.pk,
        history_type="~" if anterior else "+",
        history_date=seg.fecha_accion,
        history_user=seg.usuario_accion,
        history_change_reason=reason,
    )


def _seguimiento_history(instance) -> list:
    """Audit trail de transiciones (`SeguimientoWorkflow`) de `instance`, más
    reciente primero, mapeado a la forma de `HistoryEntrySerializer`.

    Fuente de *fallback* de `GET /history/` para modelos workflow-enabled que
    heredan solo de `Trazable` y NO declaran `HistoricalRecords` (no tienen
    `instance.history`). Scoping por la GFK `target` (content_type + object_id).
    """
    from django.contrib.contenttypes.models import ContentType
    from sinpapel.models import SeguimientoWorkflow

    ct = ContentType.objects.get_for_model(type(instance))
    seguimientos = (
        SeguimientoWorkflow.objects.filter(
            target_content_type=ct, target_object_id=instance.pk
        )
        .select_related("estado_anterior", "estado_nuevo", "usuario_accion")
        .order_by("-fecha_accion")
    )
    return [_seguimiento_to_history_entry(s) for s in seguimientos]


class WorkflowViewSet(GenericViewSet):
    """Auto-instantiated ViewSet via SinpapelRouter.

    S13.6: full implementation con signature dispatch polimórfico.
    Permission stub IsAuthenticated; grupos_permitidos enforce vía engine
    PermissionError → 403 (D-perm: skip custom DRF permission class).
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

    @action(
        detail=True, methods=["post"],
        parser_classes=[JSONParser, MultiPartParser, FormParser],
    )
    def transition(self, request, pk=None):
        """POST .../transition/ → ejecuta transición + retorna info en 201.

        S13.6: parser_classes mixto soporta JSON (modo A/manual/fake) y
        multipart (modo B server-side con cer/key files). Signature dispatch
        polimórfico vía SignatureRequestSerializer + _build_firma_payload_for_engine.
        """
        instance = self.get_object()

        req_serializer = TransitionRequestSerializer(data=request.data)
        req_serializer.is_valid(raise_exception=True)
        validated = req_serializer.validated_data

        # S13.6: dispatch signature al backend apropiado (si presente)
        firma_payload = None
        signature_data = validated.get("signature")
        if signature_data:
            try:
                firma_payload = _build_firma_payload_for_engine(
                    signature_data,
                    target_state=validated["target_state"],
                    instance=instance,
                    user=request.user,
                )
            except (SignatureValidationError, SignatureBackendNotConfiguredError) as e:
                raise ValidationError({"signature": [str(e)]})

        try:
            result_dict = instance.transition(
                target_state_name=validated["target_state"],
                user=request.user,
                comentarios=validated.get("comentarios", ""),
                condiciones=validated.get("condiciones"),
                firma_payload=firma_payload,
            )
        except PermissionError as e:
            # D3/D-perm: engine raises PermissionError para target inexistente,
            # transición no válida, grupos no permitidos → 403.
            raise PermissionDenied(detail=str(e))
        except (ValueError, SignatureValidationError) as e:
            raise ValidationError({"detail": [str(e)]})

        resp_serializer = TransitionResponseSerializer(result_dict)
        return Response(resp_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        """GET .../history/ → audit trail paginated (D4: 10/100).

        Fuente:
        - Si el modelo declara `HistoricalRecords` (django-simple-history),
          sirve `instance.history` (comportamiento original, sin cambios).
        - Si NO (modelo workflow-enabled que solo hereda de `Trazable`), hace
          fallback al audit trail de transiciones desde `SeguimientoWorkflow`,
          mapeado a la misma forma de respuesta. Antes el endpoint atrapaba el
          `AttributeError` de `instance.history` y devolvía `[]` en silencio,
          ocultando transiciones reales — el consumidor mostraba "sin
          movimientos" pese a que el estado sí había cambiado.
        """
        instance = self.get_object()
        historical = getattr(instance, "history", None)
        if historical is not None and hasattr(historical, "all"):
            queryset = list(historical.all())
        else:
            queryset = _seguimiento_history(instance)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = HistoryEntrySerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = HistoryEntrySerializer(queryset, many=True)
        return Response(serializer.data)

    @action(
        detail=True, methods=["post"], url_path="preview-transition",
    )
    def preview_transition(self, request, pk=None):
        """POST .../preview-transition/ — simulate transition + return impact report.

        Reusa WorkflowEngine.preview_transition(instance, target, user). NO muta.
        Bloqueos vienen en `permitido=false` + `razones_bloqueo`. NO ejecuta
        side-effects ni dispara firmas.

        NOTA: el decorador @workflow_enabled (sinpapel >=0.5.1) NO inyecta
        `preview_transition` en la instancia (solo available_transitions /
        can_transition_to / transition). Invocar instance.preview_transition
        levantaba AttributeError → HTTP 500. Se llama al engine directamente.
        """
        from sinpapel.services.workflow_engine import WorkflowEngine
        from sinpapel_drf.serializers import (
            PreviewTransitionRequestSerializer,
            PreviewTransitionResponseSerializer,
        )

        instance = self.get_object()

        req = PreviewTransitionRequestSerializer(data=request.data)
        req.is_valid(raise_exception=True)

        report = WorkflowEngine().preview_transition(
            instance,
            req.validated_data["target_state"],
            request.user,
        )
        resp = PreviewTransitionResponseSerializer(report)
        return Response(resp.data)

    @action(detail=True, methods=["get", "patch"], url_path="metadatos")
    def metadatos(self, request, pk=None):
        """GET / PATCH .../metadatos/ — captura estructurada via MetadatosCapturables.

        GET → {schema: [...], values: {...}}.
        PATCH → partial update validado via factory-built serializer.
        """
        from sinpapel_drf.metadata_views import (
            campo_to_dict, get_meta_serializer_class,
        )

        instance = self.get_object()
        model_cls = type(instance)
        schema = list(getattr(model_cls, "SCHEMA_METADATOS", []))

        if request.method == "GET":
            try:
                values = instance.meta.to_dict()
            except AttributeError:
                # Modelo sin MetadatosCapturables — devuelve values vacíos
                values = {}
            return Response({
                "schema": [campo_to_dict(c) for c in schema],
                "values": values,
            })

        # PATCH
        allowed_keys = {c.nombre for c in schema}
        unknown = set(request.data.keys()) - allowed_keys
        if unknown:
            raise ValidationError(
                {k: ["Campo no definido en SCHEMA_METADATOS"] for k in unknown}
            )

        Serializer = get_meta_serializer_class(model_cls)
        s = Serializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)

        try:
            for key, value in s.validated_data.items():
                setattr(instance.meta, key, value)
            instance.save()
        except (TypeError, ValueError) as exc:
            raise ValidationError({"detail": [str(exc)]})
        except DjangoValidationError as exc:
            raise ValidationError(
                getattr(exc, "message_dict", {"detail": list(exc.messages)})
            )

        return Response(instance.meta.to_dict())

    @action(
        detail=True, methods=["get", "post"], url_path="documentos",
        parser_classes=[JSONParser, MultiPartParser, FormParser],
    )
    def documentos(self, request, pk=None):
        """GET lista / POST sube InstanciaDocumento del trámite (carga typed)."""
        from django.contrib.contenttypes.models import ContentType
        from sinpapel.models import InstanciaDocumento
        from sinpapel_drf.serializers import (
            InstanciaDocumentoSerializer,
            InstanciaDocumentoUploadSerializer,
        )

        instance = self.get_object()
        ct = ContentType.objects.get_for_model(type(instance))

        if request.method == "GET":
            qs = (
                InstanciaDocumento.objects.filter(
                    target_content_type=ct, target_object_id=instance.pk
                )
                .select_related("documento", "documento__tipo_documento")
                .order_by("-creado")
            )
            return Response(InstanciaDocumentoSerializer(qs, many=True).data)

        # POST
        s = InstanciaDocumentoUploadSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        inst = InstanciaDocumento.objects.create(
            documento=data["documento_obj"],
            target=instance,
            archivo=data["archivo"],
            porcentaje=data.get("porcentaje", 100),
            metadatos=data.get("metadatos") or {},
            autor=request.user,
            modificador=request.user,
        )
        return Response(
            InstanciaDocumentoSerializer(inst).data,
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True, methods=["delete"],
        url_path=r"documentos/(?P<doc_id>[0-9]+)",
    )
    def documento_detail(self, request, pk=None, doc_id=None):
        """DELETE un InstanciaDocumento, solo si pertenece al trámite."""
        from django.contrib.contenttypes.models import ContentType
        from rest_framework.exceptions import NotFound
        from sinpapel.models import InstanciaDocumento

        instance = self.get_object()
        ct = ContentType.objects.get_for_model(type(instance))
        try:
            inst = InstanciaDocumento.objects.get(
                pk=doc_id, target_content_type=ct, target_object_id=instance.pk
            )
        except InstanciaDocumento.DoesNotExist:
            raise NotFound("Documento no encontrado para este trámite.")
        inst.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"], url_path="requisitos")
    def requisitos(self, request, pk=None):
        """GET requisitos documentales del estado actual + cumplimiento."""
        from sinpapel.services.workflow_engine import WorkflowEngine
        from sinpapel_drf.serializers import RequisitoStatusSerializer

        instance = self.get_object()
        data = WorkflowEngine().evaluar_requisitos_documentales(instance)
        data = _attach_documentos_disponibles(data)
        return Response(RequisitoStatusSerializer(data, many=True).data)

    @action(
        detail=True, methods=["post"], url_path="sla-status",
        permission_classes=[IsAdminUser],
    )
    def sla_status(self, request, pk=None):
        """POST .../sla-status/ — evaluate SLA per-instance.

        Wraps SLAEngine.evaluar_instancia(). May mutate the instance (the
        `alertar` action sets fields), hence POST + IsAdminUser.
        Returns list of actions executed, or [] if not expired / no SLAs apply.
        """
        from sinpapel.services.sla_engine import SLAEngine
        instance = self.get_object()
        result = SLAEngine.evaluar_instancia(instance)
        return Response(result)


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


# Backward compat — hashlib mantenido para tests legacy que lo importen
_ = hashlib  # noqa: B018 — preservado para imports externos potenciales
