import React, { useState, useEffect } from "react"
import { toast, Toaster } from "sonner"
import { Header } from "@/components/Header"
import { Sidebar } from "@/components/Sidebar"
import { PipelineStepper } from "@/components/PipelineStepper"
import { LiveTerminal } from "@/components/LiveTerminal"
import { ConnectionGraph } from "@/components/ConnectionGraph"
import { MttrCard } from "@/components/MttrCard"
import { PatchCard } from "@/components/PatchCard"
import { DetailTabs } from "@/components/DetailTabs"
import { GuardrailsPanel } from "@/components/GuardrailsPanel"
import { PrCard } from "@/components/PrCard"
import { DemoControlSheet } from "@/components/DemoControlSheet"
import {
  useHealth,
  useIncidents,
  useIncident,
  useTelemetryCurrent,
  useTelemetryHistory,
  useConfig,
  useUpdateConfig,
  useTriggerDemo,
  useResetDemo,
  useTimelineStream,
} from "@/hooks/useAutoSRE"
import { apiClient } from "@/lib/api"
import { AgentState } from "@/types/api"

export const Dashboard: React.FC = () => {
  const [selectedIncidentId, setSelectedIncidentId] = useState<string>("INC-8941")
  const [isControlsOpen, setIsControlsOpen] = useState<boolean>(false)
  const [theme, setTheme] = useState<"dark" | "light">("dark")

  // API Queries & Hooks
  const { data: health } = useHealth()
  const { data: incidents = [] } = useIncidents()
  const { data: incidentDetail, isLoading: isIncidentLoading } = useIncident(selectedIncidentId)
  const { data: currentTelemetry } = useTelemetryCurrent()
  const { data: telemetryHistory = [] } = useTelemetryHistory()
  const { data: config } = useConfig()

  // Mutations
  const updateConfigMutation = useUpdateConfig()
  const triggerDemoMutation = useTriggerDemo()
  const resetDemoMutation = useResetDemo()

  // Active Incident Data with fallbacks
  const currentIncident = incidentDetail || (incidents.find((i) => i.id === selectedIncidentId) || incidents[0])

  // Live SSE streaming for timeline
  const timeline = useTimelineStream(selectedIncidentId, currentIncident?.timeline || [])

  // Listen to state changes to toast notifications
  const lastState = timeline.length > 0 ? timeline[timeline.length - 1].state : "ALERT_RECEIVED"
  useEffect(() => {
    if (timeline.length > 0) {
      const latest = timeline[timeline.length - 1]
      if (latest.state === "RESOLVED") {
        toast.success(`Incident ${selectedIncidentId} Resolved!`, {
          description: latest.message,
        })
      } else if (latest.state === "PR_CREATED") {
        toast.info("Pull Request Created", {
          description: latest.message,
        })
      } else if (latest.state === "PATCHING" && currentIncident?.attempt && currentIncident.attempt > 1) {
        toast.warning("Self-Healing Re-Patching", {
          description: "Attempting retry with stack trace feedback.",
        })
      }
    }
  }, [timeline.length])

  // Theme toggle
  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark"
    setTheme(next)
    if (next === "light") {
      document.documentElement.classList.remove("dark")
    } else {
      document.documentElement.classList.add("dark")
    }
  }

  const isLiveConnected = !apiClient.isMockMode() && health?.status === "healthy"
  const isRunning = currentIncident?.status !== "RESOLVED" && currentIncident?.status !== "ESCALATED"

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col font-['Plus_Jakarta_Sans']">
      <Toaster richColors position="bottom-right" />

      {/* Top Header */}
      <Header
        mode={config?.mode || "cached"}
        isLiveConnected={isLiveConnected}
        isMock={apiClient.isMockMode()}
        onOpenControls={() => setIsControlsOpen(true)}
        theme={theme}
        onToggleTheme={toggleTheme}
      />

      <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
        {/* Left Sidebar */}
        <Sidebar
          incidents={incidents.length > 0 ? incidents : [currentIncident || ({} as any)]}
          selectedId={selectedIncidentId}
          onSelectIncident={(id) => setSelectedIncidentId(id)}
          onTriggerNew={() => {
            triggerDemoMutation.mutate()
            toast.info("Incident Triggered", { description: "Traffic simulation initiated. Pool saturation underway." })
          }}
        />

        {/* Main Command Center Canvas */}
        <main className="flex-1 overflow-y-auto p-4 lg:p-6 space-y-6">
          {/* 1. Pipeline Stepper */}
          <PipelineStepper
            currentState={currentIncident?.status || "RESOLVED"}
            attempt={currentIncident?.attempt || 2}
            maxAttempts={currentIncident?.max_attempts || 3}
          />

          {/* 2. Primary Telemetry Row: Live Terminal & Connection Graph */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <LiveTerminal timeline={timeline} />
            <ConnectionGraph
              data={telemetryHistory}
              currentTotal={currentTelemetry?.total || 15}
              maxConnections={currentTelemetry?.max || 100}
            />
          </div>

          {/* 3. Summary Row: MTTR & Suspect Code & PR Gate */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <MttrCard
              mttrSeconds={currentIncident?.mttr_seconds || 38}
              isRunning={isRunning}
            />
            <PatchCard
              suspectCommit={currentIncident?.suspect_commit || ({} as any)}
              leakingCode={currentIncident?.leaking_code || ""}
              confidence={currentIncident?.confidence || 0.94}
              risk={currentIncident?.risk || "High"}
            />
            <PrCard
              prUrl={currentIncident?.pr_url || "https://github.com/zero-ops/victim-service/pull/42"}
              status={currentIncident?.status || "awaiting_human_review"}
            />
          </div>

          {/* 4. Deep Inspection Row: Tabs & Guardrails */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2">
              <DetailTabs
                diff={currentIncident?.unified_diff || ""}
                sandboxOutput={currentIncident?.sandbox_result?.output || ""}
                postmortem={currentIncident?.postmortem || ""}
                timeline={timeline}
              />
            </div>
            <div>
              <GuardrailsPanel checks={currentIncident?.guardrails || []} />
            </div>
          </div>
        </main>
      </div>

      {/* Demo Control Drawer */}
      <DemoControlSheet
        isOpen={isControlsOpen}
        onClose={() => setIsControlsOpen(false)}
        currentMode={config?.mode || "cached"}
        onUpdateMode={(mode) => {
          updateConfigMutation.mutate({ mode })
          toast.success("Execution Mode Updated", { description: `Switched to ${mode} mode.` })
        }}
        maxAttempts={config?.max_attempts || 3}
        onUpdateMaxAttempts={(max) => {
          updateConfigMutation.mutate({ max_attempts: max })
          toast.success("Max Attempts Updated", { description: `Threshold set to ${max}.` })
        }}
        onTriggerDemo={() => {
          triggerDemoMutation.mutate()
          toast.warning("Simulating Connection Leak", {
            description: "Traffic simulator started. Ingesting alert...",
          })
          setIsControlsOpen(false)
        }}
        onResetDemo={() => {
          resetDemoMutation.mutate()
          toast.success("Environment Reset", { description: "Restored connection pool to baseline." })
          setIsControlsOpen(false)
        }}
        isTriggering={triggerDemoMutation.isPending}
        isResetting={resetDemoMutation.isPending}
        isMock={apiClient.isMockMode()}
      />
    </div>
  )
}
