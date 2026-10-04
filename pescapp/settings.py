"""
Configuración de Django para pescAPP.

- Sin apps que creen tablas (sin auth, admin, sessions ni contenttypes):
  el esquema de negocio lo crean los scripts SQL de db/postgres.
- Mensajes con CookieStorage (no requiere tabla de sesiones).
- Configuración por variables de entorno; si existe un archivo .env en la
  raíz del proyecto (ejecución sin Docker) se carga sin sobrescribir las
  variables ya definidas.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _cargar_env(ruta: Path) -> None:
    """Carga KEY=VALOR de un .env simple (sin dependencias externas)."""
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


_cargar_env(BASE_DIR / ".env")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "cambie-esta-clave-solo-para-demo")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get(
        "DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,0.0.0.0,testserver"
    ).split(",")
    if h.strip()
]

INSTALLED_APPS = [
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "core.middleware.ConsultasMiddleware",
    "core.middleware.UsuarioActualMiddleware",
]

ROOT_URLCONF = "pescapp.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.pescapp",
            ],
        },
    },
]

WSGI_APPLICATION = "pescapp.wsgi.application"

# PostgreSQL vía psycopg 3. Las 12 tablas de negocio se consultan con SQL
# explícito (core/repositorios); el ORM no se usa para ellas.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "pescapp"),
        "USER": os.environ.get("POSTGRES_USER", "pescapp"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "pescapp"),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
    }
}

# MongoDB vía pymongo
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.environ.get("MONGO_DB", "pescapp")

LANGUAGE_CODE = "es-ec"
TIME_ZONE = "America/Guayaquil"
USE_I18N = True
USE_TZ = True
USE_THOUSAND_SEPARATOR = False
FORMAT_MODULE_PATH = ["pescapp.formatos"]

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
WHITENOISE_USE_FINDERS = True

MESSAGE_STORAGE = "django.contrib.messages.storage.cookie.CookieStorage"
MESSAGE_TAGS = {40: "danger"}  # messages.ERROR -> clase Bootstrap alert-danger

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"consola": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["consola"], "level": "INFO"},
}
