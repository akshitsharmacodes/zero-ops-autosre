from django.urls import path, include
from analytics.views import health_check

urlpatterns = [
    path('health/', health_check, name='health_check'),
    path('api/', include('analytics.urls')),
]
