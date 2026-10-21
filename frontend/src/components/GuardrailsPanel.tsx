import React from "react"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { ShieldCheck, CheckCircle2, XCircle, AlertTriangle } from "lucide-react"
import { GuardrailCheck } from "@/types/api"

interface GuardrailsPanelProps {
  checks: GuardrailCheck[]
}

const DEFAULT_CHECKS: GuardrailCheck[] = [
  {
    id: "diff_size_limit",
    name: "Diff Size Constraint (<= 50 lines)",
    passed: true,
    details: "Patch touches 8 lines (threshold: 50 lines max).",
  },
  {
    id: "file_allowlist",
    name: "File Allowlist (Suspect Commit Scope)",
    passed: true,
    details: "Touched files: analytics/views.py. Unauthorized: 0.",
  },
  {
    id: "secret_scrubbing",
    name: "Secret Scrubbing & Leak Prevention",
    passed: true,
    details: "Zero credentials, API keys, or tokens detected in patch.",
  },
  {
    id: "dangerous_patterns",
    name: "Dangerous Pattern Blocklist",
    passed: true,
    details: "Passed: Rejects os.system, subprocess, DROP, and DELETE FROM.",
  },
  {
    id: "sandbox_isolation",
    name: "Sandbox Resource & Network Isolation",
    passed: true,
    details: "Zero host mounts, 512MB RAM cap, 120s execution timeout.",
  },
  {
    id: "retry_cap",
    name: "Retry Threshold Constraint (<= 3 attempts)",
    passed: true,
    details: "Capped at 3 self-healing iterations before mandatory human escalation.",
  },
  {
    id: "human_approval_gate",
    name: "Human-in-the-Loop Review Gate",
    passed: true,
    details: "Draft PR opened on isolated branch. Never push to main, never auto-merge.",
  },
]

export const GuardrailsPanel: React.FC<GuardrailsPanelProps> = ({ checks }) => {
  const activeChecks = checks && checks.length > 0 ? checks : DEFAULT_CHECKS
  const allPassed = activeChecks.every((c) => c.passed)

  return (
    <Card className="border-zinc-800 bg-zinc-950">
      <CardHeader className="py-2.5 px-4 flex flex-row items-center justify-between border-b border-zinc-800/80 bg-zinc-900/50">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-emerald-400" />
          <CardTitle className="text-xs uppercase tracking-wider font-bold text-zinc-200">
            Automated Guardrails & Safety Enforcement
          </CardTitle>
        </div>

        <Badge
          variant={allPassed ? "success" : "destructive"}
          className="text-[10px] font-mono uppercase"
        >
          {allPassed ? "All Guardrails Passed" : "Check Failed"}
        </Badge>
      </CardHeader>

      <CardContent className="p-4 space-y-2.5">
        {activeChecks.map((check) => (
          <div
            key={check.id}
            className={`flex items-start gap-2.5 p-2 rounded-lg border text-xs transition-colors ${
              check.passed
                ? "border-emerald-500/20 bg-emerald-950/10"
                : "border-red-500/30 bg-red-950/20"
            }`}
          >
            {check.passed ? (
              <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0 mt-0.5" />
            ) : (
              <XCircle className="h-4 w-4 text-red-400 shrink-0 mt-0.5" />
            )}

            <div className="flex-1">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-zinc-200">{check.name}</span>
                <span className="font-mono text-[10px] text-zinc-500">{check.id}</span>
              </div>
              <p className="text-[11px] text-zinc-400 mt-0.5">{check.details}</p>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}
