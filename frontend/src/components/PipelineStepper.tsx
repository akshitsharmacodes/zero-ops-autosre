import React from "react"
import { AlertCircle, Bell, CheckCircle2, GitMerge, GitPullRequest, Loader2, Search, ShieldCheck, Siren, Wrench } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { STATUS_LABEL, TONE_CLASSES } from "@/lib/format"
import type { Incident, IncidentStatus } from "@/types/api"

type StepState = "done" | "active" | "failed" | "pending" | "waiting"

const STEPS: { id: string; label: string; icon: React.ElementType; states: IncidentStatus[] }[] = [
  { id: "alert", label: "Alert", icon: Bell, states: ["ALERT_RECEIVED"] },
  { id: "diag", label: "Diagnosing", icon: Search, states: ["DIAGNOSING"] },
  { id: "mitigate", label: "Stop the bleeding", icon: Siren, states: ["MITIGATING"] },
  { id: "corr", label: "Root cause", icon: Search, states: ["CORRELATING"] },
  { id: "patch", label: "Patching", icon: Wrench, states: ["PATCHING"] },
  { id: "test", label: "Testing", icon: ShieldCheck, states: ["TESTING_IN_SANDBOX"] },
  { id: "pr", label: "PR created", icon: GitPullRequest, states: ["PR_CREATED", "UPDATING_PR"] },
  { id: "merge", label: "Ready → merged", icon: GitMerge, states: ["READY_TO_MERGE", "RESOLVED"] },
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
    <div className="rounded-xl border border-zinc-800 bg-zinc-950/80 px-4 py-3.5">
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 mb-3">
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
          <Badge variant="outline" className="text-xs font-mono whitespace-nowrap">Attempt {Math.max(incident.attempt, 0)}/{incident.max_attempts}</Badge>
        </div>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 min-[900px]:grid-cols-8 gap-1.5">
        {STEPS.map((step, idx) => {
          const st = stepState(idx, incident)
          const Icon = step.icon
          return (
            <div key={step.id} className={`relative flex min-h-[4.25rem] min-w-0 flex-col justify-between gap-1.5 rounded-lg border px-2 py-2 ${TONE_CLASSES[st === "active" ? "active" : st === "done" ? "done" : st === "failed" ? "failed" : st === "waiting" ? "waiting" : "pending"]}`}>
              {st === "active" && (
                <span
                  className="absolute -right-1 -top-1 h-2.5 w-2.5 rounded-full bg-emerald-400 ring-2 ring-zinc-950"
                  title="Running now"
                  aria-label="Running now"
                />
              )}
              <div className="flex items-center justify-between gap-1">
                <Icon className="h-3.5 w-3.5 shrink-0" />
                {st === "done" && <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />}
                {st === "active" && <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />}
                {st === "failed" && <AlertCircle className="h-3.5 w-3.5 shrink-0" />}
              </div>
              <div className="text-[11px] font-semibold leading-snug text-balance">{step.label}</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
