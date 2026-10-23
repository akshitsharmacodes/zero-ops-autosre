import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "victim-service-dev-only")
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "analytics",
]

MIDDLEWARE = [
    "analytics.observability.RequestLogMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "victim_project.urls"
WSGI_APPLICATION = "victim_project.wsgi.application"

if os.environ.get("POSTGRES_HOST"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "HOST": os.environ["POSTGRES_HOST"],
            "PORT": os.environ.get("POSTGRES_PORT", "5432"),
            "NAME": os.environ.get("POSTGRES_DB", "victim_db"),
            "USER": os.environ.get("POSTGRES_USER", "victim_app"),
            "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
            "CONN_MAX_AGE": 0,
            "OPTIONS": {"application_name": "victim-service:orm"},
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_TZ = True

LOG_DIR = Path(os.environ.get("VICTIM_LOG_DIR", BASE_DIR / "logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"json": {"()": "analytics.observability.JsonFormatter"}},
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "json"},
        "file": {"class": "logging.FileHandler", "filename": str(LOG_DIR / "victim.log"), "formatter": "json"},
    },
    "root": {"handlers": ["console", "file"], "level": "INFO"},
}
