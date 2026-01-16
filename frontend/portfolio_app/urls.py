from django.urls import path
from . import views

app_name = 'portfolio_app'

urlpatterns = [
    path('', views.Home.as_view(), name='home'),
    path('cv/', views.Cv.as_view(), name='cv'),
    path('about/', views.About.as_view(), name='about'),
    path('projets/', views.Projets.as_view(), name='projets'),
    path('projets/<int:pk>-<slug:slug>/', views.ProjetsDetails.as_view(), name='projets-details'),
    path('comments/', views.Comments.as_view(), name='comments'),
]
