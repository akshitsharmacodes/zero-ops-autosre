import type { IncidentStatus } from "@/types/api"

export const clock = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleTimeString([], { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" }) : ""

export function duration(seconds?: number | null): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return "—"
  const s = Math.max(0, Math.round(seconds))
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  return m < 60 ? `${m}m ${s % 60}s` : `${Math.floor(m / 60)}h ${m % 60}m`
}

export const secondsBetween = (from?: string | null, to?: string | null) =>
  from ? ((to ? new Date(to).getTime() : Date.now()) - new Date(from).getTime()) / 1000 : null

export const STATUS_LABEL: Record<IncidentStatus, string> = {
  ALERT_RECEIVED: "Alert received",
  MITIGATING: "Stopping the bleeding",
  DIAGNOSING: "Diagnosing",
  CORRELATING: "Finding the cause",
  PATCHING: "Agent fixing",
  TESTING_IN_SANDBOX: "Testing in sandbox",
  PR_CREATED: "PR open",
  UPDATING_PR: "Repairing PR",
  READY_TO_MERGE: "Ready to merge",
  RESOLVED: "Resolved",
  ESCALATED: "Escalated",
}

export const STATUS_TONE: Record<IncidentStatus, "active" | "done" | "failed" | "waiting"> = {
  ALERT_RECEIVED: "active",
  MITIGATING: "active",
  DIAGNOSING: "active",
  CORRELATING: "active",
  PATCHING: "active",
  TESTING_IN_SANDBOX: "active",
  PR_CREATED: "active",
  UPDATING_PR: "active",
  READY_TO_MERGE: "waiting",
  RESOLVED: "done",
  ESCALATED: "failed",
}

export const TONE_CLASSES = {
  active: "bg-amber-500/10 text-amber-300 border-amber-500/30",
  done: "bg-emerald-500/10 text-emerald-300 border-emerald-500/30",
  failed: "bg-red-500/10 text-red-300 border-red-500/30",
  waiting: "bg-sky-500/10 text-sky-300 border-sky-500/30",
  pending: "bg-zinc-800/60 text-zinc-500 border-zinc-700/60",
}
