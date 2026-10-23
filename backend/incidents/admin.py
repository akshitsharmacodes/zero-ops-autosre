from django.contrib import admin

from .models import AgentStep, AuditLog, GuardrailResult, Incident, RuntimeConfig, SandboxRun, TimelineEvent


class TimelineInline(admin.TabularInline):
    model = TimelineEvent
    extra = 0
    fields = ("ts", "tag", "state", "message")
    readonly_fields = fields


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "mode", "source", "attempt", "branch", "created_at")
    list_filter = ("status", "mode", "source")
    inlines = [TimelineInline]


@admin.register(AgentStep)
class AgentStepAdmin(admin.ModelAdmin):
    list_display = ("incident", "task", "attempt", "step", "tool", "ok", "ts")
    list_filter = ("task", "tool", "ok")


@admin.register(SandboxRun)
class SandboxRunAdmin(admin.ModelAdmin):
    list_display = ("incident", "task", "attempt", "engine", "isolated", "passed", "reproduced", "exit_code", "ts")


@admin.register(GuardrailResult)
class GuardrailResultAdmin(admin.ModelAdmin):
    list_display = ("incident", "attempt", "check_id", "passed", "ts")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("incident", "kind", "ts")
    list_filter = ("kind",)


admin.site.register(RuntimeConfig)
