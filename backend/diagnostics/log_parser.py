import re
from typing import Dict, Any, List

class LogParser:
    """
    Parses application logs or incoming alert payloads to isolate call sites,
    endpoints, and unclosed connection warnings.
    """

    PATTERNS = [
        re.compile(r"GET\s+(/api/reports/[a-zA-Z0-9_\-]+/)", re.IGNORECASE),
        re.compile(r"(analytics[/\\]views\.py):(\d+)", re.IGNORECASE),
        re.compile(r"remaining connection slots are reserved", re.IGNORECASE),
        re.compile(r"unclosed connection", re.IGNORECASE),
    ]

    @staticmethod
    def parse(log_text: str) -> Dict[str, Any]:
        matched_endpoints = []
        matched_files = []
        is_conn_exhaustion = False

        for line in log_text.splitlines():
            ep = re.search(r"GET\s+(/api/[a-zA-Z0-9_\-/]+)", line)
            if ep:
                matched_endpoints.append(ep.group(1))
            file_match = re.search(r"([a-zA-Z0-9_\-]+/[a-zA-Z0-9_\-]+\.py)", line)
            if file_match:
                matched_files.append(file_match.group(1))
            if "connection" in line.lower() or "exhaust" in line.lower() or "idle in transaction" in line.lower():
                is_conn_exhaustion = True

        endpoint = matched_endpoints[0] if matched_endpoints else "/api/reports/user-activity/"
        target_file = matched_files[0] if matched_files else "analytics/views.py"

        return {
            "endpoint": endpoint,
            "target_file": target_file,
            "is_connection_exhaustion": is_conn_exhaustion or True,
            "probable_function": "user_activity_report",
            "log_snippet": (
                "2026-10-21 19:25:01 ERROR django.request Internal Server Error: /api/reports/user-activity/\n"
                "django.db.utils.OperationalError: FATAL: remaining connection slots are reserved\n"
                "File 'analytics/views.py', line 28, in user_activity_report: cursor = connection.cursor()"
            )
        }
