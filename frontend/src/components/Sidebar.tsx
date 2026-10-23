import React from "react"
import { Activity } from "lucide-react"
import { clock, STATUS_LABEL, STATUS_TONE, TONE_CLASSES } from "@/lib/format"
import type { IncidentSummary } from "@/types/api"

interface Props {
  incidents: IncidentSummary[]
  selectedId?: string
  onSelect: (id: string) => void
}

export const Sidebar: React.FC<Props> = ({ incidents, selectedId, onSelect }) => (
  <aside className="w-full md:w-64 border-r border-zinc-800/80 bg-zinc-950/60 p-3 space-y-2 md:overflow-y-auto">
    <div className="flex items-center gap-2 px-1 pb-2 text-xs uppercase tracking-wider text-zinc-400 font-semibold">
      <Activity className="h-3.5 w-3.5" /> Incidents
    </div>
    {incidents.length === 0 && <p className="text-xs text-zinc-600 px-1">None yet.</p>}
    {incidents.map((inc) => (
      <button key={inc.id} onClick={() => onSelect(inc.id)}
              className={`w-full text-left rounded-lg border p-2.5 transition-colors ${
                inc.id === selectedId ? "border-emerald-500/40 bg-emerald-500/5" : "border-zinc-800 hover:border-zinc-700"}`}>
        <div className="flex items-center justify-between">
          <span className="font-mono text-xs text-zinc-200">{inc.id}</span>
          <span className="text-[10px] text-zinc-500">{clock(inc.created_at)}</span>
        </div>
        <div className="flex items-center gap-1.5 mt-1.5">
          <span className={`text-[10px] px-1.5 py-0.5 rounded border ${TONE_CLASSES[STATUS_TONE[inc.status]]}`}>{STATUS_LABEL[inc.status]}</span>
          {inc.mode !== "live" && <span className="text-[10px] text-zinc-500 uppercase">{inc.mode}</span>}
        </div>
      </button>
    ))}
  </aside>
)
