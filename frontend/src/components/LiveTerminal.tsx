import React, { useEffect, useRef, useState } from "react"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Terminal, Copy, Check, ArrowDown, Trash2 } from "lucide-react"
import { TimelineEntry, LogTag } from "@/types/api"

interface LiveTerminalProps {
  timeline: TimelineEntry[]
}

const TAG_STYLES: Record<LogTag, { bg: string; text: string; border: string }> = {
  ALERT: { bg: "bg-red-500/10", text: "text-red-400", border: "border-red-500/30" },
  DIAG: { bg: "bg-cyan-500/10", text: "text-cyan-400", border: "border-cyan-500/30" },
  CORR: { bg: "bg-purple-500/10", text: "text-purple-400", border: "border-purple-500/30" },
  PATCH: { bg: "bg-amber-500/10", text: "text-amber-400", border: "border-amber-500/30" },
  TEST: { bg: "bg-teal-500/10", text: "text-teal-400", border: "border-teal-500/30" },
  PR: { bg: "bg-emerald-500/10", text: "text-emerald-400", border: "border-emerald-500/30" },
}

export const LiveTerminal: React.FC<LiveTerminalProps> = ({ timeline }) => {
  const scrollRef = useRef<HTMLDivElement>(null)
  const [copied, setCopied] = useState(false)
  const [autoScroll, setAutoScroll] = useState(true)

  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [timeline, autoScroll])

  const copyToClipboard = () => {
    const rawText = timeline
      .map((entry) => `[${entry.ts}] [${entry.tag}] (${entry.state}) ${entry.message}`)
      .join("\n")
    navigator.clipboard.writeText(rawText)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <Card className="flex flex-col h-[380px] border-zinc-800 bg-zinc-950 font-mono">
      <CardHeader className="py-2.5 px-4 flex flex-row items-center justify-between border-b border-zinc-800/80 bg-zinc-900/50">
        <div className="flex items-center gap-2">
          <Terminal className="h-4 w-4 text-emerald-400" />
          <CardTitle className="text-xs uppercase tracking-wider font-bold text-zinc-200">
            Live Agent Execution Terminal
          </CardTitle>
          <span className="text-[10px] text-zinc-500">({timeline.length} events)</span>
        </div>

        <div className="flex items-center gap-1.5">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setAutoScroll(!autoScroll)}
            className={`h-7 px-2 text-[11px] gap-1 ${
              autoScroll ? "text-emerald-400 bg-emerald-500/10" : "text-zinc-500"
            }`}
            title="Auto Scroll"
          >
            <ArrowDown className="h-3 w-3" />
            <span>Auto-scroll</span>
          </Button>

          <Button
            variant="ghost"
            size="sm"
            onClick={copyToClipboard}
            className="h-7 px-2 text-[11px] text-zinc-400 hover:text-zinc-100 gap-1"
          >
            {copied ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
            <span>{copied ? "Copied" : "Copy"}</span>
          </Button>
        </div>
      </CardHeader>

      <CardContent
        ref={scrollRef}
        className="p-3 flex-1 overflow-y-auto space-y-1.5 text-xs select-text scrollbar-thin scrollbar-thumb-zinc-800"
      >
        {timeline.length === 0 ? (
          <div className="h-full flex items-center justify-center text-zinc-500 text-xs">
            Waiting for agent events... Trigger an incident from Demo Sheet to start.
          </div>
        ) : (
          timeline.map((entry, index) => {
            const tagStyle = TAG_STYLES[entry.tag] || {
              bg: "bg-zinc-800",
              text: "text-zinc-300",
              border: "border-zinc-700",
            }

            return (
              <div
                key={index}
                className="flex items-start gap-2.5 py-0.5 px-1 rounded hover:bg-zinc-900/50 transition-colors group"
              >
                {/* Timestamp */}
                <span className="text-zinc-500 shrink-0 text-[11px]">
                  {entry.ts}
                </span>

                {/* Colored Tag */}
                <span
                  className={`px-1.5 py-0.2 rounded text-[10px] font-bold border shrink-0 ${tagStyle.bg} ${tagStyle.text} ${tagStyle.border}`}
                >
                  [{entry.tag}]
                </span>

                {/* State Tag */}
                <span className="text-[10px] text-zinc-500 shrink-0 hidden md:inline">
                  ({entry.state})
                </span>

                {/* Message */}
                <span className="text-zinc-200 leading-relaxed break-words flex-1">
                  {entry.message}
                </span>
              </div>
            )
          })
        )}
      </CardContent>
    </Card>
  )
}
