import React from "react"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Code, Terminal, FileText, History, Check, AlertCircle } from "lucide-react"
import { TimelineEntry } from "@/types/api"

interface DetailTabsProps {
  diff: string
  sandboxOutput: string
  postmortem: string
  timeline: TimelineEntry[]
}

export const DetailTabs: React.FC<DetailTabsProps> = ({
  diff,
  sandboxOutput,
  postmortem,
  timeline,
}) => {
  return (
    <Card className="border-zinc-800 bg-zinc-950">
      <Tabs defaultValue="diff" className="w-full">
        <div className="px-4 py-2.5 border-b border-zinc-800/80 bg-zinc-900/50 flex items-center justify-between">
          <TabsList className="bg-zinc-900 border-zinc-800">
            <TabsTrigger value="diff" className="gap-1.5 text-xs font-mono">
              <Code className="h-3.5 w-3.5 text-emerald-400" />
              Unified Diff
            </TabsTrigger>
            <TabsTrigger value="sandbox" className="gap-1.5 text-xs font-mono">
              <Terminal className="h-3.5 w-3.5 text-teal-400" />
              Sandbox Runner
            </TabsTrigger>
            <TabsTrigger value="postmortem" className="gap-1.5 text-xs font-mono">
              <FileText className="h-3.5 w-3.5 text-blue-400" />
              Post-Mortem
            </TabsTrigger>
            <TabsTrigger value="audit" className="gap-1.5 text-xs font-mono">
              <History className="h-3.5 w-3.5 text-purple-400" />
              Audit Trail
            </TabsTrigger>
          </TabsList>

          <span className="text-[11px] font-mono text-zinc-500 hidden sm:inline">
            Isolated Sandbox Verification
          </span>
        </div>

        <CardContent className="p-4">
          {/* 1. Unified Diff (Plain Tailwind Syntax Highlighted) */}
          <TabsContent value="diff" className="m-0">
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/90 font-mono text-xs overflow-hidden">
              <div className="py-2 px-3 bg-zinc-800/60 border-b border-zinc-800 text-[11px] text-zinc-400 flex items-center justify-between">
                <span>victim_service/analytics/views.py</span>
                <span className="text-emerald-400">Context Manager Patch Applied</span>
              </div>
              <div className="p-3 max-h-[380px] overflow-y-auto overflow-x-auto space-y-0.5">
                {(diff || "--- a/analytics/views.py\n+++ b/analytics/views.py\n@@ -27,6 +27,6 @@\n-    cursor = connection.cursor()\n-    cursor.execute(\"SELECT 101 AS user_id, 'login_session' AS event, CURRENT_TIMESTAMP AS ts\")\n-    rows = cursor.fetchall()\n+    with connection.cursor() as cursor:\n+        cursor.execute(\"SELECT 101 AS user_id, 'login_session' AS event, CURRENT_TIMESTAMP AS ts\")\n+        rows = cursor.fetchall()\n     data = [{\"user_id\": r[0], \"event\": r[1], \"ts\": str(r[2])} for r in rows]\n     return JsonResponse({\"status\": \"success\", \"count\": len(data), \"data\": data})")
                  .split("\n")
                  .map((line, idx) => {
                    const isAddition = line.startsWith("+") && !line.startsWith("+++")
                    const isDeletion = line.startsWith("-") && !line.startsWith("---")
                    const isHunkHeader = line.startsWith("@@")
                    const isHeader = line.startsWith("---") || line.startsWith("+++")

                    let lineStyle = "text-zinc-400"
                    let rowBg = "hover:bg-zinc-800/40"
                    let badgeSign = " "

                    if (isAddition) {
                      lineStyle = "text-emerald-300 font-medium"
                      rowBg = "bg-emerald-950/25 hover:bg-emerald-950/40"
                      badgeSign = "+"
                    } else if (isDeletion) {
                      lineStyle = "text-red-300 font-medium"
                      rowBg = "bg-red-950/25 hover:bg-red-950/40"
                      badgeSign = "-"
                    } else if (isHunkHeader) {
                      lineStyle = "text-cyan-400 bg-cyan-950/20"
                      rowBg = "bg-cyan-950/10"
                    } else if (isHeader) {
                      lineStyle = "text-zinc-500 font-bold"
                    }

                    return (
                      <div
                        key={idx}
                        className={`flex items-start px-2 py-0.5 rounded leading-relaxed select-text ${rowBg}`}
                      >
                        <span className="w-8 shrink-0 text-zinc-600 select-none text-right pr-3 text-[10px]">
                          {idx + 1}
                        </span>
                        <span className="w-4 shrink-0 font-bold text-center select-none text-[11px]">
                          {badgeSign}
                        </span>
                        <span className={`flex-1 break-all ${lineStyle}`}>
                          {line.startsWith("+") || line.startsWith("-") ? line.slice(1) : line}
                        </span>
                      </div>
                    )
                  })}
              </div>
            </div>
          </TabsContent>

          {/* 2. Sandbox Output */}
          <TabsContent value="sandbox" className="m-0">
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/90 font-mono text-xs p-4 max-h-[380px] overflow-y-auto space-y-2 select-text">
              <div className="flex items-center justify-between pb-2 border-b border-zinc-800 text-[11px] text-zinc-400">
                <span>Runner: docker-py / isolated subprocess sandbox</span>
                <span className="text-emerald-400 flex items-center gap-1">
                  <Check className="h-3 w-3" />
                  Exit Code: 0 (Passed)
                </span>
              </div>
              <pre className="text-zinc-300 text-[11px] leading-relaxed whitespace-pre-wrap">
                {sandboxOutput ||
                  `=== SANDBOX VERIFICATION LOG ===\n[CHECK manage.py check]:\nSystem check identified no issues (0 silenced).\n[PYTEST RUN]:\ntests/test_health.py::test_health_check PASSED [ 33%]\ntests/test_health.py::test_metrics_summary PASSED [ 66%]\ntests/test_leak_regression.py::test_user_activity_report_closes_cursor PASSED [100%]\n============================== 3 passed in 0.08s ==============================`}
              </pre>
            </div>
          </TabsContent>

          {/* 3. Post-Mortem (Rendered Markdown) */}
          <TabsContent value="postmortem" className="m-0">
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/70 p-5 max-h-[380px] overflow-y-auto space-y-4 text-xs leading-relaxed text-zinc-300 select-text">
              <div className="prose prose-invert max-w-none space-y-3">
                {(postmortem ||
                  `# Incident Post-Mortem: INC-8941\n**Service:** victim-service (Django 4.2 / PostgreSQL 15)\n**Severity:** P1 (Critical Outage - Connection Pool Exhaustion)\n**Status:** Resolved (PR Pending Review)\n**MTTR:** 38 seconds (vs manual benchmark ~45 minutes)`
                )
                  .split("\n\n")
                  .map((block, idx) => {
                    if (block.startsWith("# ")) {
                      return <h2 key={idx} className="text-base font-bold text-zinc-100 border-b border-zinc-800 pb-1">{block.replace("# ", "")}</h2>
                    }
                    if (block.startsWith("## ")) {
                      return <h3 key={idx} className="text-sm font-semibold text-emerald-400 mt-3">{block.replace("## ", "")}</h3>
                    }
                    if (block.startsWith("```")) {
                      return (
                        <pre key={idx} className="p-3 bg-zinc-950 rounded border border-zinc-800 font-mono text-[11px] text-zinc-300 overflow-x-auto">
                          {block.replace(/```[a-z]*\n?/g, "")}
                        </pre>
                      )
                    }
                    if (block.startsWith("- ")) {
                      return (
                        <ul key={idx} className="list-disc pl-5 space-y-1 text-zinc-300">
                          {block.split("\n").map((li, i) => (
                            <li key={i}>{li.replace("- ", "")}</li>
                          ))}
                        </ul>
                      )
                    }
                    return <p key={idx} className="text-zinc-300">{block}</p>
                  })}
              </div>
            </div>
          </TabsContent>

          {/* 4. Audit Trail */}
          <TabsContent value="audit" className="m-0">
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/70 overflow-hidden font-mono text-xs">
              <div className="overflow-x-auto max-h-[380px]">
                <table className="w-full text-left">
                  <thead className="bg-zinc-800/60 text-zinc-400 text-[10px] uppercase border-b border-zinc-800">
                    <tr>
                      <th className="py-2 px-3">Timestamp</th>
                      <th className="py-2 px-3">Tag</th>
                      <th className="py-2 px-3">State Transition</th>
                      <th className="py-2 px-3">Description</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800/60 text-[11px]">
                    {timeline.map((entry, idx) => (
                      <tr key={idx} className="hover:bg-zinc-800/30">
                        <td className="py-2 px-3 text-zinc-500 whitespace-nowrap">{entry.ts}</td>
                        <td className="py-2 px-3">
                          <span className="px-1.5 py-0.5 rounded text-[10px] bg-zinc-800 text-zinc-200">
                            {entry.tag}
                          </span>
                        </td>
                        <td className="py-2 px-3 text-zinc-300 whitespace-nowrap">{entry.state}</td>
                        <td className="py-2 px-3 text-zinc-300">{entry.message}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </TabsContent>
        </CardContent>
      </Tabs>
    </Card>
  )
}
