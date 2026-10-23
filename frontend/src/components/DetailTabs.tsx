import React, { useState } from "react"
import { Download } from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Markdown } from "@/components/Markdown"
import { isActive, useDiff, usePostmortem, useSandboxRuns, useSteps } from "@/hooks/useAutoSRE"
import { api } from "@/lib/api"
import { clock } from "@/lib/format"
import type { Incident } from "@/types/api"

const TASK_LABEL = { fix: "fix", resolve_conflict: "conflict", fix_ci: "CI" }

const DiffView: React.FC<{ diff?: string; empty: string }> = ({ diff, empty }) =>
  !diff ? <p className="text-xs text-zinc-500">{empty}</p> : (
    <pre className="text-[11px] leading-relaxed font-mono overflow-x-auto">
      {diff.split("\n").map((l, i) => (
        <div key={i} className={
          l.startsWith("+++") || l.startsWith("---") ? "text-zinc-500"
            : l.startsWith("+") ? "text-emerald-400 bg-emerald-500/5"
            : l.startsWith("-") ? "text-red-400 bg-red-500/5"
            : l.startsWith("@@") ? "text-sky-400" : "text-zinc-400"}>{l || " "}</div>
      ))}
    </pre>
  )

export const DetailTabs: React.FC<{ incident?: Incident }> = ({ incident }) => {
  const id = incident?.id
  const active = isActive(incident?.status)
  const steps = useSteps(id, active).data || []
  const runs = useSandboxRuns(id, active).data || []
  const diff = useDiff(id, active).data
  const pm = usePostmortem(id, active).data?.markdown
  const [openRun, setOpenRun] = useState<number | null>(null)

  if (!incident) return null
  const d = incident.diagnosis

  return (
    <Card className="border-zinc-800 bg-zinc-950">
      <Tabs defaultValue="agent">
        <div className="flex items-center justify-between border-b border-zinc-800 px-2">
          <TabsList className="bg-transparent">
            <TabsTrigger value="agent">Agent steps ({steps.length})</TabsTrigger>
            <TabsTrigger value="diff">Diff</TabsTrigger>
            <TabsTrigger value="sandbox">Sandbox ({runs.length})</TabsTrigger>
            <TabsTrigger value="diagnosis">Diagnosis</TabsTrigger>
            <TabsTrigger value="postmortem">Post-mortem</TabsTrigger>
          </TabsList>
          <a href={api.auditUrl(incident.id)} className="text-[11px] text-zinc-400 hover:text-emerald-400 inline-flex items-center gap-1 pr-2">
            <Download className="h-3 w-3" /> Audit JSON
          </a>
        </div>
        <CardContent className="p-4 max-h-[520px] overflow-y-auto">
          <TabsContent value="agent" className="mt-0 space-y-2">
            {steps.length === 0 && <p className="text-xs text-zinc-500">The coding agent's tool calls appear here.</p>}
            {steps.map((s) => (
              <div key={s.id} className={`rounded-md border p-2 ${s.ok ? "border-zinc-800" : "border-red-500/30 bg-red-500/5"}`}>
                <div className="flex items-center gap-2 text-[11px]">
                  <span className="text-zinc-600 font-mono">{clock(s.ts)}</span>
                  <Badge variant="outline" className="text-[10px]">{TASK_LABEL[s.task]} · try {s.attempt}</Badge>
                  <span className="font-mono text-amber-300">{s.tool}</span>
                  <span className="text-zinc-500 font-mono truncate">{String(s.args.path ?? s.args.text ?? "")}</span>
                </div>
                {s.thought && <div className="text-[11px] text-zinc-300 mt-1 italic">“{s.thought}”</div>}
                <details className="mt-1">
                  <summary className="text-[10px] text-zinc-500 cursor-pointer">result</summary>
                  <pre className="text-[10.5px] text-zinc-400 whitespace-pre-wrap mt-1 max-h-48 overflow-auto">{s.result}</pre>
                </details>
              </div>
            ))}
          </TabsContent>

          <TabsContent value="diff" className="mt-0 space-y-4">
            <div>
              <div className="text-[11px] text-zinc-400 mb-1">AutoSRE fix (vs. latest main)</div>
              <DiffView diff={diff?.diff} empty="No verified fix yet." />
            </div>
            <details>
              <summary className="text-[11px] text-zinc-400 cursor-pointer">Suspect commit diff</summary>
              <DiffView diff={diff?.suspect_commit_diff} empty="No suspect commit yet." />
            </details>
          </TabsContent>

          <TabsContent value="sandbox" className="mt-0 space-y-2">
            {runs.length === 0 && <p className="text-xs text-zinc-500">No sandbox runs yet.</p>}
            {runs.map((r) => (
              <div key={r.id} className="rounded-md border border-zinc-800 p-2">
                <div className="flex flex-wrap items-center gap-2 text-[11px] cursor-pointer" onClick={() => setOpenRun(openRun === r.id ? null : r.id)}>
                  <span className="text-zinc-600 font-mono">{clock(r.ts)}</span>
                  <Badge variant={r.passed ? "success" : "destructive"} className="text-[10px]">{r.passed ? "PASSED" : r.timed_out ? "TIMEOUT" : "FAILED"}</Badge>
                  <span className="text-zinc-300">{TASK_LABEL[r.task as keyof typeof TASK_LABEL] || r.task} · attempt {r.attempt}</span>
                  <Badge variant={r.isolated ? "outline" : "warning"} className="text-[10px]">{r.engine}{r.isolated ? "" : " · NOT isolated"}</Badge>
                  {r.reproduced !== null && (
                    <span className={r.reproduced ? "text-emerald-400" : "text-red-400"}>
                      regression test {r.reproduced ? "fails on old code ✓" : "does NOT fail on old code ✗"}
                    </span>
                  )}
                  <span className="text-zinc-500">{r.duration_seconds}s</span>
                </div>
                {openRun === r.id && (
                  <pre className="mt-2 text-[10.5px] text-zinc-400 whitespace-pre-wrap max-h-80 overflow-auto bg-zinc-900 p-2 rounded">{r.output}</pre>
                )}
              </div>
            ))}
          </TabsContent>

          <TabsContent value="diagnosis" className="mt-0 space-y-3 text-xs">
            {!d?.findings ? <p className="text-zinc-500">Diagnosis pending.</p> : (
              <>
                <p className="text-zinc-200">{d.hypothesis}</p>
                <ul className="space-y-1">{d.findings.map((f) => <li key={f} className="text-zinc-400">• {f}</li>)}</ul>
                {d.delta && <p className="text-zinc-400">Change vs healthy baseline: {Object.entries(d.delta).map(([k, v]) => `${k} ${v >= 0 ? "+" : ""}${v}`).join(", ")}</p>}
                {(d.stuck_sessions?.groups || []).map((g) => (
                  <div key={g.query} className="rounded border border-zinc-800 p-2">
                    <div className="text-zinc-300">{g.count} × <span className="font-mono">{g.application_name}</span>, up to {Math.round(g.max_idle_seconds)}s stuck</div>
                    <pre className="text-[10.5px] text-zinc-400 whitespace-pre-wrap mt-1">{g.example_query}</pre>
                  </div>
                ))}
                {incident.mitigation?.terminated !== undefined && (
                  <p className="text-orange-300">Stop-the-bleeding ended {incident.mitigation.terminated} stuck session(s).</p>
                )}
              </>
            )}
          </TabsContent>

          <TabsContent value="postmortem" className="mt-0">
            {pm ? <Markdown source={pm} /> : <p className="text-xs text-zinc-500">Written when the PR is opened (or on escalation).</p>}
          </TabsContent>
        </CardContent>
      </Tabs>
    </Card>
  )
}
