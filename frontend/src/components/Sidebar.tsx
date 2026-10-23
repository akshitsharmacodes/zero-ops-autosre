import React, { useState } from "react"
import { Activity, ChevronRight } from "lucide-react"
import { clock, STATUS_LABEL, STATUS_TONE, TONE_CLASSES } from "@/lib/format"
import type { IncidentSummary } from "@/types/api"

interface Props {
  incidents: IncidentSummary[]
  selectedId?: string
  onSelect: (id: string) => void
}

const EASE = "duration-500 ease-[cubic-bezier(0.22,1,0.36,1)]"

export const Sidebar: React.FC<Props> = ({ incidents, selectedId, onSelect }) => {
  const [open, setOpen] = useState(false)
  const toggle = () => setOpen((value) => !value)

  return (
    <div className="relative shrink-0 self-start md:sticky md:top-28">
      <aside
        className={`overflow-x-hidden border-r border-zinc-800/80 bg-zinc-950/60 transition-[width] motion-reduce:transition-none ${EASE} ${
          open
            ? "w-full md:w-64 md:max-h-[calc(100dvh-7rem)] md:overflow-y-auto"
            : "w-full overflow-y-hidden md:w-12"
        }`}
      >
        <div className="w-full md:w-64">
          <button
            type="button"
            tabIndex={-1}
            aria-hidden
            onClick={toggle}
            className="flex h-12 w-full items-center gap-2.5 px-4 text-left text-zinc-400 hover:text-zinc-200"
          >
            <Activity className="h-4 w-4 shrink-0 text-emerald-400/90" />
            <span className={`truncate text-xs font-semibold uppercase tracking-wider transition-opacity motion-reduce:transition-none ${EASE} ${open ? "opacity-100" : "opacity-100 md:opacity-0"}`}>
              Incidents
            </span>
            <span className={`text-[10px] font-medium tabular-nums text-zinc-500 transition-opacity motion-reduce:transition-none ${EASE} ${open ? "opacity-100" : "opacity-100 md:opacity-0"}`}>
              {incidents.length}
            </span>
          </button>

          <div className={`grid transition-[grid-template-rows] motion-reduce:transition-none ${EASE} ${open ? "grid-rows-[1fr]" : "grid-rows-[0fr]"}`}>
            <div
              className="overflow-hidden"
              aria-hidden={!open}
              ref={(node) => {
                if (!node) return
                if (open) node.removeAttribute("inert")
                else node.setAttribute("inert", "")
              }}
            >
              <div className={`space-y-2 px-3 pb-3 transition-opacity motion-reduce:transition-none ${EASE} ${open ? "opacity-100" : "pointer-events-none opacity-0"}`}>
                {incidents.length === 0 && <p className="px-1 text-xs text-zinc-600">None yet.</p>}
                {incidents.map((inc) => (
                  <button key={inc.id} onClick={() => onSelect(inc.id)}
                          className={`w-full rounded-lg border p-2.5 text-left transition-colors ${
                            inc.id === selectedId ? "border-emerald-500/40 bg-emerald-500/5" : "border-zinc-800 hover:border-zinc-700"}`}>
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-xs text-zinc-200">{inc.id}</span>
                      <span className="text-[10px] text-zinc-500">{clock(inc.created_at)}</span>
                    </div>
                    <div className="mt-1.5 flex items-center gap-1.5">
                      <span className={`rounded border px-1.5 py-0.5 text-[10px] ${TONE_CLASSES[STATUS_TONE[inc.status]]}`}>{STATUS_LABEL[inc.status]}</span>
                      {inc.mode !== "live" && <span className="text-[10px] uppercase text-zinc-500">{inc.mode}</span>}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      </aside>

      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        aria-label={open ? "Collapse incidents" : "Show incidents"}
        className={`absolute top-3 z-20 flex h-6 w-6 items-center justify-center rounded-full border border-zinc-700 bg-zinc-900 text-zinc-300 shadow-md shadow-black/40 transition-[colors,transform] hover:border-emerald-500/40 hover:text-emerald-300 right-3 md:-right-3`}
      >
        <ChevronRight className={`h-3.5 w-3.5 transition-transform motion-reduce:transition-none ${EASE} ${open ? "rotate-180" : ""}`} />
      </button>

      {!open && (
        <span className="pointer-events-none absolute left-1.5 top-1 hidden h-4 min-w-4 items-center justify-center rounded-full bg-zinc-800 px-1 text-[9px] font-medium tabular-nums text-zinc-300 ring-1 ring-zinc-950 md:flex">
          {incidents.length}
        </span>
      )}
    </div>
  )
}
