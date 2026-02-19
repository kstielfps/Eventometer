"""
Simple health check and monitoring views.
"""
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
@require_http_methods(["GET", "HEAD"])
def health_check(request):
    """Health check endpoint for Railway and monitoring.
    This is also served by HealthCheckMiddleware before any other middleware,
    to ensure it always responds 200 even if ALLOWED_HOSTS or SSL redirect
    would block the request.
    """
    return JsonResponse({
        "status": "healthy",
        "service": "eventometer",
        "message": "ATC Booking System is running"
    })


@csrf_exempt
@require_http_methods(["GET"])
def bot_status(request):
    """Check if the Discord bot is running."""
    from django.core.cache import cache
    
    bot_active = cache.get('bot_last_heartbeat', False)
    
    return JsonResponse({
        "bot_connected": bool(bot_active),
        "message": "Bot is running" if bot_active else "Bot status unknown"
    })
