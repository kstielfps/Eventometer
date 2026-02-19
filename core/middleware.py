"""
Custom middleware for the Eventometer project.
"""
from django.http import JsonResponse


class HealthCheckMiddleware:
    """
    Intercepts requests to /health/ BEFORE any other middleware runs.
    This ensures the healthcheck always returns 200, regardless of
    ALLOWED_HOSTS, SECURE_SSL_REDIRECT, or other security settings.

    Must be placed FIRST in the MIDDLEWARE list.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/health/":
            return JsonResponse({
                "status": "healthy",
                "service": "eventometer",
                "message": "ATC Booking System is running",
            })
        return self.get_response(request)
