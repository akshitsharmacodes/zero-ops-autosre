import React, { useEffect, useState } from "react"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Timer, Zap, TrendingDown, Clock } from "lucide-react"

interface MttrCardProps {
  mttrSeconds: number
  isRunning: boolean
}

export const MttrCard: React.FC<MttrCardProps> = ({ mttrSeconds, isRunning }) => {
  const [timer, setTimer] = useState(mttrSeconds || 38)

  useEffect(() => {
    if (isRunning) {
      const interval = setInterval(() => {
        setTimer((prev) => prev + 1)
      }, 1000)
      return () => clearInterval(interval)
    } else if (mttrSeconds > 0) {
      setTimer(mttrSeconds)
    }
  }, [isRunning, mttrSeconds])

  return (
    <Card className="border-zinc-800 bg-gradient-to-br from-zinc-950 via-zinc-950 to-emerald-950/20 p-5 relative overflow-hidden">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="h-8 w-8 rounded-lg bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center">
            <Timer className="h-4 w-4 text-emerald-400" />
          </div>
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-300 font-mono">
              Mean Time to Remediate (MTTR)
            </h3>
            <p className="text-[11px] text-zinc-500">Autonomous Incident Life Cycle</p>
          </div>
        </div>

        <Badge variant={isRunning ? "warning" : "success"} className="font-mono text-xs">
          {isRunning ? "TIMER RUNNING" : "RESOLVED"}
        </Badge>
      </div>

      <div className="grid grid-cols-2 gap-4 items-center">
        {/* AutoSRE Running Timer */}
        <div className="p-3 rounded-lg bg-zinc-900/60 border border-zinc-800">
          <span className="text-[11px] text-zinc-400 font-mono">AutoSRE Autonomous</span>
          <div className="flex items-baseline gap-1 mt-1">
            <span className="text-3xl font-extrabold tracking-tight text-emerald-400 font-mono">
              {timer}s
            </span>
            <span className="text-xs text-zinc-500 font-mono">elapsed</span>
          </div>
          <div className="flex items-center gap-1 text-[10px] text-emerald-400/90 mt-1 font-mono">
            <Zap className="h-3 w-3" />
            <span>98.6% faster response</span>
          </div>
        </div>

        {/* Manual Benchmark */}
        <div className="p-3 rounded-lg bg-zinc-900/60 border border-zinc-800">
          <span className="text-[11px] text-zinc-400 font-mono">Manual On-Call Benchmark</span>
          <div className="flex items-baseline gap-1 mt-1">
            <span className="text-3xl font-extrabold tracking-tight text-zinc-400 font-mono">
              ~45m
            </span>
            <span className="text-xs text-zinc-500 font-mono">average</span>
          </div>
          <div className="flex items-center gap-1 text-[10px] text-zinc-400 mt-1 font-mono">
            <Clock className="h-3 w-3" />
            <span>P1 Human triage SLA</span>
          </div>
        </div>
      </div>
    </Card>
  )
}
