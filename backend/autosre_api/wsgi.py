import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "autosre_api.settings")

application = get_wsgi_application()

from incidents.runtime import start_background_services  # noqa: E402

start_background_services()
