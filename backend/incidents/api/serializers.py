from rest_framework import serializers

from ..models import AgentStep, GuardrailResult, Incident, SandboxRun, TimelineEvent


class TimelineEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimelineEvent
        fields = ["id", "ts", "tag", "message", "state"]


class AgentStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentStep
        fields = ["id", "ts", "task", "attempt", "step", "thought", "tool", "args", "ok", "result"]


class SandboxRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = SandboxRun
        fields = ["id", "ts", "task", "attempt", "engine", "isolated", "passed", "reproduced", "exit_code",
                  "timed_out", "duration_seconds", "output", "limits"]


class GuardrailResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = GuardrailResult
        fields = ["id", "ts", "attempt", "check_id", "name", "passed", "details"]


class IncidentSummarySerializer(serializers.ModelSerializer):
    mttr_seconds = serializers.IntegerField(read_only=True)
    time_to_mitigate_seconds = serializers.IntegerField(read_only=True)

    class Meta:
        model = Incident
        fields = [
            "id", "status", "mode", "approval_mode", "pending_approval", "source", "alert", "attempt", "max_attempts", "branch",
            "pull_request", "sandbox_isolated", "escalation_reason", "created_at", "mitigated_at",
            "pr_opened_at", "ready_at", "finished_at", "mttr_seconds", "time_to_mitigate_seconds",
        ]


class IncidentDetailSerializer(IncidentSummarySerializer):
    timeline = TimelineEventSerializer(source="events", many=True, read_only=True)

    class Meta(IncidentSummarySerializer.Meta):
        fields = IncidentSummarySerializer.Meta.fields + [
            "telemetry", "mitigation", "diagnosis", "suspect", "project_profile", "fix", "llm", "timeline",
            "related_incidents", "ai_card",
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # The full commit diff and sandbox output are large; they have their own endpoints.
        if isinstance(data.get("suspect"), dict):
            data["suspect"] = {k: v for k, v in data["suspect"].items() if k != "commit_diff"}
        if isinstance(data.get("fix"), dict) and isinstance(data["fix"].get("sandbox"), dict):
            data["fix"]["sandbox"] = {k: v for k, v in data["fix"]["sandbox"].items() if k != "output"}
        return data
