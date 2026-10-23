import React, { useState } from "react"
import { GitCommitHorizontal } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { isActive, useDiff } from "@/hooks/useAutoSRE"
import type { Incident } from "@/types/api"

const DiffLines: React.FC<{ diff?: string }> = ({ diff }) => {
  if (!diff) return <p className="text-xs text-zinc-500">The repaired diff appears here after the fix is pushed.</p>
  return (
    <pre className="text-[11px] leading-relaxed font-mono overflow-x-auto max-h-64">
      {diff.split("\n").map((line, i) => (
        <div key={i} className={
          line.startsWith("+++") || line.startsWith("---") ? "text-zinc-500"
            : line.startsWith("+") ? "text-emerald-400 bg-emerald-500/5"
            : line.startsWith("-") ? "text-red-400 bg-red-500/5"
            : line.startsWith("@@") ? "text-sky-400" : "text-zinc-400"}>{line || " "}</div>
      ))}
    </pre>
  )
}

export const ReviewPanel: React.FC<{ incident?: Incident }> = ({ incident }) => {
  const active = isActive(incident?.status)
  const diff = useDiff(incident?.id, active).data?.diff
  const reviews = incident?.pull_request?.reviews || []
  const latest = reviews[reviews.length - 1]
  const [logOpen, setLogOpen] = useState(true)

  if (!incident?.pull_request?.number && reviews.length === 0) return null

  return (
    <Card className="border-zinc-800 bg-zinc-950">
      <CardHeader className="py-2.5 px-4 border-b border-zinc-800/80 bg-zinc-900/50 space-y-0 flex flex-row items-center justify-between">
        <div className="flex items-center gap-2">
          <GitCommitHorizontal className="h-4 w-4 text-emerald-400" />
          <CardTitle className="text-xs uppercase tracking-wider font-bold text-zinc-200">Commit review</CardTitle>
        </div>
        {latest && (
          <Badge variant={latest.conflicts ? "warning" : "success"} className="text-[10px]">
            {latest.conflicts ? "merge conflict" : "clean"}
          </Badge>
        )}
      </CardHeader>
      <CardContent className="p-4 space-y-4">
        {!latest ? (
          <p className="text-xs text-zinc-500">
            Waiting for a new commit on {incident?.pull_request?.base_branch || "main"}. The conflict check, cached suite, and fix will show up here.
          </p>
        ) : (
          <>
            <div className="space-y-1">
              <div className="text-[11px] uppercase tracking-wider text-zinc-500">New commit</div>
              <div className="text-xs text-zinc-200">
                <span className="font-mono text-purple-300">{latest.short_sha}</span> {latest.message}
              </div>
              <div className="text-[11px] text-zinc-400">by {latest.author}</div>
            </div>

            <div className="space-y-1">
              <div className="text-[11px] uppercase tracking-wider text-zinc-500">Merge conflicts</div>
              {latest.conflicts ? (
                <ul className="text-xs text-amber-300 font-mono space-y-0.5">
                  {(latest.conflict_files.length ? latest.conflict_files : ["conflict detected"]).map((file) => (
                    <li key={file}>{file}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-emerald-400">Clean merge. No files conflict.</p>
              )}
            </div>

            <div className="space-y-1">
              <div className="text-[11px] uppercase tracking-wider text-zinc-500">Cached checks</div>
              {!latest.sandbox ? (
                <p className="text-xs text-zinc-500">Running the branch checks…</p>
              ) : (
                <div className="rounded-md border border-zinc-800 p-2 space-y-2">
                  <div className="flex flex-wrap items-center gap-2 text-[11px]">
                    <Badge variant={latest.sandbox.passed ? "success" : "destructive"} className="text-[10px]">
                      {latest.sandbox.passed ? "PASSED" : "FAILED"}
                    </Badge>
                    <span className="text-zinc-400">{latest.sandbox.engine} · {latest.sandbox.duration_seconds}s</span>
                  </div>
                  <ul className="text-[11px] font-mono text-zinc-300 space-y-0.5">
                    {latest.sandbox.commands.filter((command) => !command.includes("test_user_activity")).map((command) => (
                      <li key={command}>$ {command}</li>
                    ))}
                  </ul>
                  <button type="button" className="text-[10px] text-zinc-500" onClick={() => setLogOpen((open) => !open)}>
                    {logOpen ? "Hide log" : "Show log"}
                  </button>
                  {logOpen && (
                    <pre className="text-[10.5px] text-zinc-400 whitespace-pre-wrap max-h-48 overflow-auto bg-zinc-900 p-2 rounded">{latest.sandbox.output}</pre>
                  )}
                </div>
              )}
            </div>

            <div className="space-y-1">
              <div className="text-[11px] uppercase tracking-wider text-zinc-500">Fix</div>
              <p className="text-xs text-zinc-300">
                {latest.repair_summary || "The repair summary appears when the branch is pushed."}
              </p>
              <DiffLines diff={diff} />
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
