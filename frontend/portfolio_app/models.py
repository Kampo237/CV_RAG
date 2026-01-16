"""
Modèles Django pour le Portfolio

Ces modèles sont utilisés pour:
- Affichage des données sur le site
- Administration via Django Admin
- Cache local des données du backend
"""
from django.db import models
from django.utils.text import slugify


class Projet(models.Model):
    """
    Modèle des projets pour affichage dans le portfolio
    Les données principales sont dans le backend (table datas)
    Ce modèle sert de cache/enrichissement pour le frontend
    """
    titre = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    description_courte = models.CharField(max_length=300, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='projets/', blank=True, null=True)
    technologies = models.JSONField(default=list, blank=True)
    url_github = models.URLField(blank=True)
    url_demo = models.URLField(blank=True)
    date_realisation = models.DateField(blank=True, null=True)
    est_mis_en_avant = models.BooleanField(default=False)
    ordre_affichage = models.IntegerField(default=0)
    est_actif = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['ordre_affichage', '-date_realisation']
        verbose_name = 'Projet'
        verbose_name_plural = 'Projets'

    def __str__(self):
        return self.titre

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.titre)
        super().save(*args, **kwargs)

    def to_dict(self):
        return {
            'id': self.id,
            'titre': self.titre,
            'slug': self.slug,
            'description_courte': self.description_courte,
            'description': self.description,
            'image': self.image.url if self.image else None,
            'technologies': self.technologies,
            'url_github': self.url_github,
            'url_demo': self.url_demo,
            'date_realisation': self.date_realisation.isoformat() if self.date_realisation else None,
            'est_mis_en_avant': self.est_mis_en_avant,
        }


class Competence(models.Model):
    """
    Modèle des compétences techniques
    """
    NIVEAU_CHOICES = [
        (1, 'Débutant'),
        (2, 'Intermédiaire'),
        (3, 'Avancé'),
        (4, 'Expert'),
        (5, 'Maîtrise'),
    ]

    CATEGORIE_CHOICES = [
        ('backend', 'Backend'),
        ('frontend', 'Frontend'),
        ('database', 'Base de données'),
        ('devops', 'DevOps'),
        ('mobile', 'Mobile'),
        ('ai', 'Intelligence Artificielle'),
        ('tools', 'Outils'),
        ('soft', 'Soft Skills'),
    ]

    nom = models.CharField(max_length=100)
    categorie = models.CharField(max_length=50, choices=CATEGORIE_CHOICES)
    niveau = models.IntegerField(choices=NIVEAU_CHOICES, default=3)
    icone = models.CharField(max_length=50, blank=True, help_text="Classe d'icône (ex: fab fa-python)")
    description = models.TextField(blank=True)
    ordre_affichage = models.IntegerField(default=0)
    est_actif = models.BooleanField(default=True)

    class Meta:
        ordering = ['categorie', 'ordre_affichage', '-niveau']
        verbose_name = 'Compétence'
        verbose_name_plural = 'Compétences'

    def __str__(self):
        return f"{self.nom} ({self.get_categorie_display()})"

    def to_dict(self):
        return {
            'id': self.id,
            'nom': self.nom,
            'categorie': self.categorie,
            'categorie_display': self.get_categorie_display(),
            'niveau': self.niveau,
            'niveau_display': self.get_niveau_display(),
            'icone': self.icone,
            'description': self.description,
        }


class Experience(models.Model):
    """
    Modèle des expériences professionnelles
    """
    TYPE_CHOICES = [
        ('emploi', 'Emploi'),
        ('stage', 'Stage'),
        ('freelance', 'Freelance'),
        ('benevole', 'Bénévolat'),
    ]

    titre = models.CharField(max_length=200)
    entreprise = models.CharField(max_length=200)
    type_experience = models.CharField(max_length=50, choices=TYPE_CHOICES, default='emploi')
    lieu = models.CharField(max_length=200, blank=True)
    date_debut = models.DateField()
    date_fin = models.DateField(blank=True, null=True)
    en_cours = models.BooleanField(default=False)
    description = models.TextField()
    technologies = models.JSONField(default=list, blank=True)
    realisations = models.JSONField(default=list, blank=True)
    ordre_affichage = models.IntegerField(default=0)
    est_actif = models.BooleanField(default=True)

    class Meta:
        ordering = ['-en_cours', '-date_debut']
        verbose_name = 'Expérience'
        verbose_name_plural = 'Expériences'

    def __str__(self):
        return f"{self.titre} - {self.entreprise}"

    def to_dict(self):
        return {
            'id': self.id,
            'titre': self.titre,
            'entreprise': self.entreprise,
            'type_experience': self.type_experience,
            'type_display': self.get_type_experience_display(),
            'lieu': self.lieu,
            'date_debut': self.date_debut.isoformat() if self.date_debut else None,
            'date_fin': self.date_fin.isoformat() if self.date_fin else None,
            'en_cours': self.en_cours,
            'description': self.description,
            'technologies': self.technologies,
            'realisations': self.realisations,
        }


class Formation(models.Model):
    """
    Modèle des formations académiques
    """
    titre = models.CharField(max_length=200)
    etablissement = models.CharField(max_length=200)
    lieu = models.CharField(max_length=200, blank=True)
    date_debut = models.DateField()
    date_fin = models.DateField(blank=True, null=True)
    en_cours = models.BooleanField(default=False)
    description = models.TextField(blank=True)
    diplome_obtenu = models.BooleanField(default=False)
    mention = models.CharField(max_length=100, blank=True)
    ordre_affichage = models.IntegerField(default=0)
    est_actif = models.BooleanField(default=True)

    class Meta:
        ordering = ['-en_cours', '-date_debut']
        verbose_name = 'Formation'
        verbose_name_plural = 'Formations'

    def __str__(self):
        return f"{self.titre} - {self.etablissement}"

    def to_dict(self):
        return {
            'id': self.id,
            'titre': self.titre,
            'etablissement': self.etablissement,
            'lieu': self.lieu,
            'date_debut': self.date_debut.isoformat() if self.date_debut else None,
            'date_fin': self.date_fin.isoformat() if self.date_fin else None,
            'en_cours': self.en_cours,
            'description': self.description,
            'diplome_obtenu': self.diplome_obtenu,
            'mention': self.mention,
        }


class InfoPersonnelle(models.Model):
    """
    Modèle singleton pour les informations personnelles
    """
    nom_complet = models.CharField(max_length=200)
    surnom = models.CharField(max_length=100, blank=True)
    titre_professionnel = models.CharField(max_length=200)
    email = models.EmailField()
    telephone = models.CharField(max_length=20, blank=True)
    localisation = models.CharField(max_length=200)
    bio_courte = models.CharField(max_length=500)
    bio_complete = models.TextField()
    photo = models.ImageField(upload_to='profile/', blank=True, null=True)
    cv_pdf = models.FileField(upload_to='cv/', blank=True, null=True)
    linkedin = models.URLField(blank=True)
    github = models.URLField(blank=True)
    portfolio = models.URLField(blank=True)
    disponible = models.BooleanField(default=True)
    recherche_type = models.CharField(max_length=200, blank=True, help_text="Ex: Stage, Emploi, Freelance")

    class Meta:
        verbose_name = 'Information Personnelle'
        verbose_name_plural = 'Informations Personnelles'

    def __str__(self):
        return self.nom_complet

    def save(self, *args, **kwargs):
        # Singleton: s'assurer qu'il n'y a qu'une seule instance
        if not self.pk and InfoPersonnelle.objects.exists():
            raise ValueError("Il ne peut y avoir qu'une seule instance de InfoPersonnelle")
        super().save(*args, **kwargs)

    @classmethod
    def get_instance(cls):
        """Retourne l'instance unique ou None"""
        return cls.objects.first()

    def to_dict(self):
        return {
            'nom_complet': self.nom_complet,
            'surnom': self.surnom,
            'titre_professionnel': self.titre_professionnel,
            'email': self.email,
            'telephone': self.telephone,
            'localisation': self.localisation,
            'bio_courte': self.bio_courte,
            'bio_complete': self.bio_complete,
            'photo': self.photo.url if self.photo else None,
            'cv_pdf': self.cv_pdf.url if self.cv_pdf else None,
            'linkedin': self.linkedin,
            'github': self.github,
            'portfolio': self.portfolio,
            'disponible': self.disponible,
            'recherche_type': self.recherche_type,
        }
