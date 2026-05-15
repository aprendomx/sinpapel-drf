"""v0.2.0 — Unit tests for metadata_views helpers."""
from __future__ import annotations

from decimal import Decimal

import pytest

from sinpapel.mixins import CampoMetadato


def test_campo_to_dict_basic_str_field():
    from sinpapel_drf.metadata_views import campo_to_dict

    c = CampoMetadato(nombre="rfc", tipo=str, requerido=True, etiqueta="RFC")
    out = campo_to_dict(c)
    assert out == {
        "nombre": "rfc", "tipo": "str", "requerido": True,
        "default": None, "choices": None, "etiqueta": "RFC", "ayuda": "",
    }


def test_campo_to_dict_decimal_field():
    from sinpapel_drf.metadata_views import campo_to_dict

    c = CampoMetadato(nombre="monto", tipo=Decimal, default=Decimal("0"))
    out = campo_to_dict(c)
    assert out["tipo"] == "Decimal"
    assert out["default"] == "0"  # serialized


def test_campo_to_dict_with_choices():
    from sinpapel_drf.metadata_views import campo_to_dict

    c = CampoMetadato(nombre="nivel", tipo=str, choices=["A", "B"])
    out = campo_to_dict(c)
    assert out["choices"] == ["A", "B"]


def test_get_meta_serializer_class_returns_drf_serializer_class():
    from rest_framework import serializers
    from sinpapel_drf.metadata_views import get_meta_serializer_class

    class FakeModel:
        SCHEMA_METADATOS = [CampoMetadato(nombre="rfc", tipo=str, requerido=True)]

    Cls = get_meta_serializer_class(FakeModel)
    assert issubclass(Cls, serializers.Serializer)
    instance = Cls(data={"rfc": "ABCD010101ABC"})
    assert instance.is_valid(), instance.errors


def test_get_meta_serializer_class_is_cached():
    from sinpapel_drf.metadata_views import get_meta_serializer_class

    class FakeModel:
        SCHEMA_METADATOS = [CampoMetadato(nombre="rfc", tipo=str)]

    a = get_meta_serializer_class(FakeModel)
    b = get_meta_serializer_class(FakeModel)
    assert a is b  # same object — lru_cache hit


def test_campo_metadato_serializer_outputs_complete_shape():
    from sinpapel_drf.serializers import CampoMetadatoSerializer

    c = CampoMetadato(
        nombre="edad", tipo=int, requerido=False, default=18,
        choices=None, etiqueta="Edad", ayuda="años cumplidos",
    )
    payload = {
        "nombre": "edad", "tipo": "int", "requerido": False,
        "default": 18, "choices": None, "etiqueta": "Edad",
        "ayuda": "años cumplidos",
    }
    s = CampoMetadatoSerializer(payload)
    assert s.data == payload
