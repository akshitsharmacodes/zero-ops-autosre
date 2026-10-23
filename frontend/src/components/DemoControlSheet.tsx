import React, { useState } from "react"
import { toast } from "sonner"
import { Film, Github, Play, RotateCcw, Settings2 } from "lucide-react"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import {
  useConfig, useGitHubDisconnect, useGitHubStatus, useReplay, useReset, useTraffic, useTriggerDemo, useUpdateConfig,
} from "@/hooks/useAutoSRE"
import { api } from "@/lib/api"
import type { RunMode, SystemStatus } from "@/types/api"

interface Props {
  open: boolean
  onClose: () => void
  system?: SystemStatus
  onIncidentCreated: (id: string) => void
}

const err = (e: unknown) => toast.error((e as Error).message)

export const DemoControlSheet: React.FC<Props> = ({ open, onClose, system, onIncidentCreated }) => {
  const config = useConfig().data
  const traffic = useTraffic().data
  const update = useUpdateConfig()
  const trigger = useTriggerDemo()
  const replay = useReplay()
  const reset = useReset()
  const github = useGitHubStatus().data
  const disconnect = useGitHubDisconnect()
  const [clear, setClear] = useState(true)
  const [reseed, setReseed] = useState(false)

  const set = (patch: Parameters<typeof update.mutate>[0]) =>
    update.mutate(patch, { onSuccess: () => toast.success("Settings saved"), onError: err })

  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()}>
      <SheetContent side="right" className="w-full sm:max-w-md bg-zinc-950 border-zinc-800 p-6 overflow-y-auto space-y-5">
        <SheetHeader>
          <SheetTitle className="text-zinc-100">Controls</SheetTitle>
          <SheetDescription className="text-zinc-400 text-xs">
            These simulate the outside world (users, a teammate, a reviewer). They never let AutoSRE skip a safety rule.
          </SheetDescription>
        </SheetHeader>

        <section className="space-y-2">
          <h3 className="text-xs font-semibold text-zinc-300 uppercase tracking-wider">1 · Start an incident</h3>
          <p className="text-[11px] text-zinc-500">
            Sends real HTTP traffic to the victim service ({system?.victim.base_url}). Its leaky report exhausts PostgreSQL;
            the monitor raises the alert on its own.
          </p>
          <Button variant="sre" className="w-full gap-2" disabled={trigger.isPending || traffic?.running}
                  onClick={() => trigger.mutate(undefined, { onSuccess: (r) => toast.info(r.message), onError: err })}>
            <Play className="h-4 w-4" /> {traffic?.running ? `Traffic running… ${traffic.sent}/${traffic.target}` : "Start incident (send traffic)"}
          </Button>
          {traffic && traffic.sent > 0 && (
            <p className="text-[11px] text-zinc-500 font-mono">sent {traffic.sent} · ok {traffic.ok} · errors {traffic.errors}</p>
          )}
          <Button variant="outline" className="w-full gap-2" disabled={replay.isPending}
                  onClick={() => replay.mutate(undefined, {
                    onSuccess: (r) => { onIncidentCreated(r.incident.id); toast.info("Replaying a recorded run"); onClose() },
                    onError: err,
                  })}>
            <Film className="h-4 w-4" /> Replay recorded run (offline backup)
          </Button>
        </section>

        <Separator className="bg-zinc-800" />

        <section className="space-y-3">
          <h3 className="text-xs font-semibold text-zinc-300 uppercase tracking-wider flex items-center gap-1.5"><Settings2 className="h-3.5 w-3.5" /> 2 · Agent settings</h3>
          <label className="block text-[11px] text-zinc-400">Mode (applies to new incidents)
            <select className="mt-1 w-full bg-zinc-900 border border-zinc-800 rounded px-2 py-1.5 text-xs text-zinc-200"
                    value={config?.mode} onChange={(e) => set({ mode: e.target.value as RunMode })}>
              <option value="cached">cached — recorded decisions, real tools</option>
              <option value="live">live — real LLM</option>
            </select>
          </label>
          <label className="block text-[11px] text-zinc-400">Human oversight (applies to new incidents)
            <select className="mt-1 w-full bg-zinc-900 border border-zinc-800 rounded px-2 py-1.5 text-xs text-zinc-200"
                    value={config?.approval_mode} onChange={(e) => set({ approval_mode: e.target.value as "autonomous" | "review" })}>
              <option value="autonomous">autonomous - act, then report (every decision recorded)</option>
              <option value="review">review - ask a human before ending sessions and before changing code</option>
            </select>
          </label>
          <label className="block text-[11px] text-zinc-400">LLM provider (live mode)
            <select className="mt-1 w-full bg-zinc-900 border border-zinc-800 rounded px-2 py-1.5 text-xs text-zinc-200"
                    value={config?.llm_provider} onChange={(e) => set({ llm_provider: e.target.value })}>
              <option value="groq">Groq</option>
              <option value="nvidia">NVIDIA (Nemotron)</option>
            </select>
          </label>
          <label className="block text-[11px] text-zinc-400">Max fix attempts: {config?.max_attempts}
            <input type="range" min={1} max={5} value={config?.max_attempts || 3} className="w-full"
                   onChange={(e) => set({ max_attempts: Number(e.target.value) })} />
          </label>
          <label className="block text-[11px] text-zinc-400">Alert threshold: {Math.round((config?.alert_threshold || 0.9) * 100)}%
            <input type="range" min={50} max={100} value={Math.round((config?.alert_threshold || 0.9) * 100)} className="w-full"
                   onChange={(e) => set({ alert_threshold: Number(e.target.value) / 100 })} />
          </label>
        </section>

        <Separator className="bg-zinc-800" />

        <section className="space-y-2">
          <h3 className="text-xs font-semibold text-zinc-300 uppercase tracking-wider flex items-center gap-1.5"><Github className="h-3.5 w-3.5" /> 3 · GitHub</h3>
          {!github || github.provider === "local" ? (
            <p className="text-[11px] text-zinc-500">Using the local "pretend GitHub" (DELIVERY_PROVIDER=local). See docs/GITHUB_APP_SETUP.md to use real PRs.</p>
          ) : github.connected ? (
            <div className="text-[11px] text-zinc-400 space-y-1">
              <p className="text-emerald-300">Connected to {github.repo}{github.app ? ` as ${github.app.bot_login}` : " (personal token)"}</p>
              {github.token_expires_in_seconds !== null && <p>Current token renews automatically (expires in {Math.round(github.token_expires_in_seconds / 60)} min).</p>}
              {github.auth_mode === "app" && (
                <Button size="sm" variant="outline" className="h-7 text-[11px]" disabled={disconnect.isPending}
                        onClick={() => disconnect.mutate(undefined, { onSuccess: (r) => toast.info(r.note), onError: err })}>
                  Disconnect
                </Button>
              )}
            </div>
          ) : (
            <div className="space-y-2">
              {github.error && <p className="text-[11px] text-amber-300">{github.error}</p>}
              {github.auth_mode === "app" && (
                <a href={api.githubConnectUrl} className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-zinc-100 text-zinc-900 text-sm font-semibold h-9 hover:bg-white">
                  <Github className="h-4 w-4" /> Connect GitHub
                </a>
              )}
            </div>
          )}
        </section>

        <Separator className="bg-zinc-800" />

        <section className="space-y-2">
          <h3 className="text-xs font-semibold text-zinc-300 uppercase tracking-wider">4 · Reset</h3>
          <label className="flex items-center gap-2 text-[11px] text-zinc-400">
            <input type="checkbox" checked={clear} onChange={(e) => setClear(e.target.checked)} /> Clear incident history
          </label>
          <label className="flex items-center gap-2 text-[11px] text-zinc-400">
            <input type="checkbox" checked={reseed} onChange={(e) => setReseed(e.target.checked)} /> Re-seed the victim git repo (undo merged fixes)
          </label>
          <Button variant="outline" className="w-full gap-2" disabled={reset.isPending}
                  onClick={() => reset.mutate({ clear_incidents: clear, reseed_repo: reseed }, {
                    onSuccess: () => { toast.success("Environment reset"); onClose() }, onError: err,
                  })}>
            <RotateCcw className="h-4 w-4" /> Stop traffic & reset
          </Button>
        </section>
      </SheetContent>
    </Sheet>
  )
}
