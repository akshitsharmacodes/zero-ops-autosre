import React, { useState } from "react"
import { toast } from "sonner"
import { ShieldQuestion } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useDecide } from "@/hooks/useAutoSRE"
import type { Incident } from "@/types/api"

/** Review mode: AutoSRE is waiting for a person before an impactful step. */
export const ApprovalCard: React.FC<{ incident?: Incident }> = ({ incident }) => {
  const decide = useDecide()
  const [name, setName] = useState("")
  const pending = incident?.pending_approval
  if (!incident || !pending?.gate || pending.decision) return null

  const send = (decision: "approve" | "deny") =>
    decide.mutate(
      { id: incident.id, gate: pending.gate!, decision, by: name || undefined },
      {
        onSuccess: () => toast.success(decision === "approve" ? "Approved" : "Denied", { description: pending.title }),
        onError: (e) => toast.error((e as Error).message),
      },
    )

  return (
    <div className="rounded-xl border border-sky-500/40 bg-sky-500/5 p-4 flex flex-col md:flex-row md:items-center gap-3">
      <ShieldQuestion className="h-6 w-6 text-sky-300 shrink-0" />
      <div className="flex-1">
        <div className="text-[11px] uppercase tracking-wider text-sky-300 font-semibold">Human approval needed · {pending.gate}</div>
        <div className="text-sm text-zinc-100">{pending.title}</div>
        <div className="text-[11px] text-zinc-400 font-mono">
          {Object.entries(pending.details || {}).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(", ") : String(v)}`).join(" · ")}
        </div>
      </div>
      <input value={name} onChange={(e) => setName(e.target.value)} placeholder="your name"
             className="bg-zinc-900 border border-zinc-800 rounded px-2 py-1.5 text-xs text-zinc-200 w-32" />
      <div className="flex gap-2">
        <Button size="sm" variant="sre" disabled={decide.isPending} onClick={() => send("approve")}>Approve</Button>
        <Button size="sm" variant="outline" disabled={decide.isPending} onClick={() => send("deny")}>Deny</Button>
      </div>
    </div>
  )
}
