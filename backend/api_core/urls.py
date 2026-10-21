from django.urls import path
from .views import (
    health,
    receive_alert,
    list_incidents,
    get_incident,
    incident_stream,
    get_diff,
    get_postmortem,
    get_telemetry_current,
    get_telemetry_history,
    get_guardrails,
    demo_trigger,
    demo_reset,
    handle_config,
)

urlpatterns = [
    path('health', health, name='api_health'),
    path('alerts', receive_alert, name='api_alerts'),
    path('incidents', list_incidents, name='api_incidents_list'),
    path('incidents/<str:incident_id>', get_incident, name='api_incident_detail'),
    path('incidents/<str:incident_id>/stream', incident_stream, name='api_incident_stream'),
    path('incidents/<str:incident_id>/diff', get_diff, name='api_incident_diff'),
    path('incidents/<str:incident_id>/postmortem', get_postmortem, name='api_incident_postmortem'),
    path('telemetry/connections', get_telemetry_current, name='api_telemetry_current'),
    path('telemetry/connections/history', get_telemetry_history, name='api_telemetry_history'),
    path('guardrails', get_guardrails, name='api_guardrails'),
    path('demo/trigger', demo_trigger, name='api_demo_trigger'),
    path('demo/reset', demo_reset, name='api_demo_reset'),
    path('config', handle_config, name='api_config'),
]
