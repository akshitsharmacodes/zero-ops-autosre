import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { apiClient } from "../lib/api"
import { TimelineEntry, Incident } from "../types/api"

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: async () => {
      const res = await apiClient.getHealth()
      return res.data
    },
    refetchInterval: 10000,
  })
}

export function useIncidents() {
  return useQuery({
    queryKey: ["incidents"],
    queryFn: async () => {
      const res = await apiClient.getIncidents()
      return res.data || []
    },
    refetchInterval: 3000,
  })
}

export function useIncident(id: string) {
  return useQuery({
    queryKey: ["incident", id],
    queryFn: async () => {
      const res = await apiClient.getIncident(id)
      return res.data
    },
    enabled: !!id,
    refetchInterval: 2000,
  })
}

export function useDiff(id: string) {
  return useQuery({
    queryKey: ["incident-diff", id],
    queryFn: async () => {
      const res = await apiClient.getDiff(id)
      return res.data?.diff || ""
    },
    enabled: !!id,
  })
}

export function usePostmortem(id: string) {
  return useQuery({
    queryKey: ["incident-postmortem", id],
    queryFn: async () => {
      const res = await apiClient.getPostmortem(id)
      return res.data?.markdown || ""
    },
    enabled: !!id,
  })
}

export function useTelemetryCurrent() {
  return useQuery({
    queryKey: ["telemetry-current"],
    queryFn: async () => {
      const res = await apiClient.getTelemetryCurrent()
      return res.data || { active: 3, idle: 8, idle_in_transaction: 0, max: 100 }
    },
    refetchInterval: 2000,
  })
}

export function useTelemetryHistory() {
  return useQuery({
    queryKey: ["telemetry-history"],
    queryFn: async () => {
      const res = await apiClient.getTelemetryHistory()
      return res.data || []
    },
    refetchInterval: 2000,
  })
}

export function useGuardrails(incidentId?: string) {
  return useQuery({
    queryKey: ["guardrails", incidentId],
    queryFn: async () => {
      const res = await apiClient.getGuardrails(incidentId)
      return res.data?.checks || []
    },
    refetchInterval: 3000,
  })
}

export function useConfig() {
  return useQuery({
    queryKey: ["config"],
    queryFn: async () => {
      const res = await apiClient.getConfig()
      return res.data || { mode: "cached", max_attempts: 3 }
    },
  })
}

export function useUpdateConfig() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: apiClient.updateConfig,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["config"] })
    },
  })
}

export function useTriggerDemo() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: apiClient.triggerDemo,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["incidents"] })
      queryClient.invalidateQueries({ queryKey: ["telemetry-history"] })
      queryClient.invalidateQueries({ queryKey: ["telemetry-current"] })
    },
  })
}

export function useResetDemo() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: apiClient.resetDemo,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["incidents"] })
      queryClient.invalidateQueries({ queryKey: ["telemetry-history"] })
      queryClient.invalidateQueries({ queryKey: ["telemetry-current"] })
    },
  })
}

export function useTimelineStream(incidentId: string, initialTimeline: TimelineEntry[] = []) {
  const [timeline, setTimeline] = useState<TimelineEntry[]>(initialTimeline)

  useEffect(() => {
    if (initialTimeline && initialTimeline.length > 0) {
      setTimeline(initialTimeline)
    }
  }, [initialTimeline.length])

  useEffect(() => {
    if (!incidentId) return

    const unsubscribe = apiClient.subscribeTimeline(
      incidentId,
      (event) => {
        setTimeline((prev) => {
          // Avoid duplicate events with same timestamp and message
          if (prev.some((e) => e.message === event.message && e.ts === event.ts)) {
            return prev
          }
          return [...prev, event]
        })
      },
      (err) => {
        console.warn("SSE stream error:", err)
      }
    )

    return () => {
      unsubscribe()
    }
  }, [incidentId])

  return timeline
}
