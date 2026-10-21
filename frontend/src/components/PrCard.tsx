import React from "react"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { GitPullRequest, ExternalLink, UserCheck, ShieldAlert, Check } from "lucide-react"

interface PrCardProps {
  prUrl: string | null
  status: string
  branch?: string
}

export const PrCard: React.FC<PrCardProps> = ({
  prUrl = "https://github.com/zero-ops/victim-service/pull/42",
  status = "awaiting_human_review",
  branch = "autosre/fix-connection-leak",
}) => {
  const finalPrUrl = prUrl || "https://github.com/zero-ops/victim-service/pull/42"

  return (
    <Card className="border-zinc-800 bg-gradient-to-br from-zinc-950 via-zinc-950 to-purple-950/20">
      <CardHeader className="py-2.5 px-4 flex flex-row items-center justify-between border-b border-zinc-800/80 bg-zinc-900/50">
        <div className="flex items-center gap-2">
          <GitPullRequest className="h-4 w-4 text-emerald-400" />
          <CardTitle className="text-xs uppercase tracking-wider font-bold text-zinc-200">
            Guarded Delivery: Pull Request
          </CardTitle>
        </div>

        <Badge variant="warning" className="text-[10px] font-mono flex items-center gap-1">
          <UserCheck className="h-3 w-3" />
          Awaiting Human Review
        </Badge>
      </CardHeader>

      <CardContent className="p-4 space-y-3 text-xs">
        <div className="p-3 rounded-lg bg-zinc-900/60 border border-zinc-800 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-zinc-400">Target Head:</span>
            <span className="font-mono text-purple-300 font-semibold">{branch}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-zinc-400">Base Branch:</span>
            <span className="font-mono text-zinc-300">main</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-zinc-400">Auto-Merge Policy:</span>
            <span className="font-mono text-red-400 font-medium">DISABLED (Human Review Only)</span>
          </div>
        </div>

        {/* PR CTA Button */}
        <div className="pt-1">
          <a
            href={finalPrUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="w-full inline-block"
          >
            <Button
              variant="sre"
              className="w-full gap-2 text-xs font-semibold shadow-md shadow-emerald-950/50 py-2.5"
            >
              <GitPullRequest className="h-4 w-4" />
              <span>Review Pull Request #{finalPrUrl.split("/").pop()} on GitHub</span>
              <ExternalLink className="h-3.5 w-3.5 ml-auto" />
            </Button>
          </a>
        </div>

        <p className="text-[11px] text-zinc-500 text-center font-mono">
          Guardrail Guarantee: AutoSRE never auto-merges and never pushes directly to main.
        </p>
      </CardContent>
    </Card>
  )
}
