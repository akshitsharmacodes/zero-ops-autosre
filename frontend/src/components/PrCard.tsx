import React from "react"
import { toast } from "sonner"
import { ExternalLink, GitMerge, GitPullRequest, Users } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { useMerge, useTeammatePush } from "@/hooks/useAutoSRE"
import type { Incident } from "@/types/api"

export const PrCard: React.FC<{ incident?: Incident }> = ({ incident }) => {
  const merge = useMerge()
  const teammate = useTeammatePush()
  const pr = incident?.pull_request
  const isLocal = pr?.provider === "local"
  const open = pr?.state === "open"

  const state = !pr?.number ? null
    : pr.state === "merged" || incident?.status === "RESOLVED" ? { label: "merged", variant: "success" as const }
    : incident?.status === "READY_TO_MERGE" ? { label: "ready to merge", variant: "info" as const }
    : incident?.status === "UPDATING_PR" ? { label: "repairing", variant: "warning" as const }
    : pr.draft ? { label: "draft", variant: "outline" as const }
    : { label: pr.state || "open", variant: "outline" as const }

  return (
    <Card className="border-zinc-800 bg-zinc-950">
      <CardHeader className="py-2.5 px-4 border-b border-zinc-800/80 bg-zinc-900/50 space-y-0 flex flex-row items-center justify-between">
        <div className="flex items-center gap-2">
          <GitPullRequest className="h-4 w-4 text-emerald-400" />
          <CardTitle className="text-xs uppercase tracking-wider font-bold text-zinc-200">Pull request</CardTitle>
        </div>
        {state && <Badge variant={state.variant} className="text-[10px]">{state.label}</Badge>}
      </CardHeader>
      <CardContent className="p-4 space-y-3">
        {!pr?.number ? (
          <p className="text-xs text-zinc-500">
            {incident?.status === "ESCALATED" ? "No PR: escalated to a human (see post-mortem tab)." : "Opened after the fix passes the sandbox."}
          </p>
        ) : (
          <>
            <div className="text-xs text-zinc-200 font-medium">#{pr.number} {pr.title}</div>
            <div className="text-[11px] font-mono text-zinc-400">{pr.head_branch} → {pr.base_branch}</div>
            {pr.url?.startsWith("http") ? (
              <a href={pr.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-emerald-400 hover:underline">
                Open on GitHub <ExternalLink className="h-3 w-3" />
              </a>
            ) : (
              <div className="text-[11px] text-zinc-500">{pr.url} (local origin)</div>
            )}
            <div className="text-[11px] text-zinc-400">
              Repair rounds: {pr.rounds || 0} · AutoSRE never merges — a human does.
            </div>
            {isLocal && open && (
              <div className="flex flex-wrap gap-2 pt-1">
                <Button size="sm" variant="outline" className="h-7 text-[11px] gap-1" disabled={teammate.isPending}
                        onClick={() => teammate.mutate(undefined, {
                          onSuccess: (r) => toast.info("Teammate pushed to main", { description: `${r.sha.slice(0, 8)} — watch the PR loop repair the conflict.` }),
                          onError: (e) => toast.error((e as Error).message),
                        })}>
                  <Users className="h-3 w-3" /> Simulate teammate push
                </Button>
                {incident?.status === "READY_TO_MERGE" && (
                  <Button size="sm" variant="sre" className="h-7 text-[11px] gap-1" disabled={merge.isPending}
                          onClick={() => merge.mutate(incident.id, {
                            onSuccess: () => toast.success("Merged by you (the human reviewer)"),
                            onError: (e) => toast.error((e as Error).message),
                          })}>
                    <GitMerge className="h-3 w-3" /> Merge (as human reviewer)
                  </Button>
                )}
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}
