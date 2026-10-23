import React, { useEffect, useRef, useState } from "react"
import { toast, Toaster } from "sonner"
import { Header } from "@/components/Header"
import { Sidebar } from "@/components/Sidebar"
import { PipelineStepper } from "@/components/PipelineStepper"
import { LiveTerminal } from "@/components/LiveTerminal"
import { ConnectionGraph } from "@/components/ConnectionGraph"
import { MttrCard } from "@/components/MttrCard"
import { SuspectCard } from "@/components/SuspectCard"
import { PrCard } from "@/components/PrCard"
import { DetailTabs } from "@/components/DetailTabs"
import { GuardrailsPanel } from "@/components/GuardrailsPanel"
import { DemoControlSheet } from "@/components/DemoControlSheet"
import {
  isActive, useConfig, useGuardrails, useIncident, useIncidents, useSystem, useTelemetry, useTelemetryHistory, useTimeline,
} from "@/hooks/useAutoSRE"
import { STATUS_LABEL } from "@/lib/format"

export const Dashboard: React.FC = () => {
  const [selectedId, setSelectedId] = useState<string>()
  const [controlsOpen, setControlsOpen] = useState(false)
  const pinned = useRef(false)

  const system = useSystem()
  const incidents = useIncidents()
  const incident = useIncident(selectedId).data
  const telemetry = useTelemetry()
  const history = useTelemetryHistory().data || []
  const config = useConfig().data
  const guardrails = useGuardrails(selectedId, isActive(incident?.status)).data?.checks || []
  const timeline = useTimeline(selectedId, incident?.timeline)

  // Follow the newest incident unless the user picked one.
  useEffect(() => {
    const newest = incidents.data?.[0]?.id
    if (newest && (!pinned.current || !selectedId)) setSelectedId(newest)
  }, [incidents.data?.[0]?.id])

  // Toast on important transitions.
  const lastStatus = useRef<string>()
  useEffect(() => {
    if (!incident) return
    if (lastStatus.current && lastStatus.current !== incident.status) {
      const label = STATUS_LABEL[incident.status]
      if (incident.status === "ESCALATED") toast.error(`${incident.id}: escalated to a human`, { description: incident.escalation_reason })
      else if (["PR_CREATED", "READY_TO_MERGE", "RESOLVED", "UPDATING_PR"].includes(incident.status)) toast.info(`${incident.id}: ${label}`)
    }
    lastStatus.current = incident.status
  }, [incident?.status])

  const backendError = system.error ? (system.error as Error).message : undefined

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col">
      <Toaster richColors position="bottom-right" theme="dark" />
      <Header system={system.data} backendError={backendError} incident={incident} onOpenControls={() => setControlsOpen(true)} />
      <div className="flex-1 flex flex-col md:flex-row min-h-0">
        <Sidebar incidents={incidents.data || []} selectedId={selectedId}
                 onSelect={(id) => { pinned.current = true; setSelectedId(id) }} />
        <main className="flex-1 overflow-y-auto p-4 lg:p-6 space-y-6">
          <PipelineStepper incident={incident} />
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
            <LiveTerminal timeline={timeline} />
            <ConnectionGraph history={history} current={telemetry.data}
                             error={telemetry.error ? (telemetry.error as Error).message : undefined}
                             threshold={config?.alert_threshold || 0.9} />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <MttrCard incident={incident} />
            <SuspectCard incident={incident} />
            <PrCard incident={incident} />
          </div>
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
            <div className="xl:col-span-2"><DetailTabs incident={incident} /></div>
            <GuardrailsPanel checks={guardrails} />
          </div>
        </main>
      </div>
      <DemoControlSheet open={controlsOpen} onClose={() => setControlsOpen(false)} system={system.data}
                        onIncidentCreated={(id) => { pinned.current = false; setSelectedId(id) }} />
    </div>
  )
}
