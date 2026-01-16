"""
Configuration de l'administration Django pour le Portfolio
"""
from django.contrib import admin
from .models import Projet, Competence, Experience, Formation, InfoPersonnelle


@admin.register(Projet)
class ProjetAdmin(admin.ModelAdmin):
    list_display = ['titre', 'est_mis_en_avant', 'est_actif', 'ordre_affichage', 'date_realisation']
    list_filter = ['est_actif', 'est_mis_en_avant']
    search_fields = ['titre', 'description']
    prepopulated_fields = {'slug': ('titre',)}
    ordering = ['ordre_affichage', '-date_realisation']
    list_editable = ['est_mis_en_avant', 'est_actif', 'ordre_affichage']


@admin.register(Competence)
class CompetenceAdmin(admin.ModelAdmin):
    list_display = ['nom', 'categorie', 'niveau', 'est_actif', 'ordre_affichage']
    list_filter = ['categorie', 'niveau', 'est_actif']
    search_fields = ['nom', 'description']
    ordering = ['categorie', 'ordre_affichage']
    list_editable = ['niveau', 'est_actif', 'ordre_affichage']


@admin.register(Experience)
class ExperienceAdmin(admin.ModelAdmin):
    list_display = ['titre', 'entreprise', 'type_experience', 'date_debut', 'en_cours', 'est_actif']
    list_filter = ['type_experience', 'en_cours', 'est_actif']
    search_fields = ['titre', 'entreprise', 'description']
    ordering = ['-en_cours', '-date_debut']
    list_editable = ['en_cours', 'est_actif']


@admin.register(Formation)
class FormationAdmin(admin.ModelAdmin):
    list_display = ['titre', 'etablissement', 'date_debut', 'en_cours', 'diplome_obtenu', 'est_actif']
    list_filter = ['en_cours', 'diplome_obtenu', 'est_actif']
    search_fields = ['titre', 'etablissement', 'description']
    ordering = ['-en_cours', '-date_debut']
    list_editable = ['en_cours', 'diplome_obtenu', 'est_actif']


@admin.register(InfoPersonnelle)
class InfoPersonnelleAdmin(admin.ModelAdmin):
    list_display = ['nom_complet', 'titre_professionnel', 'email', 'disponible']
    fieldsets = (
        ('Identité', {
            'fields': ('nom_complet', 'surnom', 'titre_professionnel', 'photo')
        }),
        ('Contact', {
            'fields': ('email', 'telephone', 'localisation')
        }),
        ('Bio', {
            'fields': ('bio_courte', 'bio_complete')
        }),
        ('Liens', {
            'fields': ('linkedin', 'github', 'portfolio', 'cv_pdf')
        }),
        ('Statut', {
            'fields': ('disponible', 'recherche_type')
        }),
    )

    def has_add_permission(self, request):
        # Empêcher l'ajout si une instance existe déjà (singleton)
        return not InfoPersonnelle.objects.exists()
