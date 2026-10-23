"""
Jeu de questions pour l'évaluation RAGAS (qualité des réponses).

Réécrit le 2026-10-23 à partir des tables canoniques Neon : les réponses de
référence reprennent les faits en base (profil, projets, expériences,
formation, compétences, témoignages). À mettre à jour quand les données
changent — une référence périmée fait baisser les scores sans que le chat
soit en cause.

Chaque entrée :
  - user_input : la question du visiteur
  - reference  : la réponse correcte attendue (faits de la base)
  - theme      : regroupement pour l'analyse des scores
  - path       : chemin attendu en production — "rapide" (fast_path) ou "agent"
"""

TEST_DATASET = [
    # --- Profil ---------------------------------------------------------------
    {
        "user_input": "Parle-moi de toi",
        "reference": ("Jordan est technicien en informatique, diplômé en Techniques de l'informatique, basé à "
                      "Chicoutimi (Saguenay), au Québec. Il fait du soutien aux utilisateurs, de la gestion de parc et "
                      "du dépannage matériel et logiciel, et développe ou modifie des applications en C#, Python et "
                      "SQL. Il mène ses projets de bout en bout, de la base de données au déploiement."),
        "theme": "profil", "path": "rapide",
    },
    {
        "user_input": "Quel type de poste recherches-tu ?",
        "reference": ("Jordan recherche un emploi en TI : développement, programmation ou soutien informatique. "
                      "Il est disponible et peut se déplacer (permis de conduire valide)."),
        "theme": "profil", "path": "rapide",
    },
    {
        "user_input": "Comment te contacter ?",
        "reference": ("Par courriel à kampo@jordan-pokam.dev, ou via LinkedIn et GitHub (Kampo237). "
                      "Le portfolio est portfolio.jordan-pokam.dev."),
        "theme": "profil", "path": "rapide",
    },
    {
        "user_input": "As-tu un CV en PDF ?",
        "reference": "Oui, le CV en PDF est téléchargeable à l'adresse https://portfolio.jordan-pokam.dev/CV_Jordan_Pokam_Teguia.pdf.",
        "theme": "profil", "path": "rapide",
    },
    # --- Expériences ----------------------------------------------------------
    {
        "user_input": "Où travailles-tu en ce moment ?",
        "reference": ("Son poste principal actuel est superviseur de contrat chez GardaWorld, sur le site du Cégep de "
                      "Chicoutimi, à temps partiel depuis juillet 2026 : il encadre une équipe de six agents."),
        "theme": "experiences", "path": "rapide",
    },
    {
        "user_input": "Quelles sont toutes tes expériences professionnelles ?",
        "reference": ("Superviseur de contrat chez GardaWorld (temps partiel, poste principal, depuis juillet 2026) ; "
                      "préposé à l'entretien industriel chez Globatech, sous-traitant de Rio Tinto (sur appel, depuis "
                      "juillet 2024) ; agent de centre d'appels chez Uni Marketing (septembre à novembre 2023) ; "
                      "responsable informatique au Restaurant La Cantine à Yaoundé (décembre 2022 à février 2023)."),
        "theme": "experiences", "path": "rapide",
    },
    {
        "user_input": "Ton travail chez Globatech, c'est un emploi régulier ?",
        "reference": ("Non. Chez Globatech (sous-traitant de Rio Tinto), il est préposé à l'entretien industriel sur "
                      "appel seulement : il y va selon ses disponibilités et peut refuser un appel."),
        "theme": "experiences", "path": "agent",
    },
    {
        "user_input": "As-tu déjà fait du soutien informatique en entreprise ?",
        "reference": ("Oui : comme responsable informatique au Restaurant La Cantine (Yaoundé, 2022-2023), il gérait le "
                      "parc informatique (installation, configuration, dépannage) et assistait les employés sur place."),
        "theme": "experiences", "path": "agent",
    },
    # --- Formation ------------------------------------------------------------
    {
        "user_input": "Quelle est ta formation ?",
        "reference": ("DEC en Techniques de l'informatique — Conception et développement d'applications au Cégep de "
                      "Chicoutimi (2023-2026, diplôme obtenu en mai 2026) ; préparation en cours à la certification "
                      "Microsoft PL-900 ; études universitaires en sciences (mathématiques et génie mécanique) au "
                      "Cameroun de 2021 à 2023, sans diplôme ; baccalauréat scientifique obtenu en 2021."),
        "theme": "formation", "path": "rapide",
    },
    {
        "user_input": "As-tu la certification PL-900 ?",
        "reference": ("Pas encore : il prépare la certification Microsoft Power Platform Fundamentals (PL-900), examen "
                      "prévu le 15 octobre 2026."),
        "theme": "formation", "path": "rapide",
    },
    # --- Projets --------------------------------------------------------------
    {
        "user_input": "Quels sont tes projets ?",
        "reference": ("Super CChic (système de point de vente pour épiceries), CV Chatbot RAG (assistant RAG en "
                      "production sur son portfolio), SafetyHub (analyse des risques SST assistée par IA, mention "
                      "honorable au Hackathon UQAC 2025), Gestionnaire de projets (application desktop C# WPF) et "
                      "L'Écrin de Julia's (boutique en ligne, en développement)."),
        "theme": "projets", "path": "rapide",
    },
    {
        "user_input": "Parle-moi de Super CChic",
        "reference": ("Super CChic est son projet de fin de DEC (2026) : un système de point de vente complet pour "
                      "épiceries avec un assistant IA, réalisé seul. Trois applications WPF, une API ASP.NET Core et un "
                      "tableau de bord React ; MySQL, Docker et déploiement sur Azure."),
        "theme": "projets", "path": "rapide",
    },
    {
        "user_input": "Quelles technologies as-tu utilisées pour ton chatbot RAG ?",
        "reference": ("Python, FastAPI, LangChain, LangGraph, PostgreSQL avec pgvector, Claude API, Voyage AI, "
                      "Docker, AWS et Linux. Il tourne en production sur portfolio.jordan-pokam.dev depuis fin 2025."),
        "theme": "projets", "path": "rapide",
    },
    {
        "user_input": "Qu'est-ce que SafetyHub ?",
        "reference": ("Un système d'analyse des risques en santé et sécurité au travail, assisté par IA, réalisé en équipe "
                      "de deux au Hackathon UQAC 2025 (novembre 2025). Back-end Django (API REST), interface React, "
                      "assistant RAG avec des modèles locaux via Ollama. Mention honorable."),
        "theme": "projets", "path": "rapide",
    },
    {
        "user_input": "Quel est ton meilleur projet et pourquoi ?",
        "reference": ("Ses projets mis en avant sont Super CChic, CV Chatbot RAG et SafetyHub. Super CChic est le plus "
                      "complet (projet de fin de DEC réalisé seul) ; CV Chatbot RAG est en production ; SafetyHub a "
                      "obtenu une mention honorable au Hackathon UQAC 2025."),
        "theme": "projets", "path": "agent",
    },
    {
        "user_input": "L'Écrin de Julia's est-il en ligne ?",
        "reference": ("Non, pas encore : c'est une boutique en ligne de perruques et de mode avec prise de rendez-vous, "
                      "développée pour une cliente, toujours en développement ; la mise en ligne est à venir."),
        "theme": "projets", "path": "rapide",
    },
    # --- Compétences ----------------------------------------------------------
    {
        "user_input": "Tu connais Docker ?",
        "reference": ("Oui, Docker fait partie de ses compétences (systèmes et réseaux) : conteneurisation et "
                      "déploiement, notamment pour son chatbot RAG en production et Super CChic."),
        "theme": "competences", "path": "rapide",
    },
    {
        "user_input": "Quelles langues parles-tu ?",
        "reference": "Français courant et anglais intermédiaire / avancé.",
        "theme": "competences", "path": "rapide",
    },
    {
        "user_input": "As-tu de l'expérience avec le cloud ?",
        "reference": ("Oui : Azure (déploiement de Super CChic) et AWS EC2 (hébergement de production du chatbot RAG), "
                      "ainsi que Linux, Docker, DNS, certificats TLS, proxy inverse et pare-feu."),
        "theme": "competences", "path": "agent",
    },
    # --- Témoignages et règles ------------------------------------------------
    {
        "user_input": "As-tu des témoignages ?",
        "reference": ("Oui, celui de Chabi Joelle, technicien informatique à l'UQAC, qui décrit Jordan comme quelqu'un "
                      "de très travailleur et rigoureux."),
        "theme": "temoignages", "path": "rapide",
    },
    {
        "user_input": "Parle-moi de NOVA GAMES",
        "reference": "Il n'a pas d'information sur un projet NOVA GAMES : ce n'est pas un de ses projets actuels.",
        "theme": "regles", "path": "agent",
    },
    {
        "user_input": "Qu'est-ce qui te motive dans l'informatique ?",
        "reference": ("Il aime résoudre des problèmes concrets, autant pour un utilisateur pressé que face à un problème "
                      "qui demande d'ouvrir les journaux, et mener ses projets de bout en bout jusqu'à la production."),
        "theme": "profil", "path": "agent",
    },
]
