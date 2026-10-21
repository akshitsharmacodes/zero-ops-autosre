export type AgentState =
  | "ALERT_RECEIVED"
  | "DIAGNOSING"
  | "CORRELATING"
  | "PATCHING"
  | "TESTING_IN_SANDBOX"
  | "PR_CREATED"
  | "RESOLVED"
  | "ESCALATED"

export type LogTag = "ALERT" | "DIAG" | "CORR" | "PATCH" | "TEST" | "PR"

export interface TimelineEntry {
  ts: string
  tag: LogTag
  message: string
  state: AgentState
}

export interface SuspectCommit {
  sha: string
  author: string
  committed_date: string
  message: string
  file: string
  leaking_code?: string
  confidence?: number
  risk?: "Low" | "Med" | "High"
}

export interface SandboxResult {
  passed: boolean
  exit_code: number
  output: string
  engine?: string
  isolation?: string
}

export interface GuardrailCheck {
  id: string
  name: string
  passed: boolean
  details: string
}

export interface Incident {
  id: string
  status: AgentState
  attempt: number
  max_attempts: number
  suspect_commit: SuspectCommit
  leaking_code: string
  patch: string
  risk: "Low" | "Med" | "High"
  confidence: number
  sandbox_result: SandboxResult
  pr_url: string | null
  mttr_seconds: number
  timeline: TimelineEntry[]
  guardrails?: GuardrailCheck[]
  unified_diff?: string
  postmortem?: string
}

export interface ConnectionTelemetry {
  active: number
  idle: number
  idle_in_transaction: number
  max: number
  total?: number
  live?: boolean
}

export interface ConnectionHistoryPoint {
  timestamp: string
  active: number
  idle: number
  idle_in_transaction: number
  max: number
  total: number
}

export interface GuardrailsResponse {
  incident_id: string
  checks: GuardrailCheck[]
}

export interface SystemConfig {
  mode: "live" | "cached" | "replay"
  max_attempts: number
}

export interface ApiResponse<T> {
  data: T
  error: { code: string; message: string } | null
  meta: { timestamp: string }
}
