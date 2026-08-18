"""Settings standalone para la suite de sinpapel-drf.

Permite correr `pytest` sin el proyecto host (creditos): modelos espejo en
tests/models.py sustituyen a los de creditos.
"""
SECRET_KEY = "sinpapel-drf-tests-only"
DEBUG = True
USE_TZ = True
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "rest_framework",
    "simple_history",
    "sinpapel",
    "sinpapel_drf",
    "tests",
]
ROOT_URLCONF = "tests.urls"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
MEDIA_ROOT = "/tmp/sinpapel_drf_test_media"

# El host original autentica con un authenticator que emite WWW-Authenticate
# (→ 401 para anónimos). Espejo del comportamiento para los tests de auth.
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.BasicAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
}
