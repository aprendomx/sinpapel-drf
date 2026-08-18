"""S13.5 — Unit tests para serializers básicos.

Cubre validation de inputs (TransitionRequestSerializer) + shape de outputs
(EstadoSerializer, TransitionResponseSerializer, HistoryEntrySerializer).
Sin DB ni APIClient — pure serializer behavior.
"""
from __future__ import annotations

import pytest

from sinpapel_drf.serializers import (
    EstadoSerializer,
    HistoryEntrySerializer,
    TransitionRequestSerializer,
    TransitionResponseSerializer,
)


class _FakeEstado:
    """Stand-in mínimo para Estado output (sin DB)."""

    def __init__(self, id: int, nombre: str, color: str = ""):
        self.id = id
        self.nombre = nombre
        self.color = color


class _FakeUser:
    def __init__(self, username: str):
        self.username = username


class _FakeHistoryEntry:
    def __init__(self, history_id, history_type, history_date, history_user=None,
                 history_change_reason=None):
        self.history_id = history_id
        self.history_type = history_type
        self.history_date = history_date
        self.history_user = history_user
        self.history_change_reason = history_change_reason


# ─────────────────────────────────────────────────────────────────────────────
# EstadoSerializer
# ─────────────────────────────────────────────────────────────────────────────


def test_estado_serializer_outputs_id_nombre_color():
    estado = _FakeEstado(id=42, nombre="EN_REVISION", color="#abc")
    data = EstadoSerializer(estado).data
    assert data == {"id": 42, "nombre": "EN_REVISION", "color": "#abc"}


def test_estado_serializer_color_optional_empty():
    estado = _FakeEstado(id=1, nombre="INICIAL")
    data = EstadoSerializer(estado).data
    assert data["id"] == 1
    assert data["nombre"] == "INICIAL"
    assert data.get("color", "") == ""


def test_estado_serializer_many_returns_list():
    estados = [_FakeEstado(1, "A"), _FakeEstado(2, "B")]
    data = EstadoSerializer(estados, many=True).data
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["nombre"] == "A"
    assert data[1]["nombre"] == "B"


# ─────────────────────────────────────────────────────────────────────────────
# TransitionRequestSerializer
# ─────────────────────────────────────────────────────────────────────────────


def test_transition_request_target_state_required():
    s = TransitionRequestSerializer(data={})
    assert not s.is_valid()
    assert "target_state" in s.errors


def test_transition_request_target_state_blank_invalid():
    s = TransitionRequestSerializer(data={"target_state": ""})
    assert not s.is_valid()
    assert "target_state" in s.errors


def test_transition_request_minimal_valid():
    s = TransitionRequestSerializer(data={"target_state": "EN_REVISION"})
    assert s.is_valid(), s.errors
    assert s.validated_data["target_state"] == "EN_REVISION"


def test_transition_request_full_payload_valid():
    s = TransitionRequestSerializer(data={
        "target_state": "APROBADO",
        "comentarios": "OK",
        "condiciones": "Pago a 12 meses",
    })
    assert s.is_valid(), s.errors
    assert s.validated_data["condiciones"] == "Pago a 12 meses"
    assert s.validated_data["comentarios"] == "OK"


# ─────────────────────────────────────────────────────────────────────────────
# TransitionResponseSerializer
# ─────────────────────────────────────────────────────────────────────────────


def test_transition_response_maps_engine_dict():
    """D1: serializer mapea dict que retorna WorkflowEngine.cambiar_estado()."""
    engine_dict = {
        "success": True,
        "instance_id": 7,
        "estado_anterior": "INICIAL",
        "estado_nuevo": "EN_REVISION",
        "seguimiento_id": 99,
    }
    data = TransitionResponseSerializer(engine_dict).data
    assert data == engine_dict


def test_transition_response_estado_anterior_nullable():
    engine_dict = {
        "success": True,
        "instance_id": 1,
        "estado_anterior": None,
        "estado_nuevo": "INICIAL",
        "seguimiento_id": 1,
    }
    data = TransitionResponseSerializer(engine_dict).data
    assert data["estado_anterior"] is None
    assert data["estado_nuevo"] == "INICIAL"


# ─────────────────────────────────────────────────────────────────────────────
# HistoryEntrySerializer
# ─────────────────────────────────────────────────────────────────────────────


def test_history_entry_serializer_with_user():
    from datetime import datetime, timezone
    entry = _FakeHistoryEntry(
        history_id=1, history_type="+",
        history_date=datetime(2026, 4, 28, 12, 0, tzinfo=timezone.utc),
        history_user=_FakeUser("admin"),
        history_change_reason="Initial",
    )
    data = HistoryEntrySerializer(entry).data
    assert data["history_id"] == 1
    assert data["history_type"] == "+"
    assert data["history_user"] == "admin"
    assert data["history_change_reason"] == "Initial"


def test_history_entry_serializer_user_null_d9():
    """D9: history_user nullable cuando mutación ocurre sin HistoryRequestMiddleware."""
    from datetime import datetime, timezone
    entry = _FakeHistoryEntry(
        history_id=2, history_type="~",
        history_date=datetime(2026, 4, 28, 13, 0, tzinfo=timezone.utc),
        history_user=None,
    )
    data = HistoryEntrySerializer(entry).data
    assert data["history_id"] == 2
    assert data["history_user"] is None


# ─────────────────────────────────────────────────────────────────────────────
# S13.6 T3 — SignatureRequestSerializer polimórfico
# ─────────────────────────────────────────────────────────────────────────────


def test_signature_fiel_client_side_valid_input():
    """Modo A happy path: backend=fiel + mode=client-side + firma_b64 + cer_b64."""
    from sinpapel_drf.serializers import SignatureRequestSerializer

    s = SignatureRequestSerializer(data={
        "backend": "fiel",
        "mode": "client-side",
        "firma_b64": "ZmFrZQ==",
        "certificado_cer_b64": "Y2VydA==",
    })
    assert s.is_valid(), s.errors
    assert s.validated_data["firma_b64"] == "ZmFrZQ=="


def test_signature_fiel_client_side_default_mode():
    """Modo A default: si no se especifica mode, asume client-side."""
    from sinpapel_drf.serializers import SignatureRequestSerializer

    s = SignatureRequestSerializer(data={
        "backend": "fiel",
        "firma_b64": "ZmFrZQ==",
        "certificado_cer_b64": "Y2VydA==",
    })
    assert s.is_valid(), s.errors


def test_signature_fiel_client_side_missing_firma_b64():
    """Modo A: sin firma_b64 → 400 con error específico."""
    from sinpapel_drf.serializers import SignatureRequestSerializer

    s = SignatureRequestSerializer(data={
        "backend": "fiel",
        "mode": "client-side",
        "certificado_cer_b64": "Y2VydA==",
    })
    assert not s.is_valid()
    assert "firma_b64" in str(s.errors)


def test_signature_fiel_server_side_blocked_when_setting_false(settings):
    """Modo B con setting=False → error en mode field."""
    from sinpapel_drf.serializers import SignatureRequestSerializer
    settings.SINPAPEL_ALLOW_SERVER_SIGNING = False

    s = SignatureRequestSerializer(data={
        "backend": "fiel",
        "mode": "server-side",
        "cer_file": "fake_cer_data",
        "key_file": "fake_key_data",
        "password": "x",
    })
    assert not s.is_valid()
    err_str = str(s.errors)
    assert "Server-side signing is disabled" in err_str or "SINPAPEL_ALLOW_SERVER_SIGNING" in err_str


def test_signature_fiel_server_side_valid_with_setting_true(settings):
    """Modo B con setting=True acepta input (sin validar bytes)."""
    from sinpapel_drf.serializers import SignatureRequestSerializer
    from django.core.files.uploadedfile import SimpleUploadedFile
    settings.SINPAPEL_ALLOW_SERVER_SIGNING = True

    s = SignatureRequestSerializer(data={
        "backend": "fiel",
        "mode": "server-side",
        "cer_file": SimpleUploadedFile("c.cer", b"cert-bytes"),
        "key_file": SimpleUploadedFile("c.key", b"key-bytes"),
        "password": "test-pass",
    })
    assert s.is_valid(), s.errors


def test_signature_manual_valid_input():
    """Manual happy path: scanned_image_path + witness_name."""
    from sinpapel_drf.serializers import SignatureRequestSerializer

    s = SignatureRequestSerializer(data={
        "backend": "manual",
        "scanned_image_path": "/uploads/firma.png",
        "witness_name": "Lic. Pérez",
    })
    assert s.is_valid(), s.errors
    assert s.validated_data["witness_name"] == "Lic. Pérez"


def test_signature_fake_valid_no_kwargs():
    """Fake happy path: no kwargs requeridos."""
    from sinpapel_drf.serializers import SignatureRequestSerializer

    s = SignatureRequestSerializer(data={"backend": "fake"})
    assert s.is_valid(), s.errors


def test_signature_unknown_backend_returns_error():
    """Backend desconocido → 400."""
    from sinpapel_drf.serializers import SignatureRequestSerializer

    s = SignatureRequestSerializer(data={"backend": "totally-fake-backend"})
    assert not s.is_valid()
    assert "backend" in s.errors


def test_transition_request_with_nested_signature_fiel_client():
    """TransitionRequestSerializer extendido acepta signature nested."""
    from sinpapel_drf.serializers import TransitionRequestSerializer

    s = TransitionRequestSerializer(data={
        "target_state": "FIRMADO",
        "comentarios": "approved",
        "signature": {
            "backend": "fiel",
            "mode": "client-side",
            "firma_b64": "ZmFrZQ==",
            "certificado_cer_b64": "Y2VydA==",
        },
    })
    assert s.is_valid(), s.errors
    assert s.validated_data["signature"]["backend"] == "fiel"


def test_transition_request_signature_optional():
    """signature ausente sigue siendo válido (S13.5 backward compat)."""
    from sinpapel_drf.serializers import TransitionRequestSerializer

    s = TransitionRequestSerializer(data={"target_state": "EN_REVISION"})
    assert s.is_valid(), s.errors


# ── Task 1: Preview Transition serializers ────────────────────────────────

def test_preview_transition_request_requires_target_state():
    from sinpapel_drf.serializers import PreviewTransitionRequestSerializer

    s = PreviewTransitionRequestSerializer(data={})
    assert not s.is_valid()
    assert "target_state" in s.errors


def test_preview_transition_request_rejects_blank_target_state():
    from sinpapel_drf.serializers import PreviewTransitionRequestSerializer

    s = PreviewTransitionRequestSerializer(data={"target_state": ""})
    assert not s.is_valid()
    assert "target_state" in s.errors


def test_preview_transition_request_accepts_target_state():
    from sinpapel_drf.serializers import PreviewTransitionRequestSerializer

    s = PreviewTransitionRequestSerializer(data={"target_state": "Aprobado"})
    assert s.is_valid(), s.errors
    assert s.validated_data["target_state"] == "Aprobado"


def test_preview_transition_response_serializes_full_report():
    from sinpapel_drf.serializers import PreviewTransitionResponseSerializer

    report = {
        "permitido": True,
        "razones_bloqueo": [],
        "documentos_faltantes": [],
        "predicados_fallidos": [{"condicion_id": 1, "tipo": "json_logic", "mensaje": "x"}],
        "aprobadores_requeridos": [],
        "side_effects": ["Aprobado"],
        "historial_reciente": [{"fecha": "2026-01-01T00:00:00", "transicion": "A→B",
                                 "usuario": "alice", "comentarios": "c"}],
    }
    s = PreviewTransitionResponseSerializer(report)
    assert s.data["permitido"] is True
    assert s.data["side_effects"] == ["Aprobado"]
    assert s.data["predicados_fallidos"][0]["condicion_id"] == 1


def test_preview_transition_response_incluye_firma_requerida():
    """0.4.4: la key firma_requerida (sinpapel 0.8.0) pasa al response."""
    from sinpapel_drf.serializers import PreviewTransitionResponseSerializer

    base = {
        "permitido": True,
        "razones_bloqueo": [],
        "documentos_faltantes": [],
        "predicados_fallidos": [],
        "aprobadores_requeridos": [],
        "side_effects": [],
        "historial_reciente": [],
    }
    con_firma = PreviewTransitionResponseSerializer({**base, "firma_requerida": True})
    assert con_firma.data["firma_requerida"] is True

    # Engines pre-0.8 sin la key → default False, no KeyError
    sin_key = PreviewTransitionResponseSerializer(base)
    assert sin_key.data["firma_requerida"] is False
