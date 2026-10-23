"""Builds the agent's real dependencies from Django settings and runs an incident."""
from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.db.models import Avg

from agent.coding.llm import build_live_client
from agent.pipeline import AgentDeps, PipelineConfig, run_pipeline
from correlation.correlator import GitCorrelator
from delivery.providers import DeliveryError, get_provider
from agent.approvals import AutoApproval
from guardrails.injection import build_screen
from sandbox.runner import get_sandbox
from telemetry import get_adapter

from .models import Incident, RunMode, RuntimeConfig, TelemetrySample
from .approvals import DjangoApprovalGate
from .memory import DjangoIncidentMemory
from .recorder import DjangoRecorder

logger = logging.getLogger("autosre.wiring")


def secret_values() -> list[str]:
    """Configured secrets are redacted by exact value everywhere we build prompts."""
    values = [settings.DELIVERY["GITHUB_TOKEN"], settings.TARGET_DB["PASSWORD"], settings.SECRET_KEY]
    values += [p["API_KEY"] for p in settings.LLM["PROVIDERS"].values()]
    return [v for v in values if v and len(v) >= 6]


def baseline_for(incident: Incident) -> dict | None:
    """Average of healthy samples in the 10 minutes before the alert (FR-2.5)."""
    window = TelemetrySample.objects.filter(
        ts__gte=incident.created_at - timedelta(minutes=10), ts__lt=incident.created_at - timedelta(seconds=20),
    )
    agg = window.aggregate(total=Avg("total"), active=Avg("active"), idle=Avg("idle"),
                           idle_in_transaction=Avg("idle_in_transaction"))
    if agg["total"] is None:
        return None
    return {k: round(v, 1) for k, v in agg.items()}


def pipeline_config() -> PipelineConfig:
    a = settings.AUTOSRE
    return PipelineConfig(
        app_prefix=settings.TARGET_DB["APP_NAME_PREFIX"],
        idle_min_seconds=a["IDLE_IN_TX_MIN_SECONDS"],
        alert_threshold=RuntimeConfig.load().alert_threshold,
        base_branch=settings.TARGET_REPO["BASE_BRANCH"],
        max_attempts=a["MAX_ATTEMPTS"],
        max_steps=a["AGENT_MAX_STEPS"],
        pr_max_rounds=a["PR_MAX_ROUNDS"],
        pr_poll_seconds=a["PR_POLL_SECONDS"],
        pr_watch_timeout=a["PR_WATCH_TIMEOUT_SECONDS"],
        labels=settings.DELIVERY["LABELS"],
        secret_values=secret_values(),
        deliveries_dir=settings.VAR_DIR / "deliveries",
        work_dir=settings.VAR_DIR / "work",
    )


def run_incident(incident_id: str) -> None:
    incident = Incident.objects.get(pk=incident_id)
    recorder = DjangoRecorder(incident_id)

    if incident.mode == RunMode.REPLAY:
        from .replay import replay_into

        replay_into(incident)
        return

    try:
        provider = get_provider()
    except DeliveryError as exc:
        recorder.set_status("ESCALATED")
        recorder.update(escalation_reason=str(exc))
        recorder.event("ALERT", f"ESCALATED: delivery is not configured ({exc}).")
        return

    config = RuntimeConfig.load()
    incident.max_attempts = incident.max_attempts or config.max_attempts
    cfg = pipeline_config()
    cfg.max_attempts = incident.max_attempts

    deps = AgentDeps(
        recorder=recorder,
        adapter=get_adapter(),
        log_path=settings.TARGET_APP["LOG_PATH"],
        correlator=GitCorrelator(settings.TARGET_REPO["PATH"], settings.TARGET_REPO["BASE_BRANCH"],
                                 settings.TARGET_REPO["LOOKBACK_COMMITS"], settings.TARGET_REPO["LOOKBACK_DAYS"]),
        provider=provider,
        sandbox=get_sandbox(),
        mode=incident.mode,
        live_client_factory=lambda: build_live_client(
            config.llm_provider,
            on_switch=lambda old, new, why: recorder.event("AGENT", f"Model {old} is out of quota ({why}); switched to {new}."),
        ),
        config=cfg,
        started_at=incident.created_at,
        baseline=lambda: baseline_for(incident),
        # Prompt Guard (remote classifier) only when we are allowed to call the LLM provider anyway
        injection_screen=build_screen(use_remote=incident.mode == "live" and settings.LLM["PROMPT_GUARD_ENABLED"]),
        approvals=DjangoApprovalGate(incident_id, recorder, settings.AUTOSRE["APPROVAL_TIMEOUT_SECONDS"])
        if incident.approval_mode == "review" else AutoApproval(),
        memory=DjangoIncidentMemory(),
    )
    run_pipeline(incident_id, incident.alert, deps)
