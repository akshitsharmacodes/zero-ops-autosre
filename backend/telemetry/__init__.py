from .base import ConnectionSnapshot, DatabaseAdapter, SessionInfo, TelemetryUnavailable


def get_adapter() -> DatabaseAdapter:
    """Build the adapter for the configured target database engine."""
    from django.conf import settings

    cfg = settings.TARGET_DB
    engine = cfg["ENGINE"]
    if engine in ("postgres", "postgresql"):
        from .postgres import PostgresAdapter

        return PostgresAdapter(cfg["HOST"], cfg["PORT"], cfg["NAME"], cfg["USER"], cfg["PASSWORD"])
    raise ValueError(f"No telemetry adapter for database engine '{engine}' (available: postgres)")


__all__ = ["ConnectionSnapshot", "DatabaseAdapter", "SessionInfo", "TelemetryUnavailable", "get_adapter"]
