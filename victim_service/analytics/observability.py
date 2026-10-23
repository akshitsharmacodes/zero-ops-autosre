"""
Structured logging: one JSON object per line, so tools (like AutoSRE) can parse logs reliably.
"""
import json
import logging
import time
from datetime import datetime, timezone

_STANDARD_ATTRS = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in vars(record).items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                payload[key] = value if isinstance(value, (str, int, float, bool, type(None))) else str(value)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


request_logger = logging.getLogger("victim.request")


class RequestLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started = time.monotonic()
        response = self.get_response(request)
        match = getattr(request, "resolver_match", None)
        request_logger.info(
            "request",
            extra={
                "method": request.method,
                "path": request.path,
                "status": response.status_code,
                "duration_ms": round((time.monotonic() - started) * 1000, 1),
                "view": getattr(match, "_func_path", None),
            },
        )
        return response
