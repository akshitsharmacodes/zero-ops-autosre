import React, { useState } from "react"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Switch } from "@/components/ui/switch"
import { Separator } from "@/components/ui/separator"
import {
  Play,
  RotateCcw,
  Sliders,
  Cpu,
  Flame,
  CheckCircle2,
  Info,
  Layers,
} from "lucide-react"

interface DemoControlSheetProps {
  isOpen: boolean
  onClose: () => void
  currentMode: "live" | "cached" | "replay"
  onUpdateMode: (mode: "live" | "cached" | "replay") => void
  maxAttempts: number
  onUpdateMaxAttempts: (max: number) => void
  onTriggerDemo: () => void
  onResetDemo: () => void
  isTriggering: boolean
  isResetting: boolean
  isMock: boolean
}

export const DemoControlSheet: React.FC<DemoControlSheetProps> = ({
  isOpen,
  onClose,
  currentMode,
  onUpdateMode,
  maxAttempts,
  onUpdateMaxAttempts,
  onTriggerDemo,
  onResetDemo,
  isTriggering,
  isResetting,
  isMock,
}) => {
  return (
    <Sheet open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" className="w-full sm:max-w-md bg-zinc-950 border-zinc-800 p-6 flex flex-col justify-between overflow-y-auto">
        <div className="space-y-6">
          <SheetHeader>
            <div className="flex items-center gap-2">
              <Sliders className="h-5 w-5 text-emerald-400" />
              <SheetTitle className="text-base text-zinc-100 font-bold">
                AutoSRE Demo Control Center
              </SheetTitle>
            </div>
            <SheetDescription className="text-xs text-zinc-400">
              Trigger simulated incident traffic, reset baseline metrics, or tune autonomous agent modes.
            </SheetDescription>
          </SheetHeader>

          <Separator className="bg-zinc-800" />

          {/* Quick Action Buttons */}
          <div className="space-y-3">
            <h4 className="text-xs font-mono font-semibold text-zinc-300 uppercase tracking-wider">
              Simulation Actions
            </h4>

            {/* Trigger Incident Button */}
            <Button
              variant="destructive"
              className="w-full justify-start gap-2.5 py-5 text-xs font-semibold shadow-lg shadow-red-950/40"
              onClick={onTriggerDemo}
              disabled={isTriggering}
            >
              <Flame className="h-4 w-4 text-red-300 animate-pulse" />
              <div className="text-left">
                <div>Trigger Incident (Saturate Connections)</div>
                <div className="text-[10px] text-red-200/80 font-normal">
                  Ramps PostgreSQL to 98/100 conns & activates agent
                </div>
              </div>
            </Button>

            {/* Reset Button */}
            <Button
              variant="outline"
              className="w-full justify-start gap-2.5 py-5 text-xs border-zinc-800 bg-zinc-900/60 hover:bg-zinc-800 text-zinc-200"
              onClick={onResetDemo}
              disabled={isResetting}
            >
              <RotateCcw className="h-4 w-4 text-zinc-400" />
              <div className="text-left">
                <div>Reset Environment</div>
                <div className="text-[10px] text-zinc-400 font-normal">
                  Restores clean PostgreSQL connection baseline
                </div>
              </div>
            </Button>
          </div>

          <Separator className="bg-zinc-800" />

          {/* Agent Mode Selection */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-mono font-semibold text-zinc-300 uppercase tracking-wider">
                Execution Mode
              </h4>
              <Badge variant="outline" className="text-[10px] uppercase font-mono border-zinc-700">
                {currentMode}
              </Badge>
            </div>

            <div className="grid grid-cols-3 gap-2">
              {(["cached", "live", "replay"] as const).map((modeOption) => (
                <button
                  key={modeOption}
                  onClick={() => onUpdateMode(modeOption)}
                  className={`p-2.5 rounded-lg border text-xs font-mono capitalize transition-all ${
                    currentMode === modeOption
                      ? "border-emerald-500 bg-emerald-950/20 text-emerald-300 font-bold shadow-sm"
                      : "border-zinc-800 bg-zinc-900/40 text-zinc-400 hover:border-zinc-700"
                  }`}
                >
                  {modeOption}
                </button>
              ))}
            </div>

            <div className="p-2.5 rounded-lg bg-zinc-900/40 border border-zinc-800 text-[11px] text-zinc-400 flex items-start gap-2">
              <Info className="h-3.5 w-3.5 text-zinc-500 shrink-0 mt-0.5" />
              <span>
                {currentMode === "cached"
                  ? "Cached mode runs self-healing multi-agent loop with zero API keys (attempt 1 fails sandbox, attempt 2 passes)."
                  : currentMode === "live"
                  ? "Live mode dispatches prompts directly to Gemini 1.5 Flash / Vertex AI."
                  : "Replay mode replays recorded incident timeline for testing."}
              </span>
            </div>
          </div>

          <Separator className="bg-zinc-800" />

          {/* Max Attempts Tuning */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-mono font-semibold text-zinc-300 uppercase tracking-wider">
                Max Patch Attempts
              </h4>
              <span className="text-xs font-mono font-bold text-emerald-400">
                {maxAttempts} attempts
              </span>
            </div>

            <div className="flex items-center gap-2">
              {[1, 2, 3, 4, 5].map((num) => (
                <button
                  key={num}
                  onClick={() => onUpdateMaxAttempts(num)}
                  className={`flex-1 py-1.5 rounded border text-xs font-mono ${
                    maxAttempts === num
                      ? "border-emerald-500 bg-emerald-950/30 text-emerald-300 font-bold"
                      : "border-zinc-800 bg-zinc-900 text-zinc-400"
                  }`}
                >
                  {num}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Footer info */}
        <div className="pt-6 border-t border-zinc-800 text-[11px] text-zinc-500 font-mono text-center">
          AutoSRE v1.0.0 · Team Zero-Ops · Hackathon
        </div>
      </SheetContent>
    </Sheet>
  )
}
