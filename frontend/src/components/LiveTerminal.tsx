import React, { useEffect, useRef, useState } from "react"
import { ArrowDown, Check, Copy, Terminal } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { clock } from "@/lib/format"
import type { LogTag, TimelineEntry } from "@/types/api"

const TAG: Record<LogTag, string> = {
  ALERT: "text-red-400 border-red-500/30 bg-red-500/10",
  MITIGATE: "text-orange-300 border-orange-500/30 bg-orange-500/10",
  DIAG: "text-cyan-400 border-cyan-500/30 bg-cyan-500/10",
  CORR: "text-purple-400 border-purple-500/30 bg-purple-500/10",
  PATCH: "text-amber-400 border-amber-500/30 bg-amber-500/10",
  AGENT: "text-yellow-200 border-yellow-500/20 bg-yellow-500/5",
  GUARD: "text-fuchsia-300 border-fuchsia-500/30 bg-fuchsia-500/10",
  TEST: "text-teal-300 border-teal-500/30 bg-teal-500/10",
  PR: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10",
  LOOP: "text-sky-300 border-sky-500/30 bg-sky-500/10",
}

export const LiveTerminal: React.FC<{ timeline: TimelineEntry[] }> = ({ timeline }) => {
  const ref = useRef<HTMLDivElement>(null)
  const [follow, setFollow] = useState(true)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (follow && ref.current) ref.current.scrollTop = ref.current.scrollHeight
  }, [timeline, follow])

  const copy = () => {
    navigator.clipboard.writeText(timeline.map((e) => `${clock(e.ts)} [${e.tag}] ${e.message}`).join("\n"))
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <Card className="flex flex-col h-[420px] border-zinc-800 bg-zinc-950 font-mono">
      <CardHeader className="py-2.5 px-4 flex flex-row items-center justify-between border-b border-zinc-800/80 bg-zinc-900/50 space-y-0">
        <div className="flex items-center gap-2">
          <Terminal className="h-4 w-4 text-emerald-400" />
          <CardTitle className="text-xs uppercase tracking-wider font-bold text-zinc-200">Live agent log</CardTitle>
          <span className="text-[10px] text-zinc-500">({timeline.length} events)</span>
        </div>
        <div className="flex gap-1">
          <Button variant="ghost" size="sm" onClick={() => setFollow(!follow)}
                  className={`h-7 px-2 text-[11px] gap-1 ${follow ? "text-emerald-400" : "text-zinc-500"}`}>
            <ArrowDown className="h-3 w-3" /> Follow
          </Button>
          <Button variant="ghost" size="sm" onClick={copy} className="h-7 px-2 text-[11px] gap-1 text-zinc-400">
            {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />} Copy
          </Button>
        </div>
      </CardHeader>
      <CardContent ref={ref} className="flex-1 overflow-y-auto p-3 space-y-1 text-[11.5px] leading-relaxed">
        {timeline.length === 0 && <div className="text-zinc-600">Waiting for events…</div>}
        {timeline.map((e) => (
          <div key={e.id} className="flex gap-2 items-start">
            <span className="text-zinc-600 shrink-0">{clock(e.ts)}</span>
            <span className={`shrink-0 w-[68px] text-center text-[10px] font-bold px-1 rounded border ${TAG[e.tag] || "text-zinc-400 border-zinc-700"}`}>
              {e.tag}
            </span>
            <span className="text-zinc-300 whitespace-pre-wrap break-words">{e.message}</span>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}
