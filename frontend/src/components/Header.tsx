import React from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Shield, Activity, Sliders, Moon, Sun, CheckCircle2, AlertTriangle, Radio } from "lucide-react"

interface HeaderProps {
  mode: "live" | "cached" | "replay"
  isLiveConnected: boolean
  isMock: boolean
  onOpenControls: () => void
  theme: "dark" | "light"
  onToggleTheme: () => void
}

export const Header: React.FC<HeaderProps> = ({
  mode,
  isLiveConnected,
  isMock,
  onOpenControls,
  theme,
  onToggleTheme,
}) => {
  return (
    <header className="border-b border-zinc-800/80 bg-zinc-950/90 backdrop-blur-md sticky top-0 z-40 px-6 py-3">
      {/* Banner when not in pure live mode */}
      {mode !== "live" && (
        <div className="bg-amber-500/10 border-b border-amber-500/20 -mx-6 -mt-3 mb-3 px-6 py-1.5 flex items-center justify-between text-xs text-amber-400 font-medium">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
            <span>
              Operating in <span className="font-bold uppercase tracking-wider">{mode}</span> mode — deterministic multi-agent offline execution enabled.
            </span>
          </div>
          <span className="text-[11px] text-amber-500/80 hidden sm:inline">Zero external API dependencies required</span>
        </div>
      )}

      <div className="flex items-center justify-between gap-4">
        {/* Brand */}
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-lg bg-gradient-to-br from-emerald-500 to-teal-700 flex items-center justify-center shadow-lg shadow-emerald-500/20 border border-emerald-400/30">
            <Shield className="h-5 w-5 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base font-bold tracking-tight text-zinc-100 font-['Plus_Jakarta_Sans']">
                AutoSRE
              </h1>
              <Badge variant="outline" className="text-[10px] py-0 px-1.5 text-zinc-400 border-zinc-700/80">
                Team Zero-Ops
              </Badge>
            </div>
            <p className="text-[11px] text-zinc-400 hidden sm:block">
              Autonomous Multi-Agent Incident Response & Patch Synthesis
            </p>
          </div>
        </div>

        {/* Status Indicators & Controls */}
        <div className="flex items-center gap-2 sm:gap-3">
          {/* Environment */}
          <Badge variant="secondary" className="hidden md:flex items-center gap-1.5 text-xs bg-zinc-900 border-zinc-800 text-zinc-300">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400"></span>
            us-east-1 · Production
          </Badge>

          {/* Mode Badge */}
          <Badge
            variant={mode === "live" ? "success" : "warning"}
            className="uppercase font-mono text-[11px] tracking-wider"
          >
            {mode} Mode
          </Badge>

          {/* Connection Status */}
          <div className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-md bg-zinc-900 border border-zinc-800">
            <Radio className={`h-3 w-3 ${isLiveConnected ? "text-emerald-400 animate-pulse" : "text-amber-400"}`} />
            <span className="text-zinc-300 hidden sm:inline">
              {isMock ? "Mock Simulator" : isLiveConnected ? "Backend Online" : "Connecting..."}
            </span>
          </div>

          {/* Theme Toggle */}
          <Button
            variant="ghost"
            size="icon"
            onClick={onToggleTheme}
            className="h-8 w-8 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800"
            title="Toggle Theme"
          >
            {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>

          {/* Demo Controls Sheet Button */}
          <Button
            onClick={onOpenControls}
            variant="sre"
            size="sm"
            className="gap-1.5 text-xs font-semibold shadow-md shadow-emerald-900/30"
          >
            <Sliders className="h-3.5 w-3.5" />
            <span>Demo Sheet</span>
          </Button>
        </div>
      </div>
    </header>
  )
}
