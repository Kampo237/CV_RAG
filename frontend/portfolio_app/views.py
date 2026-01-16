from django.shortcuts import render
from django.views import View


# Create your views here.


class Home(View):
    def get(self, request):
        return render(request,'portfolio_app/index.html')


class About(View):
    def get(self, request):
        return render(request,'portfolio_app/about.html')


class Cv(View):
    def get(self, request):
        return render(request,'portfolio_app/cv.html')

class Projets(View):
    def get(self, request):
        return render(request,'portfolio_app/projects.html')


class ProjetsDetails(View):
    def get(self, request):
        return render(request,'portfolio_app/project-details.html')

class Comments(View):
    def get(self, request):
        return render(request,'portfolio_app/commentaire.html')