import React from "react"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { GitCommit, AlertOctagon, Sparkles, FileCode, User } from "lucide-react"
import { SuspectCommit } from "@/types/api"

interface PatchCardProps {
  suspectCommit: SuspectCommit
  leakingCode: string
  confidence: number
  risk: "Low" | "Med" | "High"
}

export const PatchCard: React.FC<PatchCardProps> = ({
  suspectCommit,
  leakingCode,
  confidence = 0.94,
  risk = "High",
}) => {
  return (
    <Card className="border-zinc-800 bg-zinc-950">
      <CardHeader className="py-2.5 px-4 flex flex-row items-center justify-between border-b border-zinc-800/80 bg-zinc-900/50">
        <div className="flex items-center gap-2">
          <GitCommit className="h-4 w-4 text-purple-400" />
          <CardTitle className="text-xs uppercase tracking-wider font-bold text-zinc-200">
            Git Blame & Offending Code Isolation
          </CardTitle>
        </div>

        <div className="flex items-center gap-2">
          {/* Risk Badge */}
          <Badge
            variant={risk === "High" ? "destructive" : risk === "Med" ? "warning" : "success"}
            className="text-[10px] font-mono uppercase"
          >
            Risk: {risk}
          </Badge>

          {/* Confidence */}
          <Badge variant="outline" className="text-[10px] font-mono border-zinc-700 bg-zinc-900 text-zinc-300">
            {Math.round(confidence * 100)}% Confidence
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="p-4 space-y-3">
        {/* Suspect Commit Metadata */}
        <div className="p-3 rounded-lg bg-zinc-900/60 border border-zinc-800/80 space-y-2 text-xs">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-1.5 font-mono">
              <span className="text-zinc-500">Commit:</span>
              <span className="px-1.5 py-0.5 rounded bg-zinc-800 text-purple-300 font-bold">
                {suspectCommit.sha || "728a817"}
              </span>
            </div>
            <div className="flex items-center gap-1.5 text-zinc-400">
              <FileCode className="h-3.5 w-3.5 text-zinc-500" />
              <span className="font-mono text-[11px]">{suspectCommit.file || "analytics/views.py"}</span>
            </div>
          </div>

          <p className="text-zinc-200 font-medium">
            "{suspectCommit.message || "perf(reports): add fast raw-sql user activity report"}"
          </p>

          <div className="flex items-center gap-2 text-[11px] text-zinc-400">
            <User className="h-3 w-3 text-zinc-500" />
            <span>{suspectCommit.author || "Charlie Contributor <charlie@zero-ops.internal>"}</span>
          </div>
        </div>

        {/* Leaking Code Snippet */}
        <div>
          <div className="flex items-center justify-between mb-1 text-[11px] font-mono">
            <span className="text-red-400 flex items-center gap-1">
              <AlertOctagon className="h-3 w-3" />
              Defect: Unclosed Raw DB Cursor
            </span>
            <span className="text-zinc-500">analytics/views.py</span>
          </div>
          <pre className="p-3 rounded-lg bg-zinc-900/90 border border-red-500/20 text-red-200/90 font-mono text-[11px] leading-relaxed overflow-x-auto">
            {leakingCode ||
              `cursor = connection.cursor()\ncursor.execute("SELECT 101 AS user_id, 'login_session' AS event, CURRENT_TIMESTAMP AS ts")\nrows = cursor.fetchall()\n# Missing: cursor.close() or context manager`}
          </pre>
        </div>
      </CardContent>
    </Card>
  )
}
