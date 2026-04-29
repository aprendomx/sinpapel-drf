"""S13.5 — Unit tests para serializers básicos.

Cubre validation de inputs (TransitionRequestSerializer) + shape de outputs
(EstadoSerializer, TransitionResponseSerializer, HistoryEntrySerializer).
Sin DB ni APIClient — pure serializer behavior.
"""
from __future__ import annotations

from decimal import Decimal

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
        "monto_aprobado": "1500.00",
        "condiciones": "Pago a 12 meses",
    })
    assert s.is_valid(), s.errors
    assert s.validated_data["monto_aprobado"] == Decimal("1500.00")
    assert s.validated_data["condiciones"] == "Pago a 12 meses"
    assert s.validated_data["comentarios"] == "OK"


def test_transition_request_monto_aprobado_optional_null():
    s = TransitionRequestSerializer(data={
        "target_state": "RECHAZADO", "monto_aprobado": None,
    })
    assert s.is_valid(), s.errors
    assert s.validated_data.get("monto_aprobado") is None


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
