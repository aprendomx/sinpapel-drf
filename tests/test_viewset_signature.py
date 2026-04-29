"""S13.6 — E2E tests para WorkflowViewSet.transition con signature dispatch.

Cubre los 4 backends + dual mode FIEL:
- Modo A (fiel/client-side) JSON body
- Modo B (fiel/server-side) multipart con setting on/off
- manual + fake backends JSON body
- backward compat sin signature (S13.5)

Pattern reusado: APIClient.force_authenticate (S13.4),
expose_solicitud_config (S13.4), `transaction=True` para signal flow (S13.2).
"""
from __future__ import annotations

import base64
import datetime as _dt
import importlib
import sys

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import clear_url_caches, include, path
from rest_framework.test import APIClient

from sinpapel.registry import WorkflowConfig, WorkflowRegistry


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures (replican test_viewset_full.py + agregan FIEL keypair)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def expose_solicitud_config(cleanup_registry):
    from creditos.models import Solicitud

    config = WorkflowConfig(
        model=Solicitud,
        state_field="estado",
        workflow_key="solicitud_test_signature",
        expose_endpoints=True,
        endpoint_slug="solicitudes-sig",
    )
    WorkflowRegistry.register("solicitud_test_signature", config)
    yield config


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(
        username="s13_6_admin", password="x", email="s13_6@example.com"
    )


@pytest.fixture
def transition_setup(db):
    from creditos.models import ProductoCreditoFOVISSSTE, ProductoVersionFlujo
    from sinpapel.models import ConfiguracionTransicion, Estado, VersionFlujo

    estado_origen = Estado.objects.create(nombre="S13_6_ORIGEN")
    estado_destino = Estado.objects.create(nombre="S13_6_DESTINO")
    flujo = VersionFlujo.objects.create(nombre="S13_6_FLUJO", activo=True)
    ConfiguracionTransicion.objects.create(
        flujo=flujo,
        estado_origen=estado_origen,
        estado_destino=estado_destino,
    )
    producto = ProductoCreditoFOVISSSTE.objects.create(
        nombre="P_S13_6", clave="P-S13-6", identificador="S136",
        marca="TEST", monto_minimo=0, monto_maximo=0,
        tasa_interes=0, tasa_interes_moratorio=0,
    )
    ProductoVersionFlujo.objects.create(producto=producto, flujo=flujo)
    return {"estado_origen": estado_origen, "estado_destino": estado_destino,
            "producto": producto, "flujo": flujo}


@pytest.fixture
def solicitud_with_flujo(transition_setup):
    from creditos.models import Solicitud
    return Solicitud.objects.create(
        estado=transition_setup["estado_origen"],
        producto=transition_setup["producto"],
    )


@pytest.fixture
def api_client_authenticated(expose_solicitud_config, admin_user, settings):
    import sinpapel_drf.urls
    importlib.reload(sinpapel_drf.urls)
    urlconf = type("UC", (), {"urlpatterns": [
        path("sinpapel/api/", include(sinpapel_drf.urls.urlpatterns)),
    ]})
    sys.modules["test_urlconf_s13_6"] = urlconf
    settings.ROOT_URLCONF = "test_urlconf_s13_6"
    clear_url_caches()
    client = APIClient()
    client.force_authenticate(user=admin_user)
    yield client
    sys.modules.pop("test_urlconf_s13_6", None)
    clear_url_caches()


@pytest.fixture(scope="session")
def fiel_keypair_for_e2e():
    """RSA + cert + PKCS#8 DER encrypted key (SAT format). Session-scoped."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "S13.6 TEST FIRMANTE"),
        x509.NameAttribute(NameOID.SERIAL_NUMBER, "TESTRFC135"),
    ])
    now = _dt.datetime.now(_dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject).issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - _dt.timedelta(days=1))
        .not_valid_after(now + _dt.timedelta(days=365))
        .sign(private_key, hashes.SHA256())
    )
    cert_der = cert.public_bytes(serialization.Encoding.DER)
    password = b"s136-test-pass"
    key_der = private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.BestAvailableEncryption(password),
    )
    # Pre-compute firma_b64 + cert_b64 para modo A
    content = b"S13.6 test content"
    firma_b64 = base64.b64encode(
        private_key.sign(content, padding.PKCS1v15(), hashes.SHA256())
    ).decode()
    return {
        "cert_der": cert_der, "key_der": key_der, "password": password,
        "content": content, "firma_b64": firma_b64,
        "cert_b64": base64.b64encode(cert_der).decode(),
        "_priv_for_test": private_key,  # exposed para tests modo A que firman canonical content
    }


# ─────────────────────────────────────────────────────────────────────────────
# Modo A — fiel/client-side
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db(transaction=True)
def test_transition_with_fiel_client_side_signing(
    transition_setup, solicitud_with_flujo, api_client_authenticated, fiel_keypair_for_e2e, admin_user,
):
    """Modo A happy path: JSON body con firma_b64 + cert_b64 → 201 + RegistroFirma fiel.

    Firma client-side debe firmar el MISMO contenido canónico que construye
    el viewset: {instance_id, target_state, user_id} JSON sort_keys.
    """
    from sinpapel.models import RegistroFirma
    from sinpapel_drf.viewsets import _canonicalize_for_signing

    rf_before = RegistroFirma.objects.count()

    # Reproduce el contenido canónico del viewset
    content = _canonicalize_for_signing(
        target_state="S13_6_DESTINO",
        instance_id=solicitud_with_flujo.pk,
        user_id=admin_user.id,
    )
    private_key = fiel_keypair_for_e2e["_priv_for_test"]  # added in fixture below
    firma_b64 = base64.b64encode(
        private_key.sign(content, padding.PKCS1v15(), hashes.SHA256())
    ).decode()

    resp = api_client_authenticated.post(
        f"/sinpapel/api/solicitudes-sig/{solicitud_with_flujo.pk}/transition/",
        data={
            "target_state": "S13_6_DESTINO",
            "comentarios": "modo A",
            "signature": {
                "backend": "fiel",
                "mode": "client-side",
                "firma_b64": firma_b64,
                "certificado_cer_b64": fiel_keypair_for_e2e["cert_b64"],
            },
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    assert RegistroFirma.objects.count() == rf_before + 1
    rf = RegistroFirma.objects.last()
    assert rf.backend_name == "fiel"
    # modo A → metadata.mode NO presente (solo modo B lo agrega)
    assert "mode" not in (rf.backend_metadata or {})


# ─────────────────────────────────────────────────────────────────────────────
# Modo B — fiel/server-side
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db(transaction=True)
@override_settings(SINPAPEL_ALLOW_SERVER_SIGNING=True)
def test_transition_with_fiel_server_side_signing(
    transition_setup, solicitud_with_flujo, api_client_authenticated, fiel_keypair_for_e2e,
):
    """Modo B happy path: multipart con cer/key/password + setting True → 201."""
    from sinpapel.models import RegistroFirma
    rf_before = RegistroFirma.objects.count()

    cer_file = SimpleUploadedFile(
        "c.cer", fiel_keypair_for_e2e["cert_der"], "application/x-x509-ca-cert"
    )
    key_file = SimpleUploadedFile(
        "c.key", fiel_keypair_for_e2e["key_der"], "application/octet-stream"
    )

    resp = api_client_authenticated.post(
        f"/sinpapel/api/solicitudes-sig/{solicitud_with_flujo.pk}/transition/",
        data={
            "target_state": "S13_6_DESTINO",
            "comentarios": "modo B",
            "signature.backend": "fiel",
            "signature.mode": "server-side",
            "signature.cer_file": cer_file,
            "signature.key_file": key_file,
            "signature.password": fiel_keypair_for_e2e["password"].decode(),
        },
        format="multipart",
    )
    assert resp.status_code == 201, resp.content
    assert RegistroFirma.objects.count() == rf_before + 1
    rf = RegistroFirma.objects.last()
    assert rf.backend_name == "fiel"
    assert rf.backend_metadata.get("mode") == "server-side"


@pytest.mark.django_db
def test_transition_server_side_blocked_when_setting_false(
    transition_setup, solicitud_with_flujo, api_client_authenticated, fiel_keypair_for_e2e,
):
    """Default seguro: setting=False → 400 explicit mensaje (NO override_settings)."""
    cer_file = SimpleUploadedFile("c.cer", fiel_keypair_for_e2e["cert_der"])
    key_file = SimpleUploadedFile("c.key", fiel_keypair_for_e2e["key_der"])

    resp = api_client_authenticated.post(
        f"/sinpapel/api/solicitudes-sig/{solicitud_with_flujo.pk}/transition/",
        data={
            "target_state": "S13_6_DESTINO",
            "signature.backend": "fiel",
            "signature.mode": "server-side",
            "signature.cer_file": cer_file,
            "signature.key_file": key_file,
            "signature.password": "x",
        },
        format="multipart",
    )
    assert resp.status_code == 400, resp.content
    assert "Server-side signing is disabled" in resp.content.decode()


# ─────────────────────────────────────────────────────────────────────────────
# Manual + Fake backends
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db(transaction=True)
def test_transition_with_manual_signature(
    transition_setup, solicitud_with_flujo, api_client_authenticated,
):
    """Manual happy path → 201 + RegistroFirma manual."""
    from sinpapel.models import RegistroFirma
    rf_before = RegistroFirma.objects.count()

    resp = api_client_authenticated.post(
        f"/sinpapel/api/solicitudes-sig/{solicitud_with_flujo.pk}/transition/",
        data={
            "target_state": "S13_6_DESTINO",
            "signature": {
                "backend": "manual",
                "scanned_image_path": "/uploads/firma.png",
                "witness_name": "Lic. Pérez",
            },
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    assert RegistroFirma.objects.count() == rf_before + 1
    assert RegistroFirma.objects.last().backend_name == "manual"


@pytest.mark.django_db(transaction=True)
def test_transition_with_fake_signature(
    transition_setup, solicitud_with_flujo, api_client_authenticated,
):
    """Fake happy path (tests only) → 201 + RegistroFirma fake."""
    from sinpapel.models import RegistroFirma
    rf_before = RegistroFirma.objects.count()

    resp = api_client_authenticated.post(
        f"/sinpapel/api/solicitudes-sig/{solicitud_with_flujo.pk}/transition/",
        data={
            "target_state": "S13_6_DESTINO",
            "signature": {"backend": "fake"},
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    assert RegistroFirma.objects.count() == rf_before + 1
    assert RegistroFirma.objects.last().backend_name == "fake"


# ─────────────────────────────────────────────────────────────────────────────
# Validation errors
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_transition_signature_with_unknown_backend(
    transition_setup, solicitud_with_flujo, api_client_authenticated,
):
    """Backend inválido → 400."""
    resp = api_client_authenticated.post(
        f"/sinpapel/api/solicitudes-sig/{solicitud_with_flujo.pk}/transition/",
        data={
            "target_state": "S13_6_DESTINO",
            "signature": {"backend": "totally-fake"},
        },
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_transition_signature_fiel_missing_firma_b64(
    transition_setup, solicitud_with_flujo, api_client_authenticated,
):
    """Modo A sin firma_b64 → 400."""
    resp = api_client_authenticated.post(
        f"/sinpapel/api/solicitudes-sig/{solicitud_with_flujo.pk}/transition/",
        data={
            "target_state": "S13_6_DESTINO",
            "signature": {"backend": "fiel", "mode": "client-side",
                          "certificado_cer_b64": "Y2VydA=="},
        },
        format="json",
    )
    assert resp.status_code == 400
    assert "firma_b64" in resp.content.decode()


# ─────────────────────────────────────────────────────────────────────────────
# Backward compat S13.5 (sin signature)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db(transaction=True)
def test_transition_without_signature_backward_compat(
    transition_setup, solicitud_with_flujo, api_client_authenticated,
):
    """S13.5 backward compat: sin signature sigue funcionando."""
    resp = api_client_authenticated.post(
        f"/sinpapel/api/solicitudes-sig/{solicitud_with_flujo.pk}/transition/",
        data={"target_state": "S13_6_DESTINO"},
        format="json",
    )
    assert resp.status_code == 201, resp.content
