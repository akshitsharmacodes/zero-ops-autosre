"""
Every API response uses the same envelope so the frontend handles them uniformly:

    {"data": ..., "error": null | {"code": "...", "message": "..."}, "meta": {"timestamp": "..."}}
"""
from typing import Any

from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


def _meta() -> dict:
    return {"timestamp": timezone.now().isoformat()}


def ok(data: Any = None, status: int = 200) -> Response:
    return Response({"data": data, "error": None, "meta": _meta()}, status=status)


def fail(code: str, message: str, status: int = 400, data: Any = None) -> Response:
    return Response({"data": data, "error": {"code": code, "message": message}, "meta": _meta()}, status=status)


def exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        return None
    detail = response.data.get("detail") if isinstance(response.data, dict) else response.data
    response.data = {
        "data": None,
        "error": {"code": getattr(exc, "default_code", "error").upper(), "message": str(detail or exc)},
        "meta": _meta(),
    }
    return response
