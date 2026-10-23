from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("reports/top-pages/", views.top_pages, name="top_pages"),
    path("metrics/summary/", views.metrics_summary, name="metrics_summary"),
    path("reports/user-activity/", views.user_activity_report, name="user_activity_report"),
]
