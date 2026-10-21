import React from "react"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Database, AlertTriangle } from "lucide-react"
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts"
import { ConnectionHistoryPoint } from "@/types/api"

interface ConnectionGraphProps {
  data: ConnectionHistoryPoint[]
  currentTotal: number
  maxConnections: number
}

export const ConnectionGraph: React.FC<ConnectionGraphProps> = ({
  data,
  currentTotal,
  maxConnections = 100,
}) => {
  const isSaturated = currentTotal >= 90

  return (
    <Card className="flex flex-col h-[380px] border-zinc-800 bg-zinc-950">
      <CardHeader className="py-2.5 px-4 flex flex-row items-center justify-between border-b border-zinc-800/80 bg-zinc-900/50">
        <div className="flex items-center gap-2">
          <Database className="h-4 w-4 text-emerald-400" />
          <CardTitle className="text-xs uppercase tracking-wider font-bold text-zinc-200">
            PostgreSQL Connection Pool Telemetry
          </CardTitle>
        </div>

        <div className="flex items-center gap-2">
          {isSaturated && (
            <Badge variant="destructive" className="text-[10px] animate-pulse flex items-center gap-1">
              <AlertTriangle className="h-3 w-3" />
              Exhaustion Critical ({currentTotal}/100)
            </Badge>
          )}
          <Badge variant="outline" className="text-[11px] font-mono border-zinc-700 bg-zinc-900 text-zinc-200">
            Current: {currentTotal} / {maxConnections} conns
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="p-4 flex-1 flex flex-col justify-between">
        {/* Legend */}
        <div className="flex items-center gap-4 text-xs font-mono mb-2">
          <div className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-red-500"></span>
            <span className="text-zinc-400">Idle in Transaction (Leak)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-amber-500"></span>
            <span className="text-zinc-400">Active</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-emerald-500"></span>
            <span className="text-zinc-400">Idle</span>
          </div>
          <div className="flex items-center gap-1.5 ml-auto text-zinc-500">
            <span className="h-0.5 w-3 bg-red-400 border-dashed inline-block"></span>
            <span>Limit (100)</span>
          </div>
        </div>

        {/* Chart */}
        <div className="w-full h-[260px]">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="colorIdleInTx" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#ef4444" stopOpacity={0.6} />
                  <stop offset="95%" stopColor="#ef4444" stopOpacity={0.0} />
                </linearGradient>
                <linearGradient id="colorActive" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.5} />
                  <stop offset="95%" stopColor="#f59e0b" stopOpacity={0.0} />
                </linearGradient>
                <linearGradient id="colorIdle" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10b981" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0.0} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="timestamp"
                stroke="#52525b"
                fontSize={10}
                tickLine={false}
              />
              <YAxis
                domain={[0, 110]}
                stroke="#52525b"
                fontSize={10}
                tickLine={false}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#09090b",
                  borderColor: "#27272a",
                  borderRadius: "8px",
                  fontSize: "11px",
                  fontFamily: "monospace",
                }}
              />
              <ReferenceLine
                y={100}
                stroke="#ef4444"
                strokeDasharray="3 3"
                label={{
                  value: "MAX: 100",
                  fill: "#ef4444",
                  fontSize: 10,
                  position: "insideTopRight",
                }}
              />
              <Area
                type="monotone"
                dataKey="idle_in_transaction"
                stackId="1"
                stroke="#ef4444"
                fill="url(#colorIdleInTx)"
                name="Idle in Tx (Leak)"
              />
              <Area
                type="monotone"
                dataKey="active"
                stackId="1"
                stroke="#f59e0b"
                fill="url(#colorActive)"
                name="Active"
              />
              <Area
                type="monotone"
                dataKey="idle"
                stackId="1"
                stroke="#10b981"
                fill="url(#colorIdle)"
                name="Idle"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  )
}
