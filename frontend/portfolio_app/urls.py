"""
URLs pour l'application Portfolio
"""
from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from . import views

app_name = 'portfolio_app'

urlpatterns = [
    # Pages principales
    path('', views.Home.as_view(), name='home'),
    path('cv/', views.Cv.as_view(), name='cv'),
    path('about/', views.About.as_view(), name='about'),
    path('projets/', views.Projets.as_view(), name='projets'),
    path('projets/details/', views.ProjetsDetails.as_view(), name='projets-details'),
    path('comments/', views.Comments.as_view(), name='comments'),

    # API Proxy (pour éviter CORS)
    path('api/chat/session', csrf_exempt(views.APIProxySession.as_view()), name='api-chat-session'),
    path('api/chat/message', csrf_exempt(views.APIProxyChat.as_view()), name='api-chat-message'),
    path('api/testimonials', csrf_exempt(views.APIProxyTestimonial.as_view()), name='api-testimonials'),
]
