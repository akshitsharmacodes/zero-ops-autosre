import React from "react"
import { GitCommit } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import type { Incident } from "@/types/api"

const RISK_VARIANT = { Low: "success", Medium: "warning", High: "destructive" } as const

export const SuspectCard: React.FC<{ incident?: Incident }> = ({ incident }) => {
  const s = incident?.suspect
  const commit = s?.commit
  const loc = s?.location
  const risk = incident?.fix?.risk
  return (
    <Card className="border-zinc-800 bg-zinc-950">
      <CardHeader className="py-2.5 px-4 border-b border-zinc-800/80 bg-zinc-900/50 space-y-0 flex flex-row items-center justify-between">
        <div className="flex items-center gap-2">
          <GitCommit className="h-4 w-4 text-purple-400" />
          <CardTitle className="text-xs uppercase tracking-wider font-bold text-zinc-200">Root cause</CardTitle>
        </div>
        {risk && <Badge variant={RISK_VARIANT[risk]} className="text-[10px]">fix risk: {risk}</Badge>}
      </CardHeader>
      <CardContent className="p-4 space-y-2">
        {!commit ? (
          <p className="text-xs text-zinc-500">The suspect commit appears here after correlation.</p>
        ) : (
          <>
            <div className="text-xs">
              <span className="font-mono text-purple-300">{commit.short_sha}</span>{" "}
              <span className="text-zinc-200">{commit.message}</span>
            </div>
            <div className="text-[11px] text-zinc-400">by {commit.author}</div>
            <div>
              <div className="flex justify-between text-[10px] text-zinc-500 mb-1">
                <span>confidence</span><span>{Math.round((s?.confidence || 0) * 100)}%</span>
              </div>
              <div className="h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                <div className="h-full bg-purple-500" style={{ width: `${(s?.confidence || 0) * 100}%` }} />
              </div>
            </div>
            {loc?.start_line && (
              <div className="text-[11px] text-zinc-400 font-mono">
                {loc.file}:{loc.start_line}-{loc.end_line} {loc.function && `· ${loc.function}()`}
              </div>
            )}
            {loc?.snippet && (
              <pre className="text-[10.5px] bg-zinc-900 border border-zinc-800 rounded p-2 max-h-36 overflow-auto text-zinc-300">{loc.snippet}</pre>
            )}
            <ul className="space-y-0.5">
              {(s?.evidence || []).slice(0, 4).map((e) => (
                <li key={e} className="text-[10.5px] text-zinc-400 leading-snug">• {e}</li>
              ))}
            </ul>
          </>
        )}
      </CardContent>
    </Card>
  )
}
