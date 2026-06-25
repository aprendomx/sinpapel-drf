"""sinpapel-drf — WorkflowViewSet full implementation (S13.5 + S13.6).

3 actions completas:
- available_transitions (GET) → EstadoSerializer many=True (D5: lista plana)
- transition (POST) → TransitionRequestSerializer + signature dispatch (S13.6)
- history (GET) → HistoryEntrySerializer + PageNumberPagination (D4)

S13.6 signature dispatch (D-discr + D-parser + D-engine-passthrough):
- Modo A (fiel/client-side): JSON body → engine recibe firma_payload con verify-fields
- Modo B (fiel/server-side): multipart → viewset invoca FielBackend.sign_server_side
  → engine recibe firma_payload={"registro_firma_id": rf.id}
- manual/fake: JSON body → viewset invoca el backend correspondiente → engine
  recibe firma_payload={"registro_firma_id": rf.id}

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
        # Engine verifica via FielBackend.request_signature
        # firma_b64 viene base64 del cliente; cer_b64 también.
        return {
            "contenido": _canonicalize_for_signing(
                target_state, instance.pk, user.id
            ),
            "firma_b64": sig_data["firma_b64"],
            "certificado_cer_b64": sig_data["certificado_cer_b64"],
        }

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
                monto_aprobado=validated.get("monto_aprobado"),
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
