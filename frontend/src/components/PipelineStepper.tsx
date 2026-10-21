import React from "react"
import { Badge } from "@/components/ui/badge"
import { CheckCircle2, RotateCw, AlertCircle, GitPullRequest, Search, Wrench, ShieldCheck, ArrowRight } from "lucide-react"
import { AgentState } from "@/types/api"

interface PipelineStepperProps {
  currentState: AgentState
  attempt: number
  maxAttempts: number
}

interface StepConfig {
  id: string
  label: string
  description: string
  icon: React.ComponentType<{ className?: string }>
  associatedStates: AgentState[]
}

const STEPS: StepConfig[] = [
  {
    id: "diag",
    label: "Diagnosing",
    description: "pg_stat_activity & stop bleeding",
    icon: Search,
    associatedStates: ["ALERT_RECEIVED", "DIAGNOSING", "CORRELATING"],
  },
  {
    id: "patch",
    label: "Patching",
    description: "LLM synthesis & context manager",
    icon: Wrench,
    associatedStates: ["PATCHING"],
  },
  {
    id: "test",
    label: "Testing in Sandbox",
    description: "pytest & docker-py isolation",
    icon: ShieldCheck,
    associatedStates: ["TESTING_IN_SANDBOX"],
  },
  {
    id: "delivery",
    label: "PR Created",
    description: "Guardrails, draft PR & post-mortem",
    icon: GitPullRequest,
    associatedStates: ["PR_CREATED", "RESOLVED"],
  },
]

export const PipelineStepper: React.FC<PipelineStepperProps> = ({
  currentState,
  attempt,
  maxAttempts,
}) => {
  // Determine step status
  const getStepStatus = (index: number): "done" | "active" | "failed" | "pending" => {
    if (currentState === "ESCALATED") {
      if (index === 2) return "failed"
    }

    if (currentState === "RESOLVED" || currentState === "PR_CREATED") {
      return "done"
    }

    // Active state index
    let activeIndex = 0
    if (["ALERT_RECEIVED", "DIAGNOSING", "CORRELATING"].includes(currentState)) activeIndex = 0
    else if (currentState === "PATCHING") activeIndex = 1
    else if (currentState === "TESTING_IN_SANDBOX") activeIndex = 2
    else activeIndex = 3

    if (index < activeIndex) return "done"
    if (index === activeIndex) return "active"
    return "pending"
  }

  // Show failed retry loop-back indicator if on attempt >= 2 and currently in patching or after sandbox
  const isRetrying = attempt > 1

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-950/80 p-5 shadow-lg backdrop-blur-sm relative overflow-hidden">
      {/* Background glow on active */}
      <div className="absolute top-0 right-0 w-96 h-full bg-gradient-to-l from-emerald-500/5 to-transparent pointer-events-none" />

      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-5 pb-4 border-b border-zinc-800/60">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold tracking-wider uppercase text-zinc-300 font-mono">
              Autonomous Remediation Pipeline
            </h2>
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>
          </div>
          <p className="text-xs text-zinc-400 mt-0.5">
            Multi-agent state machine with self-healing feedback loop
          </p>
        </div>

        <div className="flex items-center gap-2">
          {isRetrying && (
            <Badge variant="destructive" className="flex items-center gap-1 text-[11px] font-mono animate-pulse">
              <RotateCw className="h-3 w-3 animate-spin" />
              Self-Healing Loop Triggered
            </Badge>
          )}
          <Badge variant="outline" className="text-xs font-mono border-zinc-700 bg-zinc-900 text-zinc-200">
            Attempt {Math.max(1, attempt)}/{maxAttempts}
          </Badge>
        </div>
      </div>

      {/* Stepper Grid */}
      <div className="relative">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 relative z-10">
          {STEPS.map((step, idx) => {
            const status = getStepStatus(idx)
            const Icon = step.icon

            return (
              <div
                key={step.id}
                className={`relative flex flex-col p-4 rounded-lg border transition-all duration-300 ${
                  status === "active"
                    ? "border-amber-500/50 bg-amber-500/5 shadow-md shadow-amber-500/10"
                    : status === "done"
                    ? "border-emerald-500/40 bg-emerald-500/5"
                    : status === "failed"
                    ? "border-red-500/50 bg-red-500/5"
                    : "border-zinc-800/80 bg-zinc-900/40 opacity-70"
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <div
                      className={`h-7 w-7 rounded-md flex items-center justify-center ${
                        status === "active"
                          ? "bg-amber-500 text-zinc-950 animate-pulse"
                          : status === "done"
                          ? "bg-emerald-500 text-zinc-950"
                          : status === "failed"
                          ? "bg-red-500 text-zinc-950"
                          : "bg-zinc-800 text-zinc-400"
                      }`}
                    >
                      <Icon className="h-4 w-4" />
                    </div>
                    <span className="text-xs font-semibold text-zinc-200">
                      {step.label}
                    </span>
                  </div>

                  {status === "done" && (
                    <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                  )}
                  {status === "active" && (
                    <RotateCw className="h-3.5 w-3.5 text-amber-400 animate-spin" />
                  )}
                  {status === "failed" && (
                    <AlertCircle className="h-4 w-4 text-red-400" />
                  )}
                </div>

                <p className="text-[11px] text-zinc-400 leading-relaxed mt-1">
                  {step.description}
                </p>

                {/* Progress bar inside each card */}
                <div className="mt-3 h-1 w-full rounded-full bg-zinc-800 overflow-hidden">
                  <div
                    className={`h-full transition-all duration-500 ${
                      status === "done"
                        ? "w-full bg-emerald-500"
                        : status === "active"
                        ? "w-2/3 bg-amber-400 animate-pulse"
                        : status === "failed"
                        ? "w-full bg-red-500"
                        : "w-0"
                    }`}
                  />
                </div>
              </div>
            )
          })}
        </div>

        {/* Loop-back retry indicator banner */}
        {isRetrying && (
          <div className="mt-3 py-1.5 px-3 rounded-lg border border-red-500/30 bg-red-500/10 flex items-center justify-between text-xs text-red-300">
            <div className="flex items-center gap-2">
              <RotateCw className="h-3.5 w-3.5 text-red-400 animate-spin" />
              <span>
                <strong className="font-semibold text-red-200">Retry Feedback Loop:</strong> Sandbox failure in Attempt 1 captured stack trace → fed to LLM → successfully synthesized Attempt 2.
              </span>
            </div>
            <span className="font-mono text-[10px] bg-red-950/60 px-2 py-0.5 rounded border border-red-800/40">
              Stack Trace Feedback
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
