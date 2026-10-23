from django.urls import path

from . import views

urlpatterns = [
    path("health", views.health, name="health"),
    path("alerts", views.receive_alert, name="alerts"),
]
