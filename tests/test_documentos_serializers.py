"""Unit tests del serializer de carga — resolución documento/tipo_documento.

NOT runnable in this workspace (no creditos host). Verificado además vía harness
autocontenido (/tmp/sp_verify/run_verify_endpoints.py).
"""
from __future__ import annotations

import pytest

from sinpapel_drf.serializers import InstanciaDocumentoUploadSerializer


@pytest.fixture
def tipo_y_documento(db):
    from sinpapel.models import Documento, TipoDocumento
    td = TipoDocumento.objects.create(nombre="INE")
    doc = Documento.objects.create(nombre="INE", tipo_documento=td, valor="INE")
    return td, doc


def _archivo():
    from django.core.files.uploadedfile import SimpleUploadedFile
    return SimpleUploadedFile("ine.pdf", b"%PDF-fake", content_type="application/pdf")


@pytest.mark.django_db
def test_upload_resuelve_por_documento_pk(tipo_y_documento):
    _td, doc = tipo_y_documento
    s = InstanciaDocumentoUploadSerializer(
        data={"archivo": _archivo(), "documento": doc.pk}
    )
    assert s.is_valid(), s.errors
    assert s.validated_data["documento_obj"].pk == doc.pk
    assert s.validated_data["porcentaje"] == 100


@pytest.mark.django_db
def test_upload_resuelve_por_tipo_unico(tipo_y_documento):
    td, doc = tipo_y_documento
    s = InstanciaDocumentoUploadSerializer(
        data={"archivo": _archivo(), "tipo_documento": td.pk}
    )
    assert s.is_valid(), s.errors
    assert s.validated_data["documento_obj"].pk == doc.pk


@pytest.mark.django_db
def test_upload_tipo_sin_documento_da_error(db):
    from sinpapel.models import TipoDocumento
    td = TipoDocumento.objects.create(nombre="CURP")
    s = InstanciaDocumentoUploadSerializer(
        data={"archivo": _archivo(), "tipo_documento": td.pk}
    )
    assert not s.is_valid()
    assert "tipo_documento" in s.errors


@pytest.mark.django_db
def test_upload_tipo_ambiguo_da_error(db):
    from sinpapel.models import Documento, TipoDocumento
    td = TipoDocumento.objects.create(nombre="COMPROBANTE")
    Documento.objects.create(nombre="A", tipo_documento=td, valor="A")
    Documento.objects.create(nombre="B", tipo_documento=td, valor="B")
    s = InstanciaDocumentoUploadSerializer(
        data={"archivo": _archivo(), "tipo_documento": td.pk}
    )
    assert not s.is_valid()
    assert "tipo_documento" in s.errors


@pytest.mark.django_db
def test_upload_sin_tipo_ni_documento_da_error():
    s = InstanciaDocumentoUploadSerializer(data={"archivo": _archivo()})
    assert not s.is_valid()


@pytest.mark.django_db
def test_upload_porcentaje_fuera_de_rango(tipo_y_documento):
    _td, doc = tipo_y_documento
    s = InstanciaDocumentoUploadSerializer(
        data={"archivo": _archivo(), "documento": doc.pk, "porcentaje": 150}
    )
    assert not s.is_valid()
    assert "porcentaje" in s.errors
