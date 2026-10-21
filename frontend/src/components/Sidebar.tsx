import React from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { AlertCircle, CheckCircle2, RotateCw, Flame, ChevronRight, Activity, Shield } from "lucide-react"
import { Incident, AgentState } from "@/types/api"

interface SidebarProps {
  incidents: Incident[]
  selectedId: string
  onSelectIncident: (id: string) => void
  onTriggerNew: () => void
}

const STATE_BADGE: Record<AgentState, { label: string; variant: "success" | "warning" | "destructive" | "default" | "secondary" }> = {
  ALERT_RECEIVED: { label: "Alert", variant: "destructive" },
  DIAGNOSING: { label: "Diagnosing", variant: "warning" },
  CORRELATING: { label: "Correlating", variant: "warning" },
  PATCHING: { label: "Patching", variant: "warning" },
  TESTING_IN_SANDBOX: { label: "Sandbox", variant: "warning" },
  PR_CREATED: { label: "PR Open", variant: "success" },
  RESOLVED: { label: "Resolved", variant: "success" },
  ESCALATED: { label: "Escalated", variant: "destructive" },
}

export const Sidebar: React.FC<SidebarProps> = ({
  incidents,
  selectedId,
  onSelectIncident,
  onTriggerNew,
}) => {
  return (
    <aside className="w-full md:w-64 lg:w-72 shrink-0 border-r border-zinc-800 bg-zinc-950/80 p-4 flex flex-col justify-between overflow-y-auto">
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-emerald-400" />
            <h2 className="text-xs font-mono font-bold uppercase tracking-wider text-zinc-300">
              Active Incidents
            </h2>
          </div>
          <Badge variant="outline" className="text-[10px] font-mono border-zinc-800">
            {incidents.length}
          </Badge>
        </div>

        {/* Incident List */}
        <div className="space-y-2">
          {incidents.map((inc) => {
            const isSelected = inc.id === selectedId
            const badgeConfig = STATE_BADGE[inc.status] || { label: inc.status, variant: "default" }

            return (
              <button
                key={inc.id}
                onClick={() => onSelectIncident(inc.id)}
                className={`w-full text-left p-3 rounded-lg border transition-all ${
                  isSelected
                    ? "border-emerald-500/50 bg-emerald-950/20 shadow-sm"
                    : "border-zinc-800/80 bg-zinc-900/40 hover:bg-zinc-800/60 hover:border-zinc-700"
                }`}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <span className="font-mono text-xs font-bold text-zinc-200">
                    {inc.id}
                  </span>
                  <Badge variant={badgeConfig.variant} className="text-[10px] font-mono">
                    {badgeConfig.label}
                  </Badge>
                </div>

                <div className="text-[11px] text-zinc-400 truncate mb-1">
                  PostgreSQL Connection Pool Exhaustion (98/100)
                </div>

                <div className="flex items-center justify-between text-[10px] text-zinc-500 font-mono">
                  <span>victim-service</span>
                  <span>Attempt {Math.max(1, inc.attempt)}/3</span>
                </div>
              </button>
            )
          })}
        </div>
      </div>

      {/* Trigger Incident Button */}
      <div className="pt-4 border-t border-zinc-800/80">
        <Button
          onClick={onTriggerNew}
          variant="outline"
          className="w-full gap-2 text-xs border-zinc-800 bg-zinc-900/60 hover:bg-zinc-800 hover:text-zinc-100 text-zinc-300"
        >
          <Flame className="h-3.5 w-3.5 text-red-400" />
          <span>Simulate New Incident</span>
        </Button>
      </div>
    </aside>
  )
}
