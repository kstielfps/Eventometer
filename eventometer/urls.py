"""
URL configuration for eventometer project.
"""
from django.contrib import admin
from django.urls import path
from core.health import health_check, bot_status

urlpatterns = [
    path('admin/', admin.site.urls),
    path('health/', health_check, name='health_check'),
    path('bot-status/', bot_status, name='bot_status'),
]
