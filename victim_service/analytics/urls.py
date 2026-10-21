from django.urls import path
from .views import metrics_summary, user_activity_report

urlpatterns = [
    path('metrics/summary/', metrics_summary, name='metrics_summary'),
    path('reports/user-activity/', user_activity_report, name='user_activity_report'),
]
