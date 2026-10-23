from rest_framework import serializers

from ..models import Incident


class IncidentSummarySerializer(serializers.ModelSerializer):
    mttr_seconds = serializers.IntegerField(read_only=True)
    time_to_mitigate_seconds = serializers.IntegerField(read_only=True)

    class Meta:
        model = Incident
        fields = [
            "id", "status", "mode", "source", "alert", "attempt", "max_attempts", "branch",
            "pull_request", "sandbox_isolated", "escalation_reason", "created_at", "mitigated_at",
            "pr_opened_at", "ready_at", "finished_at", "mttr_seconds", "time_to_mitigate_seconds",
        ]
