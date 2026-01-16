"""
Context Processors pour le Portfolio
Rend les variables globales disponibles dans tous les templates
"""

from django.conf import settings


def api_settings(request):
    """
    Ajoute les paramètres de l'API au contexte de tous les templates
    """
    return {
        'API_BASE_URL': getattr(settings, 'API_BASE_URL', 'http://localhost:8001'),
        'DEBUG': settings.DEBUG,
    }
