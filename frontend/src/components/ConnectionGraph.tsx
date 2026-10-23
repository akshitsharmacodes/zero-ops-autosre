import React from "react"
import { AlertTriangle, Database } from "lucide-react"
import { Area, AreaChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { clock } from "@/lib/format"
import type { ConnectionHistoryPoint, ConnectionTelemetry } from "@/types/api"

interface Props {
  history: ConnectionHistoryPoint[]
  current?: ConnectionTelemetry
  error?: string
  threshold: number
}

export const ConnectionGraph: React.FC<Props> = ({ history, current, error, threshold }) => {
  const max = current?.max || history[history.length - 1]?.max || 100
  const saturated = current ? current.utilization >= threshold : false
  const data = history.map((p) => ({ ...p, time: clock(p.timestamp) }))

  return (
    <Card className="flex flex-col h-[420px] border-zinc-800 bg-zinc-950">
      <CardHeader className="py-2.5 px-4 flex flex-row items-center justify-between border-b border-zinc-800/80 bg-zinc-900/50 space-y-0">
        <div className="flex items-center gap-2">
          <Database className="h-4 w-4 text-emerald-400" />
          <CardTitle className="text-xs uppercase tracking-wider font-bold text-zinc-200">PostgreSQL connections</CardTitle>
        </div>
        {current ? (
          <div className="flex items-center gap-2">
            {saturated && (
              <Badge variant="destructive" className="text-[10px] animate-pulse gap-1">
                <AlertTriangle className="h-3 w-3" /> Exhausting
              </Badge>
            )}
            <Badge variant="outline" className="text-[11px] font-mono">{current.total} / {current.max}</Badge>
          </div>
        ) : (
          <Badge variant="warning" className="text-[10px]">telemetry unavailable</Badge>
        )}
      </CardHeader>
      <CardContent className="p-4 flex-1 flex flex-col">
        {error && !current && <p className="text-[11px] text-amber-300/80 mb-2 line-clamp-2">{error}</p>}
        <div className="flex gap-4 text-[11px] font-mono mb-2 text-zinc-400">
          <span><span className="inline-block h-2 w-2 rounded-sm bg-red-500 mr-1" />idle in transaction (stuck)</span>
          <span><span className="inline-block h-2 w-2 rounded-sm bg-amber-400 mr-1" />active</span>
          <span><span className="inline-block h-2 w-2 rounded-sm bg-emerald-500 mr-1" />idle</span>
        </div>
        <div className="flex-1 min-h-0">
          {data.length === 0 ? (
            <div className="h-full flex items-center justify-center text-xs text-zinc-600">No samples yet — the monitor records one every few seconds.</div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                <XAxis dataKey="time" tick={{ fontSize: 10, fill: "#71717a" }} minTickGap={40} />
                <YAxis domain={[0, max]} tick={{ fontSize: 10, fill: "#71717a" }} />
                <Tooltip contentStyle={{ background: "#09090b", border: "1px solid #27272a", fontSize: 11 }} />
                <ReferenceLine y={Math.round(max * threshold)} stroke="#ef4444" strokeDasharray="4 4"
                               label={{ value: `alert ${Math.round(threshold * 100)}%`, fill: "#ef4444", fontSize: 10, position: "insideTopRight" }} />
                <Area type="monotone" dataKey="idle_in_transaction" stackId="1" stroke="#ef4444" fill="#ef4444" fillOpacity={0.35} isAnimationActive={false} />
                <Area type="monotone" dataKey="active" stackId="1" stroke="#f59e0b" fill="#f59e0b" fillOpacity={0.3} isAnimationActive={false} />
                <Area type="monotone" dataKey="idle" stackId="1" stroke="#10b981" fill="#10b981" fillOpacity={0.25} isAnimationActive={false} />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
