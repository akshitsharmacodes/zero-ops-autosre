"""
ASGI entrypoint (run with: uvicorn autosre_api.asgi:application).

ASGI lets the live event stream (SSE) wait for new events without tying up a
worker thread per open dashboard tab.
"""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "autosre_api.settings")

application = get_asgi_application()

from incidents.runtime import start_background_services  # noqa: E402

start_background_services()
