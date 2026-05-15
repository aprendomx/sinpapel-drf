"""sinpapel-drf — Metadata helpers for the WorkflowViewSet.metadatos action.

`get_meta_serializer_class(model_cls)` — returns a DRF Serializer subclass
built dynamically via `sinpapel.forms.MetaFormFactory.build_serializer()`,
cached per model class (SCHEMA_METADATOS is ClassVar/immutable).

`campo_to_dict(campo)` — serializes a `CampoMetadato` (frozen dataclass) into
a JSON-safe dict for the GET /metadatos/ schema field.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from functools import lru_cache
from typing import Any

from sinpapel.forms import MetaFormFactory
from sinpapel.mixins import CampoMetadato

_TIPO_TO_STR: dict[type, str] = {
    str: "str",
    int: "int",
    bool: "bool",
    Decimal: "Decimal",
    date: "date",
}


def _serialize_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    return value


def campo_to_dict(campo: CampoMetadato) -> dict[str, Any]:
    """Convert a CampoMetadato to a JSON-serializable dict."""
    return {
        "nombre": campo.nombre,
        "tipo": _TIPO_TO_STR.get(campo.tipo, campo.tipo.__name__),
        "requerido": campo.requerido,
        "default": _serialize_default(campo.default),
        "choices": list(campo.choices) if campo.choices is not None else None,
        "etiqueta": campo.etiqueta,
        "ayuda": campo.ayuda,
    }


@lru_cache(maxsize=None)
def get_meta_serializer_class(model_cls: type) -> type:
    """Build + cache the DRF Serializer subclass for SCHEMA_METADATOS.

    Cache-safe: SCHEMA_METADATOS is a ClassVar of immutable frozen dataclasses.
    """
    schema = list(getattr(model_cls, "SCHEMA_METADATOS", []))
    return MetaFormFactory.build_serializer(
        schema, name=f"MetadatosSerializer_{model_cls.__name__}",
    )
