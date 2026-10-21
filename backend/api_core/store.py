import time
import queue
import threading
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import logging

from agent.state import AgentState, TimelineEntry
from agent.graph import create_autosre_graph
from diagnostics.pg_analyzer import PgAnalyzer

logger = logging.getLogger(__name__)

class ConfigStore:
    def __init__(self):
        self.mode: str = "cached"  # live | cached | replay
        self.max_attempts: int = 3
        self.lock = threading.Lock()

    def get_config(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "mode": self.mode,
                "max_attempts": self.max_attempts
            }

    def update_config(self, mode: Optional[str] = None, max_attempts: Optional[int] = None) -> Dict[str, Any]:
        with self.lock:
            if mode is not None and mode in ["live", "cached", "replay"]:
                self.mode = mode
            if max_attempts is not None and max_attempts > 0:
                self.max_attempts = int(max_attempts)
            return {
                "mode": self.mode,
                "max_attempts": self.max_attempts
            }

class TelemetryStore:
    def __init__(self):
        self.lock = threading.Lock()
        self.is_incident_active = False
        self.history: List[Dict[str, Any]] = []
        self._init_history()

    def _init_history(self):
        now = datetime.utcnow()
        # Create 20 baseline points
        for i in range(20, 0, -1):
            pt_time = now - timedelta(seconds=i * 10)
            self.history.append({
                "timestamp": pt_time.strftime("%H:%M:%S"),
                "active": 4,
                "idle": 8,
                "idle_in_transaction": 0,
                "max": 100,
                "total": 12
            })

    def record_pulse(self, active: int, idle: int, idle_in_tx: int):
        with self.lock:
            now_str = datetime.utcnow().strftime("%H:%M:%S")
            pt = {
                "timestamp": now_str,
                "active": active,
                "idle": idle,
                "idle_in_transaction": idle_in_tx,
                "max": 100,
                "total": active + idle + idle_in_tx
            }
            self.history.append(pt)
            if len(self.history) > 60:
                self.history.pop(0)

    def set_incident_active(self, active: bool):
        with self.lock:
            self.is_incident_active = active

    def get_current(self) -> Dict[str, Any]:
        # Check pg_analyzer first
        stats = PgAnalyzer().get_connection_stats()
        if self.is_incident_active:
            stats["idle_in_transaction"] = max(stats["idle_in_transaction"], 88)
            stats["active"] = max(stats["active"], 4)
            stats["idle"] = max(stats["idle"], 6)
            stats["total"] = stats["active"] + stats["idle"] + stats["idle_in_transaction"]
        self.record_pulse(stats["active"], stats["idle"], stats["idle_in_transaction"])
        return stats

    def get_history(self) -> List[Dict[str, Any]]:
        with self.lock:
            return list(self.history)

class IncidentStore:
    def __init__(self, config_store: ConfigStore, telemetry_store: TelemetryStore):
        self.config_store = config_store
        self.telemetry_store = telemetry_store
        self.lock = threading.Lock()
        self.incidents: Dict[str, Dict[str, Any]] = {}
        self.subscribers: Dict[str, List[queue.Queue]] = {}
        self._seed_default_incident()

    def _seed_default_incident(self):
        default_id = "INC-8941"
        self.incidents[default_id] = {
            "id": default_id,
            "status": "ALERT_RECEIVED",
            "attempt": 0,
            "max_attempts": 3,
            "suspect_commit": {
                "sha": "728a817",
                "author": "Charlie Contributor <charlie@zero-ops.internal>",
                "committed_date": "2026-10-20T09:15:00Z",
                "message": "perf(reports): add fast raw-sql user activity report",
                "file": "analytics/views.py"
            },
            "leaking_code": (
                "def user_activity_report(request):\n"
                "    cursor = connection.cursor()\n"
                "    cursor.execute(\"SELECT 101 AS user_id, 'login_session' AS event, CURRENT_TIMESTAMP AS ts\")\n"
                "    rows = cursor.fetchall()\n"
                "    data = [{'user_id': r[0], 'event': r[1], 'ts': str(r[2])} for r in rows]\n"
                "    return JsonResponse({'status': 'success', 'count': len(data), 'data': data})"
            ),
            "patch": "",
            "risk": "High",
            "confidence": 0.94,
            "sandbox_result": {},
            "pr_url": None,
            "mttr_seconds": 0,
            "timeline": [
                {
                    "ts": datetime.utcnow().strftime("%H:%M:%S"),
                    "tag": "ALERT",
                    "message": "High connection utilization alert received (PostgreSQL 98/100).",
                    "state": "ALERT_RECEIVED"
                }
            ],
            "guardrails": [
                {"id": "diff_size_limit", "name": "Diff Size Constraint (<= 50 lines)", "passed": True, "details": "Pending evaluation"},
                {"id": "file_allowlist", "name": "File Allowlist", "passed": True, "details": "Pending evaluation"},
                {"id": "secret_scrubbing", "name": "Secret Scrubbing", "passed": True, "details": "Pending evaluation"},
                {"id": "dangerous_patterns", "name": "Dangerous Pattern Blocklist", "passed": True, "details": "Pending evaluation"},
                {"id": "sandbox_isolation", "name": "Sandbox Resource Isolation", "passed": True, "details": "Pending evaluation"},
                {"id": "human_approval_gate", "name": "Human-in-the-Loop Review Gate", "passed": True, "details": "Pending evaluation"}
            ],
            "unified_diff": "",
            "postmortem": ""
        }

    def list_incidents(self) -> List[Dict[str, Any]]:
        with self.lock:
            return list(self.incidents.values())

    def get_incident(self, incident_id: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            return self.incidents.get(incident_id)

    def create_incident(self, alert_payload: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            incident_id = f"INC-{uuid.uuid4().hex[:4].upper()}"
            config = self.config_store.get_config()
            new_inc = {
                "id": incident_id,
                "status": "ALERT_RECEIVED",
                "attempt": 0,
                "max_attempts": config["max_attempts"],
                "suspect_commit": {},
                "leaking_code": "",
                "patch": "",
                "risk": "High",
                "confidence": 0.94,
                "sandbox_result": {},
                "pr_url": None,
                "mttr_seconds": 0,
                "timeline": [],
                "guardrails": [],
                "unified_diff": "",
                "postmortem": "",
                "alert_payload": alert_payload
            }
            self.incidents[incident_id] = new_inc
            self.telemetry_store.set_incident_active(True)

        # Launch background agent thread
        thread = threading.Thread(
            target=self._run_agent_thread,
            args=(incident_id, alert_payload),
            daemon=True
        )
        thread.start()
        return new_inc

    def subscribe_stream(self, incident_id: str) -> queue.Queue:
        q = queue.Queue()
        with self.lock:
            if incident_id not in self.subscribers:
                self.subscribers[incident_id] = []
            self.subscribers[incident_id].append(q)
        return q

    def unsubscribe_stream(self, incident_id: str, q: queue.Queue):
        with self.lock:
            if incident_id in self.subscribers and q in self.subscribers[incident_id]:
                self.subscribers[incident_id].remove(q)

    def publish_event(self, incident_id: str, event: TimelineEntry):
        with self.lock:
            subs = list(self.subscribers.get(incident_id, []))
        for q in subs:
            try:
                q.put_nowait(event)
            except Exception:
                pass

    def _run_agent_thread(self, incident_id: str, alert_payload: Dict[str, Any]):
        logger.info(f"Starting agent thread for {incident_id}")
        config = self.config_store.get_config()

        initial_state: AgentState = {
            "incident_id": incident_id,
            "status": "ALERT_RECEIVED",
            "attempt": 0,
            "max_attempts": config["max_attempts"],
            "alert_payload": alert_payload,
            "diagnostics_result": {},
            "suspect_commit": {},
            "leaking_code": "",
            "patch": "",
            "unified_diff": "",
            "risk": "High",
            "confidence": 0.94,
            "sandbox_result": {},
            "error_trace": None,
            "guardrails_result": {},
            "pr_url": None,
            "postmortem": None,
            "timeline": [],
            "mttr_seconds": 0,
            "start_time": time.time(),
            "mode": config["mode"]
        }

        # Custom stream callback hook for graph
        graph = create_autosre_graph()

        # Execute graph step-by-step or stream to capture each state transition live
        last_timeline_len = 0
        try:
            for state_chunk in graph.stream(initial_state):
                for node_name, updated_state in state_chunk.items():
                    # Sync state to incident
                    with self.lock:
                        inc = self.incidents.get(incident_id)
                        if inc:
                            inc["status"] = updated_state.get("status", inc["status"])
                            inc["attempt"] = updated_state.get("attempt", inc["attempt"])
                            inc["suspect_commit"] = updated_state.get("suspect_commit", inc["suspect_commit"])
                            inc["leaking_code"] = updated_state.get("leaking_code", inc["leaking_code"])
                            inc["patch"] = updated_state.get("patch", inc["patch"])
                            inc["unified_diff"] = updated_state.get("unified_diff", inc["unified_diff"])
                            inc["risk"] = updated_state.get("risk", inc["risk"])
                            inc["confidence"] = updated_state.get("confidence", inc["confidence"])
                            inc["sandbox_result"] = updated_state.get("sandbox_result", inc["sandbox_result"])
                            inc["pr_url"] = updated_state.get("pr_url", inc["pr_url"])
                            inc["postmortem"] = updated_state.get("postmortem", inc["postmortem"])
                            inc["mttr_seconds"] = updated_state.get("mttr_seconds", inc["mttr_seconds"])
                            if "guardrails_result" in updated_state and "checks" in updated_state["guardrails_result"]:
                                inc["guardrails"] = updated_state["guardrails_result"]["checks"]

                            # Publish any newly appended timeline events
                            timeline = updated_state.get("timeline", [])
                            while last_timeline_len < len(timeline):
                                new_entry = timeline[last_timeline_len]
                                inc["timeline"].append(new_entry)
                                self.publish_event(incident_id, new_entry)
                                last_timeline_len += 1

                    # If bleed was stopped or resolved, update telemetry
                    if node_name == "node_diagnose":
                        # Capacity drops from 98 down to healthy
                        self.telemetry_store.set_incident_active(False)
                        self.telemetry_store.record_pulse(active=3, idle=12, idle_in_tx=0)

        except Exception as e:
            logger.error(f"Error in agent graph execution for {incident_id}: {e}", exc_info=True)
            err_event: TimelineEntry = {
                "ts": datetime.utcnow().strftime("%H:%M:%S"),
                "tag": "ALERT",
                "message": f"Agent runtime exception: {e}",
                "state": "ESCALATED"
            }
            with self.lock:
                inc = self.incidents.get(incident_id)
                if inc:
                    inc["status"] = "ESCALATED"
                    inc["timeline"].append(err_event)
            self.publish_event(incident_id, err_event)

    def reset(self):
        with self.lock:
            self.incidents.clear()
            self._seed_default_incident()
            self.telemetry_store.set_incident_active(False)
            self.telemetry_store._init_history()

# Global singletons
config_store = ConfigStore()
telemetry_store = TelemetryStore()
incident_store = IncidentStore(config_store, telemetry_store)
