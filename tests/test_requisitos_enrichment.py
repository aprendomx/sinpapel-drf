"""Unit tests de `_attach_documentos_disponibles` — opciones de Documento por
tipo para el <select> dependiente del cliente (v0.4.0).

NOT runnable in this workspace (no creditos host). Verificado vía el harness
autocontenido junto al resto de la suite de documentos.
"""
from __future__ import annotations

import pytest

from sinpapel_drf.viewsets import _attach_documentos_disponibles


@pytest.fixture
def identificacion(db):
    """Tipo "Identificación" con dos Documento: Pasaporte e INE."""
    from sinpapel.models import Documento, TipoDocumento
    td = TipoDocumento.objects.create(nombre="Identificación")
    pasaporte = Documento.objects.create(
        nombre="Pasaporte", tipo_documento=td, valor="PAS"
    )
    ine = Documento.objects.create(nombre="INE", tipo_documento=td, valor="INE")
    return td, pasaporte, ine


@pytest.mark.django_db
def test_adjunta_opciones_de_documento_por_tipo(identificacion):
    td, pasaporte, ine = identificacion
    requisitos = [
        {
            "nivel": "requisito_documento",
            "tipo_documento": "Identificación",
            "tipo_documento_id": td.pk,
            "porcentaje_requerido": 100,
            "porcentaje_actual": 0,
            "satisfecho": False,
        }
    ]

    out = _attach_documentos_disponibles(requisitos)

    opciones = out[0]["documentos_disponibles"]
    ids = sorted(o["id"] for o in opciones)
    nombres = sorted(o["nombre"] for o in opciones)
    assert ids == sorted([pasaporte.pk, ine.pk])
    assert nombres == ["INE", "Pasaporte"]


@pytest.mark.django_db
def test_no_toca_items_de_nivel_expediente(identificacion):
    requisitos = [
        {"nivel": "expediente", "satisfecho": False, "mensaje": "Falta expediente."}
    ]
    out = _attach_documentos_disponibles(requisitos)
    assert "documentos_disponibles" not in out[0]


@pytest.mark.django_db
def test_tipo_sin_documento_da_lista_vacia(db):
    from sinpapel.models import TipoDocumento
    td = TipoDocumento.objects.create(nombre="CURP")
    requisitos = [
        {
            "nivel": "requisito_documento",
            "tipo_documento": "CURP",
            "tipo_documento_id": td.pk,
            "satisfecho": False,
        }
    ]
    out = _attach_documentos_disponibles(requisitos)
    assert out[0]["documentos_disponibles"] == []


def test_sin_requisitos_documentales_es_noop():
    requisitos = [{"nivel": "expediente", "satisfecho": True}]
    assert _attach_documentos_disponibles(requisitos) is requisitos
