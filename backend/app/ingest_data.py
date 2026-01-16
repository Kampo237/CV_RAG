import requests
import os
import time , sys

# 1. Configuration
API_BASE = os.getenv("API_URL", "http://localhost:8001")
ENDPOINT = f"{API_BASE}/knowledge/add"

# 2. Tes données (Adaptées de ton dump précédent)
knowledge_base = [
    {
        "message_text": "Projet personnel: création d'un chatbot CV intelligent avec RAG, utilisant FastAPI, PostgreSQL, pgvector, Claude et Voyage AI. Déployé sur Render.",
        "category": "projet",
        "metadata": {
            "nom": "CV Chatbot",
            "statut": "en production",
            "technologies": ["FastAPI", "PostgreSQL", "Claude", "Voyage AI"],
            "db_id": 4
        }
    },
    {
        "message_text": "Je m'appelle Yann Willy Jordan Pokam Teguia et je suis un jeune diplômé en techniques de l'informatique au Cégep de Chicoutimi. Je suis passionné d'informatique et de tous ses aspects qui mettent en jeu la logique, le raisonnement poussé et les défis en tout genre. C'est d'ailleurs pourquoi j'ai élaboré mon CV sous forme électronique en intégrant un chatbot boosté à l'IA qui pourrait me représenter devant un employeur, premièrement pour démontrer mes réelles compétences techniques, mais aussi pour donner la possibilité à ce dernier d'avoir un aperçu du type d'employé que je peux être en donnant au mieux les armes nécessaires au chatbot pour le faire.",
        "category": "Général",
        "metadata": {
            "langue": "fr",
            "statut": "diplômé",
            "section": "presentation_personnelle",
            "mots_cles": ["formation", "passion", "logique", "chatbot IA", "CV électronique", "compétences techniques"],
            "programme": "Techniques de l'informatique",
            "importance": "haute",
            "institution": "Cégep de Chicoutimi",
            "candidat_nom": "Yann Willy Jordan Pokam Teguia",
            "date_creation": "2025-11-08",
            "document_type": "cv_introduction",
            "source_original": "cv_principal",
            "competences_liees": ["développement IA", "chatbot", "développement web, développement d'applications natives"],
            "db_id": 5
        }
    },
    {
        "message_text": "Je suis désolé, mais je ne peux pas répondre à des questions personnelles comme les préférences amoureuses, les habitudes alimentaires ou les sujets qui ne sont pas liés à mon profil professionnel ou technique.",
        "category": "Général",
        "metadata": {
            "langue": "fr",
            "motifs": ["question_personnelle", "hors_contexte", "confidentialité"],
            "section": "questions_hors_contexte",
            "importance": "haute",
            "type_reponse": "refus_poli",
            "date_creation": "2025-11-08",
            "document_type": "regle_conversationnelle",
            "db_id": 9
        }
    },
    {
        "message_text": "Je préfère garder mes réponses centrées sur mon parcours professionnel et mes compétences, afin de respecter la confidentialité et la pertinence du cadre de ce CV virtuel.",
        "category": "Général",
        "metadata": {
            "langue": "fr",
            "motifs": ["propos_humoristique", "hors_contexte"],
            "section": "ton_conversationnel",
            "importance": "moyenne",
            "type_reponse": "refus_contextuel",
            "document_type": "regle_conversationnelle",
            "db_id": 10
        }
    },
    {
        "message_text": "Je ne prends pas position sur des sujets politiques, religieux ou personnels. Mon objectif ici est de représenter mon profil professionnel.",
        "category": "Général",
        "metadata": {
            "langue": "fr",
            "section": "neutralite",
            "importance": "moyenne",
            "type_reponse": "refus_poli",
            "document_type": "regle_conversationnelle",
            "db_id": 11
        }
    },
    {
        "message_text": "Yann Willy Jordan Pokam Teguia est un jeune diplômé en Techniques de l’informatique au Cégep de Chicoutimi, passionné par les systèmes intelligents, la logique et les projets qui allient rigueur et créativité.",
        "category": "Profil professionnel",
        "metadata": {
            "langue": "fr",
            "niveau": "DEC",
            "section": "resume",
            "mots_cles": ["profil", "passion", "logique", "créativité"],
            "programme": "Techniques de l'informatique",
            "importance": "haute",
            "institution": "Cégep de Chicoutimi",
            "document_type": "cv_profil",
            "db_id": 12
        }
    },
    {
        "message_text": "Je suis une personne logique, curieuse et déterminée. J’aime comprendre le fonctionnement des systèmes complexes et trouver des solutions élégantes à des problèmes techniques.",
        "category": "Profil professionnel",
        "metadata": {
            "section": "valeurs_et_traits",
            "mots_cles": ["curiosité", "rigueur", "analyse", "logique"],
            "importance": "moyenne",
            "document_type": "description_personnalite",
            "db_id": 13
        }
    },
    {
        "message_text": "Je privilégie la qualité du code, la clarté de la structure et la maintenabilité avant tout. Un bon projet est un projet que quelqu’un d’autre peut reprendre facilement.",
        "category": "Profil professionnel",
        "metadata": {
            "section": "principes_professionnels",
            "mots_cles": ["qualité", "propreté du code", "maintenabilité"],
            "importance": "moyenne",
            "document_type": "ethique_travail",
            "db_id": 14
        }
    },
    {
        "message_text": "J’ai obtenu un DEC en Techniques de l’informatique au Cégep de Chicoutimi, où j’ai appris la programmation orientée objet, la conception de bases de données, le développement web et la gestion de projets logiciels.",
        "category": "Formation",
        "metadata": {
            "statut": "diplômé",
            "programme": "Techniques de l'informatique",
            "cours_cles": ["programmation orientée objet", "bases de données", "développement web", "gestion de projet"],
            "institution": "Cégep de Chicoutimi",
            "document_type": "formation_academique",
            "date_obtention": "2025",
            "db_id": 15
        }
    },
    {
        "message_text": "Pendant ma formation, j’ai développé plusieurs projets complets en C#, ASP.NET et WPF, me permettant d’appliquer concrètement les notions d’architecture logicielle et de modélisation UML.",
        "category": "Formation",
        "metadata": {
            "section": "projets_academiques",
            "document_type": "formation_projets",
            "competences_acquises": ["C#", "ASP.NET", "UML", "architecture logicielle"],
            "db_id": 16
        }
    },
    {
        "message_text": "Je maîtrise le développement en C#, .NET et WPF, ainsi que les principes du modèle MVVM pour concevoir des interfaces structurées et maintenables.",
        "category": "Compétences techniques",
        "metadata": {
            "section": "developpement_logiciel",
            "importance": "haute",
            "technologies": ["C#", ".NET", "WPF", "MVVM"],
            "document_type": "competence_technique",
            "niveau_maitrise": "avancé",
            "db_id": 17
        }
    },
    {
        "message_text": "Je conçois des applications web avec ASP.NET Core, Razor Pages et Bootstrap, en intégrant des fonctionnalités AJAX pour une meilleure interactivité.",
        "category": "Compétences techniques",
        "metadata": {
            "section": "developpement_web",
            "importance": "haute",
            "technologies": ["ASP.NET Core", "Razor", "Bootstrap", "AJAX"],
            "document_type": "competence_technique",
            "niveau_maitrise": "intermédiaire",
            "db_id": 18
        }
    },
    {
        "message_text": "Je développe des chatbots basés sur des modèles d’IA pour représenter des profils numériques ou assister des utilisateurs dans des interfaces conversationnelles.",
        "category": "Compétences techniques",
        "metadata": {
            "section": "intelligence_artificielle",
            "importance": "moyenne",
            "technologies": ["Python", "FastAPI", "embedding", "chatbots"],
            "document_type": "competence_technique",
            "niveau_maitrise": "intermédiaire",
            "db_id": 19
        }
    },
    {
        "message_text": "Je suis à l’aise avec les outils de documentation comme HelpNDoc et les tests unitaires automatisés via MSTest et FluentAssertions.",
        "category": "Compétences techniques",
        "metadata": {
            "section": "qualite_logicielle",
            "technologies": ["HelpNDoc", "MSTest", "FluentAssertions"],
            "document_type": "competence_technique",
            "niveau_maitrise": "intermédiaire",
            "db_id": 20
        }
    },
    {
        "message_text": "J’ai conçu une application de gestion de dépenses entre amis permettant d’attribuer dynamiquement des parts aux participants et de calculer les soldes selon les arrondis. Elle est bâtie en C# avec une architecture MVVM et une documentation complète sous HelpNDoc.",
        "category": "Projets réalisés",
        "metadata": {
            "section": "application_gestion_depenses",
            "importance": "haute",
            "technologies": ["C#", "WPF", "MVVM", "HelpNDoc"],
            "document_type": "projet_logiciel",
            "db_id": 21
        }
    },
    {
        "message_text": "J’ai développé une application WPF de gestion de bibliothèque intégrant une vue d’authentification, la gestion des livres et des emprunts, et des tests unitaires via MSTest et FluentAssertions.",
        "category": "Projets réalisés",
        "metadata": {
            "section": "application_bibliotheque",
            "importance": "moyenne",
            "technologies": ["C#", "WPF", "MSTest", "FluentAssertions"],
            "document_type": "projet_logiciel",
            "db_id": 22
        }
    },
    {
        "message_text": "J’ai élaboré un CV interactif sous forme de chatbot alimenté par un modèle d’IA, conçu pour simuler un entretien en ligne et permettre à un employeur de découvrir mes compétences techniques et mon raisonnement.",
        "category": "Projets réalisés",
        "metadata": {
            "section": "cv_intelligent",
            "importance": "très_haute",
            "technologies": ["FastAPI", "embedding", "chatbot IA"],
            "document_type": "projet_personnel",
            "db_id": 23
        }
    },
    {
        "message_text": "J’ai aussi développé des scripts d’automatisation et de simulation en Python, notamment pour des jeux de cartes simplifiés et des calculs de répartition de dépenses.",
        "category": "Projets réalisés",
        "metadata": {
            "section": "automation_python",
            "importance": "moyenne",
            "technologies": ["Python"],
            "document_type": "projet_experimentation",
            "db_id": 24
        }
    },
    {
        "message_text": "Je crois qu’un bon développeur ne se limite pas à écrire du code : il comprend le besoin, structure la solution et anticipe les erreurs possibles.",
        "category": "Philosophie et motivation",
        "metadata": {
            "mots_cles": ["rigueur", "analyse", "qualité", "anticipation"],
            "importance": "haute",
            "document_type": "philosophie_travail",
            "db_id": 25
        }
    },
    {
        "message_text": "Pour moi, chaque projet est une opportunité d’apprendre et de m’améliorer. Je valorise la collaboration et le partage de connaissances.",
        "category": "Philosophie et motivation",
        "metadata": {
            "mots_cles": ["collaboration", "apprentissage", "esprit_d_equipe"],
            "document_type": "valeur_professionnelle",
            "db_id": 26
        }
    },
    {
        "message_text": "Je privilégie les solutions élégantes et performantes aux solutions rapides. L’élégance d’un code bien pensé se traduit toujours dans sa maintenance.",
        "category": "Philosophie et motivation",
        "metadata": {
            "mots_cles": ["performance", "élégance", "maintenance"],
            "document_type": "philosophie_code",
            "db_id": 27
        }
    },
    {
        "message_text": "Je souhaite devenir gestionnaire de projet TI et développer mes compétences en gestion d’équipes, en planification et en coordination de projets technologiques.",
        "category": "Objectifs futurs",
        "metadata": {
            "mots_cles": ["gestion de projet", "coordination", "leadership"],
            "document_type": "aspiration_professionnelle",
            "db_id": 28
        }
    },
    {
        "message_text": "Je prévois de suivre des certifications en gestion de projet, notamment PMP et ITIL, afin de compléter mes connaissances techniques par une solide base en management.",
        "category": "Objectifs futurs",
        "metadata": {
            "importance": "moyenne",
            "document_type": "plan_formation_future",
            "certifications_ciblees": ["PMP", "ITIL"],
            "db_id": 29
        }
    },
    {
        "message_text": "Je consacre actuellement une dizaine d’heures par semaine à ma montée en compétences, notamment en suivant des formations en ligne dans le domaine des TI.",
        "category": "Objectifs futurs",
        "metadata": {
            "modalite": "en ligne",
            "document_type": "habitudes_apprentissage",
            "temps_hebdomadaire": "10 heures",
            "db_id": 30
        }
    },
    {
        "message_text": "Je cherche à combiner mes compétences en développement et mes aptitudes organisationnelles pour encadrer des projets TI ambitieux.",
        "category": "Objectifs futurs",
        "metadata": {
            "mots_cles": ["gestion de projet", "coordination", "leadership"],
            "document_type": "aspiration_professionnelle",
            "db_id": 31
        }
    },
    {
        "message_text": "J’ai une forte appétence pour la gestion des équipes techniques et la mise en place de processus de développement efficaces.",
        "category": "Objectifs futurs",
        "metadata": {
            "mots_cles": ["management", "processus", "efficacité"],
            "document_type": "vision_professionnelle",
            "db_id": 32
        }
    },
    {
        "message_text": "J’apprécie particulièrement les projets qui demandent de structurer l’information et d’organiser des systèmes complexes.",
        "category": "Profil professionnel",
        "metadata": {
            "mots_cles": ["organisation", "structure", "complexité"],
            "document_type": "interet_professionnel",
            "db_id": 33
        }
    },
    {
        "message_text": "Je suis passionné par l’interface entre la logique humaine et la logique machine — un espace où la créativité technique prend tout son sens.",
        "category": "Philosophie et motivation",
        "metadata": {
            "mots_cles": ["logique", "créativité", "interaction_homme_machine"],
            "document_type": "reflexion_personnelle",
            "db_id": 34
        }
    },
    {
        "message_text": "Je cherche à rendre mes applications à la fois esthétiques, ergonomiques et robustes, pour offrir une expérience utilisateur de qualité.",
        "category": "Compétences techniques",
        "metadata": {
            "mots_cles": ["UX", "UI", "ergonomie", "design"],
            "importance": "moyenne",
            "document_type": "competence_design",
            "db_id": 35
        }
    },
    {
        "message_text": "J’ai développé un intérêt particulier pour la documentation technique claire et structurée, afin de rendre chaque projet transmissible et durable.",
        "category": "Compétences techniques",
        "metadata": {
            "mots_cles": ["documentation", "structuration", "transmission"],
            "document_type": "competence_documentation",
            "db_id": 36
        }
    },
    {
        "message_text": "Je garde une vision à long terme de ma carrière, cherchant à progresser dans la gestion, sans jamais m’éloigner totalement du volet technique.",
        "category": "Objectifs futurs",
        "metadata": {
            "mots_cles": ["gestion", "carrière", "équilibre_technique"],
            "document_type": "vision_long_terme",
            "db_id": 37
        }
    },
    {
        "message_text": "Mon approche du travail repose sur la rigueur, la planification et la remise en question constante de mes méthodes pour les améliorer.",
        "category": "Philosophie et motivation",
        "metadata": {
            "mots_cles": ["rigueur", "perfectionnement", "auto-évaluation"],
            "document_type": "ethique_professionnelle",
            "db_id": 38
        }
    }
]

def ingest_data():
    print(f"🕒 Attente de la disponibilité de l'API à {API_BASE}...")

    # Petite boucle pour attendre que l'API soit prête (retry pattern)
    for i in range(10):
        try:
            # On tente juste un ping ou un check basique
            requests.get(f"{API_BASE}/docs", timeout=2)
            print("🚀 API détectée ! Envoi des données...")
            break
        except requests.exceptions.ConnectionError:
            time.sleep(2)
            print(f"⏳ Tentative {i + 1}/10...")
    else:
        print("❌ Impossible de joindre l'API après 20 secondes.")
        sys.exit(1)

    try:
        print(f"📦 Envoi de {len(knowledge_base)} éléments...")
        response = requests.post(ENDPOINT, json=knowledge_base)

        if response.status_code == 200:
            print("✅ SUCCÈS ! Base de données initialisée avec les données CV.")
            print("Réponse:", response.json())
        else:
            print(f"❌ Erreur {response.status_code}")
            print(response.text)

    except Exception as e:
        print(f"❌ Erreur critique : {e}")


if __name__ == "__main__":
    ingest_data()