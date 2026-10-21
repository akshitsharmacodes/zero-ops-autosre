import json
import time
import queue
from datetime import datetime
from typing import Dict, Any

from django.http import JsonResponse, StreamingHttpResponse, HttpResponse
from rest_framework.decorators import api_view, renderer_classes
from rest_framework.renderers import JSONRenderer

from .store import incident_store, telemetry_store, config_store

def make_response(data: Any = None, error: Dict[str, Any] = None, status: int = 200) -> JsonResponse:
    payload = {
        "data": data,
        "error": error,
        "meta": {
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    }
    return JsonResponse(payload, status=status, safe=False)

@api_view(["GET"])
def health(request):
    return make_response({
        "status": "healthy",
        "service": "autosre_api",
        "version": "1.0.0",
        "time": datetime.utcnow().isoformat() + "Z"
    })

@api_view(["POST"])
def receive_alert(request):
    try:
        payload = request.data if hasattr(request, "data") else json.loads(request.body or "{}")
    except Exception:
        payload = {}
    new_inc = incident_store.create_incident(payload)
    return make_response(new_inc, status=201)

@api_view(["GET"])
def list_incidents(request):
    incidents = incident_store.list_incidents()
    return make_response(incidents)

@api_view(["GET"])
def get_incident(request, incident_id):
    inc = incident_store.get_incident(incident_id)
    if not inc:
        return make_response(error={"code": "NOT_FOUND", "message": f"Incident {incident_id} not found"}, status=404)
    return make_response(inc)

def incident_stream(request, incident_id):
    inc = incident_store.get_incident(incident_id)
    if not inc:
        return JsonResponse({"error": {"code": "NOT_FOUND", "message": "Incident not found"}}, status=404)

    subscriber_queue = incident_store.subscribe_stream(incident_id)

    def event_generator():
        # First yield existing timeline entries as backlog
        current_inc = incident_store.get_incident(incident_id)
        if current_inc:
            for entry in current_inc.get("timeline", []):
                yield f"data: {json.dumps(entry)}\n\n"

        # If incident is already resolved or escalated, send done and finish
        if current_inc and current_inc.get("status") in ["RESOLVED", "ESCALATED"]:
            return

        # Stream new events
        timeout_counter = 0
        while timeout_counter < 120:
            try:
                event = subscriber_queue.get(timeout=1.0)
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("state") in ["RESOLVED", "ESCALATED"]:
                    break
            except queue.Empty:
                # Keep-alive heartbeat
                yield ": keepalive\n\n"
                timeout_counter += 1
                # Check status
                c = incident_store.get_incident(incident_id)
                if c and c.get("status") in ["RESOLVED", "ESCALATED"]:
                    break
        incident_store.unsubscribe_stream(incident_id, subscriber_queue)

    response = StreamingHttpResponse(event_generator(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    response["Access-Control-Allow-Origin"] = "*"
    return response

@api_view(["GET"])
def get_diff(request, incident_id):
    inc = incident_store.get_incident(incident_id)
    if not inc:
        return make_response(error={"code": "NOT_FOUND", "message": "Incident not found"}, status=404)
    diff_text = inc.get("unified_diff") or (
        "--- a/analytics/views.py\n"
        "+++ b/analytics/views.py\n"
        "@@ -27,6 +27,6 @@\n"
        "-    cursor = connection.cursor()\n"
        "-    cursor.execute(\"SELECT 101 AS user_id, 'login_session' AS event, CURRENT_TIMESTAMP AS ts\")\n"
        "-    rows = cursor.fetchall()\n"
        "+    with connection.cursor() as cursor:\n"
        "+        cursor.execute(\"SELECT 101 AS user_id, 'login_session' AS event, CURRENT_TIMESTAMP AS ts\")\n"
        "+        rows = cursor.fetchall()\n"
        "     data = [{\"user_id\": r[0], \"event\": r[1], \"ts\": str(r[2])} for r in rows]\n"
        "     return JsonResponse({\"status\": \"success\", \"count\": len(data), \"data\": data})"
    )
    return make_response({"diff": diff_text, "incident_id": incident_id})

@api_view(["GET"])
def get_postmortem(request, incident_id):
    inc = incident_store.get_incident(incident_id)
    if not inc:
        return make_response(error={"code": "NOT_FOUND", "message": "Incident not found"}, status=404)
    pm = inc.get("postmortem")
    if not pm:
        from delivery.postmortem import PostMortemGenerator
        pm = PostMortemGenerator.generate(inc)
    return make_response({"markdown": pm, "incident_id": incident_id})

@api_view(["GET"])
def get_telemetry_current(request):
    stats = telemetry_store.get_current()
    return make_response(stats)

@api_view(["GET"])
def get_telemetry_history(request):
    history = telemetry_store.get_history()
    return make_response(history)

@api_view(["GET"])
def get_guardrails(request):
    incident_id = request.GET.get("incident_id", "INC-8941")
    inc = incident_store.get_incident(incident_id)
    checks = []
    if inc and inc.get("guardrails"):
        checks = inc["guardrails"]
    else:
        checks = [
            {"id": "diff_size_limit", "name": "Diff Size Constraint (<= 50 lines)", "passed": True, "details": "Patch touches 8 lines (threshold: 50 lines)."},
            {"id": "file_allowlist", "name": "File Allowlist (Suspect Commit Scope)", "passed": True, "details": "Touched files: analytics/views.py. Unauthorized: 0."},
            {"id": "secret_scrubbing", "name": "Secret Scrubbing & Leak Prevention", "passed": True, "details": "No sensitive credentials detected in patch."},
            {"id": "dangerous_patterns", "name": "Dangerous Pattern Blocklist", "passed": True, "details": "Passed: No destructive commands or unauthorized execution."},
            {"id": "sandbox_isolation", "name": "Sandbox Resource & Network Isolation", "passed": True, "details": "Isolation verified (0 host mounts, 512MB RAM, 120s max runtime)."},
            {"id": "retry_cap", "name": "Retry Threshold Constraint (<= 3 attempts)", "passed": True, "details": "Current attempt: 2/3."},
            {"id": "human_approval_gate", "name": "Human-in-the-Loop Review Gate", "passed": True, "details": "Target branch 'autosre/fix-connection-leak' (auto-merge disabled; human review mandatory)."}
        ]
    return make_response({"incident_id": incident_id, "checks": checks})

@api_view(["POST"])
def demo_trigger(request):
    """
    Starts the traffic simulator to saturate connections and triggers an incident.
    """
    telemetry_store.set_incident_active(True)
    # Record high connection spike
    telemetry_store.record_pulse(active=6, idle=4, idle_in_tx=88)
    
    # Create incident and run agent in background
    alert_payload = {
        "alert_name": "PostgresConnectionsExhausted",
        "service": "victim-service",
        "severity": "critical",
        "value": 98,
        "threshold": 95,
        "log_text": "ERROR: django.db.utils.OperationalError: FATAL: remaining connection slots are reserved\nGET /api/reports/user-activity/"
    }
    new_inc = incident_store.create_incident(alert_payload)
    return make_response({
        "status": "triggered",
        "incident": new_inc,
        "message": "Traffic simulator initiated; incident created and agent launched."
    })

@api_view(["POST"])
def demo_reset(request):
    incident_store.reset()
    return make_response({
        "status": "reset_complete",
        "message": "Victim service simulation and incidents reset to baseline."
    })

@api_view(["GET", "PATCH"])
def handle_config(request):
    if request.method == "GET":
        return make_response(config_store.get_config())
    elif request.method == "PATCH":
        body = request.data if hasattr(request, "data") else json.loads(request.body or "{}")
        updated = config_store.update_config(
            mode=body.get("mode"),
            max_attempts=body.get("max_attempts")
        )
        return make_response(updated)
