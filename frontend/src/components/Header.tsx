import React from "react"
import { AlertTriangle, Bot, Box, Database, GitPullRequest, Shield, Sliders } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import type { Incident, SystemStatus } from "@/types/api"

interface HeaderProps {
  system?: SystemStatus
  backendError?: string
  incident?: Incident
  onOpenControls: () => void
}

const Chip: React.FC<{ ok: boolean | null; icon: React.ElementType; label: string; title?: string }> = ({ ok, icon: Icon, label, title }) => (
  <div
    title={title}
    className={`hidden md:flex items-center gap-1.5 text-[11px] px-2 py-1 rounded-md border ${
      ok === null ? "border-zinc-800 text-zinc-400" : ok ? "border-emerald-500/30 text-emerald-300 bg-emerald-500/5" : "border-amber-500/30 text-amber-300 bg-amber-500/5"
    }`}
  >
    <Icon className="h-3 w-3" />
    {label}
  </div>
)

export const Header: React.FC<HeaderProps> = ({ system, backendError, incident, onOpenControls }) => {
  // FR-9.3: always say when the run is not fully live or not fully isolated.
  const cachedChecks = system?.sandbox.engine === "cached"
  const banners: string[] = []
  if (backendError) banners.push(backendError)
  if (incident?.mode === "replay") banners.push(`REPLAY: ${incident.id} is a playback of a recorded run — nothing is being executed.`)
  else if (incident?.llm?.fallback_used) banners.push(`LLM unreachable (${incident.llm.fallback_reason}) — this incident used CACHED recorded decisions.`)
  else if (system?.mode === "cached" && !cachedChecks) banners.push("CACHED mode: the agent replays recorded decisions; files, guardrails and sandbox still run for real.")
  if (system && !cachedChecks && !system.sandbox.isolated) banners.push("Docker is not running — sandbox runs are NOT ISOLATED (subprocess fallback).")

  return (
    <header className="border-b border-zinc-800/80 bg-zinc-950/90 backdrop-blur-md sticky top-0 z-40">
      {banners.map((b) => (
        <div key={b} className="bg-amber-500/10 border-b border-amber-500/20 px-6 py-1.5 flex items-center gap-2 text-xs text-amber-300">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
          <span>{b}</span>
        </div>
      ))}
      <div className="px-6 py-3 flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-lg bg-gradient-to-br from-emerald-500 to-teal-700 flex items-center justify-center shadow-lg shadow-emerald-500/20">
            <Shield className="h-5 w-5 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base font-bold tracking-tight text-zinc-100">AutoSRE</h1>
              <Badge variant="outline" className="text-[10px] py-0 px-1.5 text-zinc-400">Team Zero-Ops</Badge>
            </div>
            <p className="text-[11px] text-zinc-400 hidden sm:block">Detect · mitigate · fix · verify · deliver — humans merge</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {system && (
            <>
              <Chip ok={system.database.reachable} icon={Database}
                    label={system.database.reachable ? "DB connected" : "DB unreachable"} title={system.database.error || system.database.host} />
              <Chip ok={cachedChecks ? true : system.sandbox.isolated} icon={Box}
                    label={cachedChecks ? "Cached checks" : system.sandbox.isolated ? "Docker sandbox" : "Sandbox NOT isolated"} />
              <Chip ok={system.mode !== "live" || system.llm.configured} icon={Bot}
                    label={system.mode === "live" ? `${system.llm.provider}${system.llm.configured ? "" : " (no key)"}` : "Cached brain"}
                    title={system.llm.model} />
              <Chip ok={system.delivery.configured} icon={GitPullRequest}
                    label={system.delivery.provider === "github" ? "GitHub" : "Local origin"} title={system.delivery.target} />
              <Badge variant={system.mode === "live" ? "success" : "warning"} className="uppercase font-mono text-[11px] tracking-wider">
                {system.mode}
              </Badge>
            </>
          )}
          <Button onClick={onOpenControls} variant="sre" size="sm" className="gap-1.5 text-xs">
            <Sliders className="h-3.5 w-3.5" />
            Controls
          </Button>
        </div>
      </div>
    </header>
  )
}
