import {
  Incident,
  ConnectionTelemetry,
  ConnectionHistoryPoint,
  GuardrailsResponse,
  SystemConfig,
  ApiResponse,
  TimelineEntry
} from "../types/api"

const BASE_URL = import.meta.env.VITE_API_BASE_URL || ""
const USE_MOCK = import.meta.env.VITE_USE_MOCK === "true"

// Mock state store for mock mode
const mockStore = {
  incident: {
    id: "INC-8941",
    status: "RESOLVED" as const,
    attempt: 2,
    max_attempts: 3,
    suspect_commit: {
      sha: "728a817",
      author: "Charlie Contributor <charlie@zero-ops.internal>",
      committed_date: "2026-10-20T09:15:00Z",
      message: "perf(reports): add fast raw-sql user activity report",
      file: "analytics/views.py"
    },
    leaking_code: `def user_activity_report(request):
    cursor = connection.cursor()
    cursor.execute("SELECT 101 AS user_id, 'login_session' AS event, CURRENT_TIMESTAMP AS ts")
    rows = cursor.fetchall()
    # Missing: cursor.close() or 'with connection.cursor() as cursor:'
    data = [{"user_id": r[0], "event": r[1], "ts": str(r[2])} for r in rows]
    return JsonResponse({"status": "success", "count": len(data), "data": data})`,
    patch: `def user_activity_report(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 101 AS user_id, 'login_session' AS event, CURRENT_TIMESTAMP AS ts")
        rows = cursor.fetchall()
    data = [{"user_id": r[0], "event": r[1], "ts": str(r[2])} for r in rows]
    return JsonResponse({"status": "success", "count": len(data), "data": data})`,
    risk: "High" as const,
    confidence: 0.94,
    sandbox_result: {
      passed: true,
      exit_code: 0,
      output: `=== SANDBOX VERIFICATION LOG ===
[CHECK manage.py check]:
System check identified no issues (0 silenced).
[PYTEST RUN]:
test_health.py::test_health_check PASSED [ 33%]
test_health.py::test_metrics_summary PASSED [ 66%]
test_leak_regression.py::test_user_activity_report_closes_cursor PASSED [100%]
============================== 3 passed in 0.08s ==============================`,
      engine: "isolated_sandbox",
      isolation: "container"
    },
    pr_url: "https://github.com/zero-ops/victim-service/pull/42",
    mttr_seconds: 38,
    timeline: [
      { ts: "19:28:10", tag: "ALERT", message: "Postgres connection pool exhausted (98/100 connections). Alert ingested.", state: "ALERT_RECEIVED" },
      { ts: "19:28:14", tag: "DIAG", message: "pg_stat_activity shows 88 sessions stuck in 'idle in transaction' on user_activity_report.", state: "DIAGNOSING" },
      { ts: "19:28:17", tag: "DIAG", message: "Stop-the-bleeding executed: Terminated 88 hanging backends with pg_terminate_backend.", state: "DIAGNOSING" },
      { ts: "19:28:21", tag: "CORR", message: "Git blame identified commit 728a817 by Charlie Contributor in analytics/views.py.", state: "CORRELATING" },
      { ts: "19:28:27", tag: "PATCH", message: "LLM synthesized attempt #1: Added cursor.close() after response construction.", state: "PATCHING" },
      { ts: "19:28:32", tag: "TEST", message: "Sandbox Attempt #1 FAILED: AssertionError: Cursor #1 was NOT closed before exit. Reading stack trace...", state: "TESTING_IN_SANDBOX" },
      { ts: "19:28:39", tag: "PATCH", message: "LLM synthesized attempt #2 with error trace: Wrapped execution in 'with connection.cursor() as cursor:'.", state: "PATCHING" },
      { ts: "19:28:44", tag: "TEST", message: "Sandbox Attempt #2 PASSED: pytest exited 0. All 3 regression & health tests passed.", state: "TESTING_IN_SANDBOX" },
      { ts: "19:28:47", tag: "PR", message: "Guardrails passed: Diff 8 lines <= 50, secret scrubbing clean, isolated runner verified.", state: "PR_CREATED" },
      { ts: "19:28:48", tag: "PR", message: "Pull Request #42 opened: https://github.com/zero-ops/victim-service/pull/42 (Awaiting human review)", state: "PR_CREATED" },
      { ts: "19:28:48", tag: "ALERT", message: "Incident INC-8941 RESOLVED autonomously in 38s (vs ~45 min manual MTTR).", state: "RESOLVED" }
    ] as TimelineEntry[],
    guardrails: [
      { id: "diff_size_limit", name: "Diff Size Constraint (<= 50 lines)", passed: true, details: "Patch touches 8 lines (threshold: 50 lines)." },
      { id: "file_allowlist", name: "File Allowlist (Suspect Commit Scope)", passed: true, details: "Touched files: analytics/views.py. Unauthorized: 0." },
      { id: "secret_scrubbing", name: "Secret Scrubbing & Leak Prevention", passed: true, details: "No sensitive credentials detected in patch." },
      { id: "dangerous_patterns", name: "Dangerous Pattern Blocklist", passed: true, details: "Passed: No destructive commands or unauthorized execution." },
      { id: "sandbox_isolation", name: "Sandbox Resource & Network Isolation", passed: true, details: "Isolation verified (0 host mounts, 512MB RAM, 120s max runtime)." },
      { id: "retry_cap", name: "Retry Threshold Constraint (<= 3 attempts)", passed: true, details: "Current attempt: 2/3." },
      { id: "human_approval_gate", name: "Human-in-the-Loop Review Gate", passed: true, details: "Target branch 'autosre/fix-connection-leak' (auto-merge disabled; human review mandatory)." }
    ],
    unified_diff: `--- a/analytics/views.py
+++ b/analytics/views.py
@@ -27,6 +27,6 @@
-    cursor = connection.cursor()
-    cursor.execute("SELECT 101 AS user_id, 'login_session' AS event, CURRENT_TIMESTAMP AS ts")
-    rows = cursor.fetchall()
+    with connection.cursor() as cursor:
+        cursor.execute("SELECT 101 AS user_id, 'login_session' AS event, CURRENT_TIMESTAMP AS ts")
+        rows = cursor.fetchall()
     data = [{"user_id": r[0], "event": r[1], "ts": str(r[2])} for r in rows]
     return JsonResponse({"status": "success", "count": len(data), "data": data})`,
    postmortem: `# Incident Post-Mortem: INC-8941
**Service:** \`victim-service\` (Django 4.2 / PostgreSQL 15)  
**Severity:** P1 (Critical Outage - Connection Pool Exhaustion)  
**Status:** Resolved (PR Pending Review)  
**MTTR:** **38 seconds** (vs manual benchmark ~45 minutes)  
**Pull Request:** [https://github.com/zero-ops/victim-service/pull/42](https://github.com/zero-ops/victim-service/pull/42)

---

## 1. Executive Summary
At 19:28:10 UTC, PostgreSQL connection utilization reached 98% (98/100). AutoSRE autonomously ingested the alert, inspected \`pg_stat_activity\`, halted connection bleed via session termination, correlated the offending query with Git commit \`728a817\`, synthesized a context-managed cursor patch, validated the fix inside a Docker sandbox across 2 iterations (re-patching after attempt #1 failure), and submitted a guarded pull request awaiting human review.

---

## 2. Root Cause Analysis (RCA)
- **Offending Commit:** \`728a817\` - *"perf(reports): add fast raw-sql user activity report"* by Charlie Contributor.
- **Defect:** In \`analytics/views.py\`, \`user_activity_report\` initialized a raw DB cursor via \`cursor = connection.cursor()\` without invoking \`cursor.close()\` or employing a Python context manager (\`with connection.cursor() as cursor:\`).
- **Impact:** Each HTTP request to \`/api/reports/user-activity/\` held an unreleased PostgreSQL transaction open in \`idle in transaction\` state. Under normal traffic, available connection slots (100) were fully exhausted within 3 minutes.`
  },
  config: {
    mode: "cached" as const,
    max_attempts: 3
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<ApiResponse<T>> {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 60))
    return handleMockRequest<T>(path, options)
  }

  const url = `${BASE_URL}/api/v1${path}`
  try {
    const res = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...options.headers,
      },
    })
    const json = await res.json()
    return json as ApiResponse<T>
  } catch (err: any) {
    return {
      data: null as unknown as T,
      error: { code: "NETWORK_ERROR", message: err.message || "Failed to reach backend API" },
      meta: { timestamp: new Date().toISOString() }
    }
  }
}

function handleMockRequest<T>(path: string, options: RequestInit): ApiResponse<T> {
  const method = options.method || "GET"

  if (path === "/health") {
    return {
      data: { status: "healthy", service: "autosre_api (mock)", version: "1.0.0" } as unknown as T,
      error: null,
      meta: { timestamp: new Date().toISOString() }
    }
  }

  if (path === "/incidents") {
    return {
      data: [mockStore.incident] as unknown as T,
      error: null,
      meta: { timestamp: new Date().toISOString() }
    }
  }

  if (path.startsWith("/incidents/") && path.endsWith("/diff")) {
    return {
      data: { diff: mockStore.incident.unified_diff, incident_id: mockStore.incident.id } as unknown as T,
      error: null,
      meta: { timestamp: new Date().toISOString() }
    }
  }

  if (path.startsWith("/incidents/") && path.endsWith("/postmortem")) {
    return {
      data: { markdown: mockStore.incident.postmortem, incident_id: mockStore.incident.id } as unknown as T,
      error: null,
      meta: { timestamp: new Date().toISOString() }
    }
  }

  if (path.startsWith("/incidents/")) {
    return {
      data: mockStore.incident as unknown as T,
      error: null,
      meta: { timestamp: new Date().toISOString() }
    }
  }

  if (path === "/telemetry/connections") {
    return {
      data: { active: 3, idle: 12, idle_in_transaction: 0, max: 100, total: 15 } as unknown as T,
      error: null,
      meta: { timestamp: new Date().toISOString() }
    }
  }

  if (path === "/telemetry/connections/history") {
    const history: ConnectionHistoryPoint[] = []
    const now = Date.now()
    for (let i = 24; i >= 0; i--) {
      const timeStr = new Date(now - i * 5000).toTimeString().split(" ")[0]
      let active = 4
      let idle = 8
      let idleInTx = 0
      if (i > 8 && i < 18) {
        // Simulated spike before resolution
        idleInTx = Math.min(88, (18 - i) * 12 + 20)
        active = 6
        idle = 4
      } else if (i <= 8) {
        // After fix
        idleInTx = 0
        active = 3
        idle = 12
      }
      history.push({
        timestamp: timeStr,
        active,
        idle,
        idle_in_transaction: idleInTx,
        max: 100,
        total: active + idle + idleInTx
      })
    }
    return {
      data: history as unknown as T,
      error: null,
      meta: { timestamp: new Date().toISOString() }
    }
  }

  if (path.startsWith("/guardrails")) {
    return {
      data: { incident_id: mockStore.incident.id, checks: mockStore.incident.guardrails } as unknown as T,
      error: null,
      meta: { timestamp: new Date().toISOString() }
    }
  }

  if (path === "/config") {
    if (method === "PATCH") {
      const body = JSON.parse((options.body as string) || "{}")
      if (body.mode) mockStore.config.mode = body.mode
      if (body.max_attempts) mockStore.config.max_attempts = body.max_attempts
    }
    return {
      data: mockStore.config as unknown as T,
      error: null,
      meta: { timestamp: new Date().toISOString() }
    }
  }

  if (path === "/demo/trigger") {
    return {
      data: { status: "triggered", incident: mockStore.incident } as unknown as T,
      error: null,
      meta: { timestamp: new Date().toISOString() }
    }
  }

  if (path === "/demo/reset") {
    return {
      data: { status: "reset_complete" } as unknown as T,
      error: null,
      meta: { timestamp: new Date().toISOString() }
    }
  }

  return {
    data: null as unknown as T,
    error: { code: "NOT_FOUND", message: "Path not found" },
    meta: { timestamp: new Date().toISOString() }
  }
}

// Single API client exposing all operations
export const apiClient = {
  isMockMode: () => USE_MOCK,

  getHealth: () => request<{ status: string; service: string }>("/health"),

  getIncidents: () => request<Incident[]>("/incidents"),

  getIncident: (id: string) => request<Incident>(`/incidents/${id}`),

  getDiff: (id: string) => request<{ diff: string; incident_id: string }>(`/incidents/${id}/diff`),

  getPostmortem: (id: string) => request<{ markdown: string; incident_id: string }>(`/incidents/${id}/postmortem`),

  getTelemetryCurrent: () => request<ConnectionTelemetry>("/telemetry/connections"),

  getTelemetryHistory: () => request<ConnectionHistoryPoint[]>("/telemetry/connections/history"),

  getGuardrails: (incidentId?: string) => request<GuardrailsResponse>(incidentId ? `/guardrails?incident_id=${incidentId}` : "/guardrails"),

  getConfig: () => request<SystemConfig>("/config"),

  updateConfig: (config: Partial<SystemConfig>) => request<SystemConfig>("/config", {
    method: "PATCH",
    body: JSON.stringify(config),
  }),

  triggerDemo: () => request<{ status: string; incident: Incident }>("/demo/trigger", { method: "POST" }),

  resetDemo: () => request<{ status: string }>("/demo/reset", { method: "POST" }),

  /**
   * SSE Stream connection with native EventSource and realistic mock simulator.
   * Delivers one event per timeline entry: {ts, tag, message, state}
   */
  subscribeTimeline(
    incidentId: string,
    onEvent: (event: TimelineEntry) => void,
    onError?: (err: any) => void
  ): () => void {
    if (USE_MOCK) {
      let isCancelled = false
      const fullTimeline = [...mockStore.incident.timeline]
      let index = 0

      const timer = setInterval(() => {
        if (isCancelled) return
        if (index < fullTimeline.length) {
          onEvent(fullTimeline[index])
          index++
        } else {
          clearInterval(timer)
        }
      }, 700)

      return () => {
        isCancelled = true
        clearInterval(timer)
      }
    }

    const eventSource = new EventSource(`${BASE_URL}/api/v1/incidents/${incidentId}/stream`)

    eventSource.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data) as TimelineEntry
        onEvent(data)
      } catch (err) {
        // Heartbeat or comment
      }
    }

    eventSource.onerror = (err) => {
      if (onError) onError(err)
      eventSource.close()
    }

    return () => {
      eventSource.close()
    }
  }
}
