from rest_framework.decorators import api_view

from .envelope import ok


@api_view(["GET"])
def health(request):
    return ok({"status": "healthy", "service": "autosre", "version": "2.0.0"})
