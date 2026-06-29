"""Unit tests puros para el mapeo SeguimientoWorkflow → forma HistoryEntry.

No tocan DB ni dependen del proyecto host (`creditos`): ejercitan
`_seguimiento_to_history_entry` con objetos fake que imitan los atributos de
un SeguimientoWorkflow. Verifican la lógica propensa a error (history_type
'+'/'~', change_reason 'A → B' + comentarios) de forma aislada.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from sinpapel_drf.viewsets import _seguimiento_to_history_entry


def _fake_seg(*, pk, estado_anterior, estado_nuevo, comentarios="", usuario="u1"):
    """Construye un objeto con la misma interfaz de atributos que usa el mapeo."""
    anterior_ns = (
        SimpleNamespace(nombre=estado_anterior) if estado_anterior else None
    )
    return SimpleNamespace(
        pk=pk,
        estado_anterior_id=(1 if estado_anterior else None),
        estado_anterior=anterior_ns,
        estado_nuevo=SimpleNamespace(nombre=estado_nuevo),
        usuario_accion=SimpleNamespace(username=usuario),
        fecha_accion=datetime(2026, 4, 28, 12, 0, tzinfo=timezone.utc),
        comentarios=comentarios,
    )


def test_creation_entry_is_plus_and_reason_is_new_state():
    """estado_anterior None → history_type '+' y reason = solo el estado nuevo."""
    seg = _fake_seg(pk=7, estado_anterior=None, estado_nuevo="CAPTURA")
    entry = _seguimiento_to_history_entry(seg)
    assert entry.history_id == 7
    assert entry.history_type == "+"
    assert entry.history_change_reason == "CAPTURA"
    assert entry.history_user.username == "u1"


def test_modification_entry_is_tilde_and_reason_is_arrow():
    """estado_anterior presente → history_type '~' y reason 'A → B'."""
    seg = _fake_seg(pk=8, estado_anterior="CAPTURA", estado_nuevo="EN_REVISION")
    entry = _seguimiento_to_history_entry(seg)
    assert entry.history_type == "~"
    assert entry.history_change_reason == "CAPTURA → EN_REVISION"


def test_comentarios_appended_after_arrow():
    seg = _fake_seg(
        pk=9, estado_anterior="A", estado_nuevo="B", comentarios="ok por monto",
    )
    entry = _seguimiento_to_history_entry(seg)
    assert entry.history_change_reason == "A → B — ok por monto"


def test_history_date_passthrough():
    seg = _fake_seg(pk=10, estado_anterior="A", estado_nuevo="B")
    entry = _seguimiento_to_history_entry(seg)
    assert entry.history_date == seg.fecha_accion
