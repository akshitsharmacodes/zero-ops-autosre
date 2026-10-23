import React, { useEffect, useState } from "react"
import { Timer } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { duration, secondsBetween } from "@/lib/format"
import type { Incident } from "@/types/api"

const MANUAL_MTTR_SECONDS = 45 * 60 // typical manual response, for comparison (AO-1)

export const MttrCard: React.FC<{ incident?: Incident }> = ({ incident }) => {
  const [, tick] = useState(0)
  const running = !!incident && !incident.ready_at && !incident.finished_at
  useEffect(() => {
    if (!running) return
    const t = setInterval(() => tick((n) => n + 1), 1000)
    return () => clearInterval(t)
  }, [running])

  const toFix = incident ? (incident.mttr_seconds ?? secondsBetween(incident.created_at, null)) : null
  const toMitigate = incident?.time_to_mitigate_seconds ?? null
  const pct = toFix ? Math.min(100, (toFix / MANUAL_MTTR_SECONDS) * 100) : 0

  return (
    <Card className="border-zinc-800 bg-zinc-950">
      <CardHeader className="py-2.5 px-4 border-b border-zinc-800/80 bg-zinc-900/50 space-y-0 flex flex-row items-center gap-2">
        <Timer className="h-4 w-4 text-emerald-400" />
        <CardTitle className="text-xs uppercase tracking-wider font-bold text-zinc-200">Time to recovery</CardTitle>
      </CardHeader>
      <CardContent className="p-4 space-y-3">
        {!incident ? (
          <p className="text-xs text-zinc-500">Starts when an alert arrives.</p>
        ) : (
          <>
            <div>
              <div className="text-[11px] text-zinc-400">Service restored (stop-the-bleeding)</div>
              <div className="text-xl font-mono font-bold text-orange-300">{toMitigate !== null ? duration(toMitigate) : running ? "…" : "—"}</div>
            </div>
            <div>
              <div className="text-[11px] text-zinc-400">Alert → verified fix ready to merge {running && "(running)"}</div>
              <div className={`text-2xl font-mono font-bold ${incident.status === "ESCALATED" ? "text-red-400" : "text-emerald-400"}`}>
                {duration(toFix)}
              </div>
            </div>
            <div>
              <div className="flex justify-between text-[10px] text-zinc-500 mb-1">
                <span>AutoSRE</span><span>typical manual ≈ 45 min</span>
              </div>
              <div className="h-2 rounded-full bg-zinc-800 overflow-hidden">
                <div className="h-full bg-emerald-500 transition-all" style={{ width: `${Math.max(pct, 1)}%` }} />
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
