"""
Views Django pour le Portfolio

Ces views utilisent les modèles Django locaux et peuvent
également récupérer des données depuis l'API backend.
"""
from django.shortcuts import render, get_object_or_404
from django.views import View
from django.http import JsonResponse
from django.conf import settings
import requests
import logging

from .models import Projet, Competence, Experience, Formation, InfoPersonnelle

logger = logging.getLogger(__name__)

# URL de l'API Backend
API_BASE_URL = getattr(settings, 'API_BASE_URL', 'http://localhost:8001')


def get_api_data(endpoint: str, default=None):
    """Helper pour récupérer des données depuis l'API backend"""
    try:
        response = requests.get(f"{API_BASE_URL}{endpoint}", timeout=5)
        if response.status_code == 200:
            return response.json()
    except requests.RequestException as e:
        logger.warning(f"Erreur API {endpoint}: {e}")
    return default


class Home(View):
    """Page d'accueil du portfolio"""

    def get(self, request):
        context = {
            'info': InfoPersonnelle.get_instance(),
            'projets_featured': Projet.objects.filter(est_actif=True, est_mis_en_avant=True)[:3],
            'competences': Competence.objects.filter(est_actif=True)[:8],
        }
        return render(request, 'portfolio_app/index.html', context)


class About(View):
    """Page À propos"""

    def get(self, request):
        context = {
            'info': InfoPersonnelle.get_instance(),
            'formations': Formation.objects.filter(est_actif=True),
            'experiences': Experience.objects.filter(est_actif=True),
        }
        return render(request, 'portfolio_app/about.html', context)


class Cv(View):
    """Page CV"""

    def get(self, request):
        context = {
            'info': InfoPersonnelle.get_instance(),
            'formations': Formation.objects.filter(est_actif=True),
            'experiences': Experience.objects.filter(est_actif=True),
            'competences': Competence.objects.filter(est_actif=True),
        }
        return render(request, 'portfolio_app/cv.html', context)


class Projets(View):
    """Page des projets"""

    def get(self, request):
        # Projets depuis Django
        projets_django = list(Projet.objects.filter(est_actif=True))

        # Projets depuis l'API (table datas)
        api_data = get_api_data('/api/projects', {'projects': []})
        projets_api = api_data.get('projects', [])

        context = {
            'info': InfoPersonnelle.get_instance(),
            'projets': projets_django,
            'projets_api': projets_api,
        }
        return render(request, 'portfolio_app/projects.html', context)


class ProjetsDetails(View):
    """Détails d'un projet (pour le modal)"""

    def get(self, request):
        projet_id = request.GET.get('id')
        source = request.GET.get('source', 'django')

        if source == 'api' and projet_id:
            # Récupérer depuis l'API
            data = get_api_data(f'/api/projects/{projet_id}')
            if data:
                return JsonResponse(data)
            return JsonResponse({'error': 'Projet non trouvé'}, status=404)

        elif projet_id:
            # Récupérer depuis Django
            projet = get_object_or_404(Projet, id=projet_id, est_actif=True)
            return JsonResponse(projet.to_dict())

        # Fallback: afficher le template
        return render(request, 'portfolio_app/project-details.html')


class Comments(View):
    """Page commentaires/témoignages avec chatbot"""

    def get(self, request):
        # Récupérer les témoignages depuis l'API
        api_data = get_api_data('/api/testimonials/', {'testimonials': []})
        testimonials = api_data.get('testimonials', [])

        # Récupérer les FAQ
        faq_data = get_api_data('/faq/', {'categories': {}})
        faqs = faq_data.get('categories', {})

        context = {
            'info': InfoPersonnelle.get_instance(),
            'testimonials': testimonials,
            'faqs': faqs,
        }
        return render(request, 'portfolio_app/commentaire.html', context)


# =============================================================================
# API PROXY VIEWS (pour éviter les problèmes CORS)
# =============================================================================

class APIProxyChat(View):
    """Proxy pour l'API de chat"""

    def post(self, request):
        try:
            import json
            data = json.loads(request.body)

            response = requests.post(
                f"{API_BASE_URL}/api/chat/message",
                json=data,
                headers={'Content-Type': 'application/json'},
                stream=True,
                timeout=60
            )

            # Streamer la réponse
            from django.http import StreamingHttpResponse

            def generate():
                for chunk in response.iter_content(chunk_size=1):
                    if chunk:
                        yield chunk.decode('utf-8', errors='ignore')

            return StreamingHttpResponse(
                generate(),
                content_type='text/plain'
            )

        except Exception as e:
            logger.error(f"Erreur proxy chat: {e}")
            return JsonResponse({'error': str(e)}, status=500)


class APIProxySession(View):
    """Proxy pour la création de session"""

    def post(self, request):
        try:
            import json
            data = json.loads(request.body)

            response = requests.post(
                f"{API_BASE_URL}/api/chat/session",
                json=data,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )

            return JsonResponse(response.json(), status=response.status_code)

        except Exception as e:
            logger.error(f"Erreur proxy session: {e}")
            return JsonResponse({'error': str(e)}, status=500)


class APIProxyTestimonial(View):
    """Proxy pour les témoignages"""

    def post(self, request):
        try:
            import json
            data = json.loads(request.body)

            response = requests.post(
                f"{API_BASE_URL}/api/testimonials/",
                json=data,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )

            return JsonResponse(response.json(), status=response.status_code)

        except Exception as e:
            logger.error(f"Erreur proxy testimonial: {e}")
            return JsonResponse({'error': str(e)}, status=500)
