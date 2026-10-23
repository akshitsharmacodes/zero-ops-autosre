import React from "react"
import { AlertCircle, Bell, CheckCircle2, GitMerge, GitPullRequest, Loader2, Search, ShieldCheck, Siren, Wrench } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { STATUS_LABEL, TONE_CLASSES } from "@/lib/format"
import type { Incident, IncidentStatus } from "@/types/api"

type StepState = "done" | "active" | "failed" | "pending" | "waiting"

const STEPS: { id: string; label: string; hint: string; icon: React.ElementType; states: IncidentStatus[] }[] = [
  { id: "alert", label: "Alert", hint: "Monitor / webhook", icon: Bell, states: ["ALERT_RECEIVED"] },
  { id: "diag", label: "Diagnosing", hint: "pg_stat_activity + logs", icon: Search, states: ["DIAGNOSING"] },
  { id: "mitigate", label: "Stop the bleeding", hint: "end stuck sessions", icon: Siren, states: ["MITIGATING"] },
  { id: "corr", label: "Root cause", hint: "git history scoring", icon: Search, states: ["CORRELATING"] },
  { id: "patch", label: "Patching", hint: "coding agent", icon: Wrench, states: ["PATCHING"] },
  { id: "test", label: "Testing", hint: "sandbox", icon: ShieldCheck, states: ["TESTING_IN_SANDBOX"] },
  { id: "pr", label: "PR created", hint: "watch & repair", icon: GitPullRequest, states: ["PR_CREATED", "UPDATING_PR"] },
  { id: "merge", label: "Ready → merged", hint: "human merges", icon: GitMerge, states: ["READY_TO_MERGE", "RESOLVED"] },
]

function lastActiveIndex(incident: Incident): number {
  // For escalations, find the last state reached from the timeline.
  const states = incident.timeline.map((e) => e.state).filter((s) => s !== "ESCALATED" && s !== "AWAITING_APPROVAL")
  const last = states[states.length - 1] || "ALERT_RECEIVED"
  return STEPS.findIndex((s) => s.states.includes(last))
}

function stepState(idx: number, incident: Incident): StepState {
  const status = incident.status
  // PATCHING <-> TESTING alternate during retries; treat both as the "fix" phase.
  const current = status === "ESCALATED" || status === "AWAITING_APPROVAL" ? lastActiveIndex(incident) : STEPS.findIndex((s) => s.states.includes(status))
  if (status === "ESCALATED") return idx < current ? "done" : idx === current ? "failed" : "pending"
  if (status === "RESOLVED") return "done"
  if (status === "READY_TO_MERGE") return idx < 7 ? "done" : "waiting"
  const inFix = status === "PATCHING" || status === "TESTING_IN_SANDBOX"
  if (inFix && (idx === 4 || idx === 5)) return STEPS[idx].states.includes(status) ? "active" : incident.attempt > 0 ? "done" : "pending"
  return idx < current ? "done" : idx === current ? "active" : "pending"
}

export const PipelineStepper: React.FC<{ incident?: Incident }> = ({ incident }) => {
  if (!incident) {
    return (
      <div className="rounded-xl border border-zinc-800 bg-zinc-950/80 p-5 text-sm text-zinc-400">
        No incident yet. Open <span className="text-emerald-400">Controls → Start incident</span> to send traffic to the victim
        service; the monitor will raise the alert by itself when connections pass the threshold.
      </div>
    )
  }
  const rounds = incident.pull_request?.rounds || 0
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-950/80 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div>
          <h2 className="text-sm font-semibold tracking-wider uppercase text-zinc-300 font-mono">{incident.id}</h2>
          <p className="text-xs text-zinc-400 mt-0.5">
            {STATUS_LABEL[incident.status]}
            {incident.status === "ESCALATED" && incident.escalation_reason ? ` — ${incident.escalation_reason}` : ""}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {incident.attempt > 1 && (
            <Badge variant="destructive" className="text-[11px] font-mono">Self-healing: retried with test feedback</Badge>
          )}
          {rounds > 0 && <Badge variant="info" className="text-[11px] font-mono">PR repair rounds: {rounds}</Badge>}
          <Badge variant="outline" className="text-xs font-mono">Attempt {Math.max(incident.attempt, 0)}/{incident.max_attempts}</Badge>
        </div>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2">
        {STEPS.map((step, idx) => {
          const st = stepState(idx, incident)
          const Icon = step.icon
          return (
            <div key={step.id} className={`p-2.5 rounded-lg border ${TONE_CLASSES[st === "active" ? "active" : st === "done" ? "done" : st === "failed" ? "failed" : st === "waiting" ? "waiting" : "pending"]}`}>
              <div className="flex items-center justify-between">
                <Icon className="h-4 w-4" />
                {st === "done" && <CheckCircle2 className="h-3.5 w-3.5" />}
                {st === "active" && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                {st === "failed" && <AlertCircle className="h-3.5 w-3.5" />}
              </div>
              <div className="mt-1.5 text-[11px] font-semibold leading-tight">{step.label}</div>
              <div className="text-[10px] opacity-70 leading-tight">{step.hint}</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
