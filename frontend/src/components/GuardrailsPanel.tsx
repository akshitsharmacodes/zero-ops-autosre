import React from "react"
import { CheckCircle2, CircleDashed, ShieldAlert, ShieldCheck, XCircle } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import type { GuardrailCheck } from "@/types/api"

export const GuardrailsPanel: React.FC<{ checks: GuardrailCheck[] }> = ({ checks }) => {
  const passed = checks.filter((c) => c.status === "passed").length
  const failed = checks.filter((c) => c.status === "failed").length
  return (
    <Card className="border-zinc-800 bg-zinc-950 h-full">
      <CardHeader className="py-2.5 px-4 border-b border-zinc-800/80 bg-zinc-900/50 space-y-0 flex flex-row items-center justify-between">
        <div className="flex items-center gap-2">
          {failed ? <ShieldAlert className="h-4 w-4 text-amber-400" /> : <ShieldCheck className="h-4 w-4 text-emerald-400" />}
          <CardTitle className="text-xs uppercase tracking-wider font-bold text-zinc-200">Guardrails</CardTitle>
        </div>
        <span className="text-[11px] font-mono text-zinc-400">{passed}/{checks.length} passed</span>
      </CardHeader>
      <CardContent className="p-3 space-y-2">
        {checks.map((c) => (
          <div key={c.id} className="flex gap-2 items-start">
            {c.status === "passed" && <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0 mt-0.5" />}
            {c.status === "failed" && <XCircle className="h-4 w-4 text-red-400 shrink-0 mt-0.5" />}
            {c.status === "pending" && <CircleDashed className="h-4 w-4 text-zinc-600 shrink-0 mt-0.5" />}
            <div>
              <div className={`text-xs font-medium ${c.status === "pending" ? "text-zinc-500" : "text-zinc-200"}`}>{c.name}</div>
              <div className="text-[10.5px] text-zinc-500 leading-snug">{c.details}</div>
            </div>
          </div>
        ))}
        <p className="text-[10px] text-zinc-600 pt-1">
          Enforced by code inside the agent's tools — a refused edit is sent back to the agent with the reason.
        </p>
      </CardContent>
    </Card>
  )
}
