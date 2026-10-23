// Single API client for the AutoSRE backend. No mock data: what you see is what the backend reports.
import type {
  AgentStep,
  ApiResponse,
  ConnectionHistoryPoint,
  ConnectionTelemetry,
  GuardrailCheck,
  Incident,
  IncidentSummary,
  SandboxRun,
  SystemConfig,
  SystemStatus,
  TimelineEntry,
  TrafficStatus,
} from "@/types/api"

export const BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "")

export class ApiRequestError extends Error {
  code: string
  status: number
  constructor(code: string, message: string, status: number) {
    super(message)
    this.code = code
    this.status = status
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${BASE_URL}/api/v1${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init.headers || {}) },
    })
  } catch {
    throw new ApiRequestError("BACKEND_UNREACHABLE", `Cannot reach the AutoSRE backend at ${BASE_URL}`, 0)
  }
  let body: ApiResponse<T> | null = null
  try {
    body = (await res.json()) as ApiResponse<T>
  } catch {
    throw new ApiRequestError("BAD_RESPONSE", `Unexpected response (${res.status})`, res.status)
  }
  if (!res.ok || body.error) {
    throw new ApiRequestError(body.error?.code || "HTTP_ERROR", body.error?.message || `HTTP ${res.status}`, res.status)
  }
  return body.data
}

const post = <T>(path: string, data: unknown = {}) => request<T>(path, { method: "POST", body: JSON.stringify(data) })

export const api = {
  health: () => request<{ status: string; version: string }>("/health"),
  system: () => request<SystemStatus>("/system"),
  incidents: () => request<IncidentSummary[]>("/incidents"),
  incident: (id: string) => request<Incident>(`/incidents/${id}`),
  diff: (id: string) => request<{ diff: string; suspect_commit_diff: string }>(`/incidents/${id}/diff`),
  postmortem: (id: string) => request<{ markdown: string }>(`/incidents/${id}/postmortem`),
  steps: (id: string) => request<AgentStep[]>(`/incidents/${id}/steps`),
  sandboxRuns: (id: string) => request<SandboxRun[]>(`/incidents/${id}/sandbox-runs`),
  guardrails: (id?: string) =>
    request<{ incident_id: string | null; checks: GuardrailCheck[] }>(`/guardrails${id ? `?incident_id=${id}` : ""}`),
  telemetry: () => request<ConnectionTelemetry>("/telemetry/connections"),
  telemetryHistory: (minutes = 10) => request<ConnectionHistoryPoint[]>(`/telemetry/connections/history?minutes=${minutes}`),
  config: () => request<SystemConfig>("/config"),
  updateConfig: (patch: Partial<SystemConfig>) =>
    request<SystemConfig>("/config", { method: "PATCH", body: JSON.stringify(patch) }),
  triggerDemo: () => post<{ traffic: TrafficStatus; message: string }>("/demo/trigger"),
  traffic: () => request<TrafficStatus>("/demo/traffic"),
  replay: () => post<{ incident: IncidentSummary }>("/demo/replay"),
  teammatePush: () => post<{ sha: string }>("/demo/teammate-push"),
  merge: (id: string) => post<{ merged: boolean; sha: string }>(`/incidents/${id}/merge`),
  reset: (opts: { clear_incidents?: boolean; reseed_repo?: boolean }) => post<Record<string, unknown>>("/demo/reset", opts),
  auditUrl: (id: string) => `${BASE_URL}/api/v1/incidents/${id}/audit`,
}

/** Live timeline via Server-Sent Events. The browser reconnects automatically (Last-Event-ID). */
export function subscribeTimeline(
  incidentId: string,
  handlers: { onEvent: (e: TimelineEntry) => void; onStatus?: (status: string) => void; onEnd?: () => void },
): () => void {
  const source = new EventSource(`${BASE_URL}/api/v1/incidents/${incidentId}/stream`)
  source.addEventListener("timeline", (msg) => handlers.onEvent(JSON.parse((msg as MessageEvent).data)))
  source.addEventListener("status", (msg) => handlers.onStatus?.(JSON.parse((msg as MessageEvent).data).status))
  source.addEventListener("end", () => {
    handlers.onEnd?.()
    source.close()
  })
  return () => source.close()
}
