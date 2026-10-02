"""
Dataset de test pour l'évaluation RAGAS du chatbot CV.

Chaque entrée contient :
  - user_input : la question posée
  - reference  : la réponse correcte attendue (ground truth, écrite à la main)
  - intent     : l'intent attendu (SQL, VECTOR, VECTOR_SQL, OFF_TOPIC) — pour analyse

Les champs `response` et `retrieved_contexts` seront remplis automatiquement
par le script run_baseline.py en exécutant le pipeline RAG.
"""

TEST_DATASET = [
    # ═══════════════════════════════════════════════════════════════
    # VECTOR — Questions qualitatives / descriptives
    # ═══════════════════════════════════════════════════════════════
    {
        "user_input": "Parle-moi de toi",
        "reference": "Yann Willy Jordan Pokam Teguia est un jeune diplômé en Techniques de l'informatique au Cégep de Chicoutimi, passionné par les systèmes intelligents, la logique et les projets qui allient rigueur et créativité.",
        "intent": "VECTOR",
    },
    {
        "user_input": "Quelle est ta philosophie de code ?",
        "reference": "Il privilégie la qualité du code, la clarté de la structure et la maintenabilité. Un bon projet est un projet que quelqu'un d'autre peut reprendre facilement. Il préfère les solutions élégantes et performantes aux solutions rapides.",
        "intent": "VECTOR",
    },
    {
        "user_input": "Pourquoi as-tu choisi l'informatique ?",
        "reference": "Il est passionné d'informatique et de tous ses aspects qui mettent en jeu la logique, le raisonnement poussé et les défis en tout genre. Il est passionné par l'interface entre la logique humaine et la logique machine.",
        "intent": "VECTOR",
    },
    {
        "user_input": "Quelles sont tes qualités professionnelles ?",
        "reference": "Il est logique, curieux et déterminé. Il aime comprendre le fonctionnement des systèmes complexes et trouver des solutions élégantes. Son approche repose sur la rigueur, la planification et la remise en question constante.",
        "intent": "VECTOR",
    },
    {
        "user_input": "Que valorises-tu dans le travail d'équipe ?",
        "reference": "Il valorise la collaboration et le partage de connaissances. Chaque projet est une opportunité d'apprendre et de s'améliorer.",
        "intent": "VECTOR",
    },
    {
        "user_input": "Quels sont tes objectifs de carrière ?",
        "reference": "Il souhaite devenir gestionnaire de projet TI et développer ses compétences en gestion d'équipes, planification et coordination de projets technologiques. Il prévoit des certifications PMP et ITIL. Il garde une vision à long terme sans s'éloigner du volet technique.",
        "intent": "VECTOR",
    },

    # ═══════════════════════════════════════════════════════════════
    # SQL — Questions factuelles / structurées
    # ═══════════════════════════════════════════════════════════════
    {
        "user_input": "Combien de projets as-tu réalisés ?",
        "reference": "Il a réalisé plusieurs projets dont une application de gestion de dépenses, une application de gestion d'épicerie et un CV interactif sous forme de chatbot IA.",
        "intent": "SQL",
    },
    {
        "user_input": "Quel diplôme as-tu obtenu ?",
        "reference": "Il a obtenu un DEC en Techniques de l'informatique au Cégep de Chicoutimi.",
        "intent": "SQL",
    },
    {
        "user_input": "As-tu de l'expérience en Python ?",
        "reference": "Oui, il développe en Python avec Django et FastAPI.",
        "intent": "SQL",
    },
    {
        "user_input": "Tu connais React ?",
        "reference": "Oui, il utilise React dans ses projets, notamment pour le développement frontend.",
        "intent": "SQL",
    },
    {
        "user_input": "Quelles technologies maîtrises-tu ?",
        "reference": "Il maîtrise C#, .NET, WPF, MVVM, ASP.NET Core, Python, Django, FastAPI, et développe des chatbots basés sur l'IA.",
        "intent": "SQL",
    },
    {
        "user_input": "As-tu de l'expérience en C# ?",
        "reference": "Oui, il maîtrise le développement en C#, .NET et WPF avec le modèle MVVM pour concevoir des interfaces structurées et maintenables.",
        "intent": "SQL",
    },
    {
        "user_input": "Tu as un portfolio ?",
        "reference": "Oui, il a élaboré non seulement un portfolio déployé mais aussi CV interactif sous forme de chatbot alimenté par un modèle d'IA, conçu pour simuler un entretien en ligne et permettre à un employeur de découvrir ses compétences plus aisément.",
        "intent": "SQL",
    },

    # ═══════════════════════════════════════════════════════════════
    # VECTOR_SQL — Questions hybrides
    # ═══════════════════════════════════════════════════════════════
    {
        "user_input": "Décris ton projet le plus avancé en IA",
        "reference": "Son projet le plus avancé en IA est son chatbot CV intelligent, un système RAG complet utilisant FastAPI, PostgreSQL avec pgvector, Voyage AI pour les embeddings et Claude comme LLM. Il est déployé en production.",
        "intent": "VECTOR_SQL",
    },
    {
        "user_input": "Parle-moi de tes projets en C#",
        "reference": "Il a conçu une application de gestion de projets avec des amis en C# avec WPF/MVVM, ainsi qu'une application WPF de gestion d'épicerie complète et prête à être utilisée en situation réelle.",
        "intent": "VECTOR_SQL",
    },
    {
        "user_input": "Quel est ton meilleur projet et pourquoi ?",
        "reference": "Son meilleur projet est le chatbot CV intelligent, un système RAG avec FastAPI, PostgreSQL, pgvector, Voyage AI et Claude. Il l'a conçu pour démontrer ses compétences techniques et donner la possibilité à un employeur d'avoir un aperçu du type d'employé qu'il peut être.",
        "intent": "VECTOR_SQL",
    },
    {
        "user_input": "Explique ton expérience en développement web",
        "reference": "Il conçoit des applications web avec ASP.NET Core, et React avec des interfaces assez intuitives et immersives. Il développe aussi avec Django et FastAPI côté backend Python.",
        "intent": "VECTOR_SQL",
    },

    # ═══════════════════════════════════════════════════════════════
    # OFF_TOPIC — Questions hors contexte
    # ═══════════════════════════════════════════════════════════════
    {
        "user_input": "Donne-moi une recette de gâteau au chocolat",
        "reference": "Cette question est hors du contexte professionnel du chatbot CV. Le chatbot devrait rediriger poliment vers le profil professionnel.",
        "intent": "OFF_TOPIC",
    },
    {
        "user_input": "Quelle est ta couleur préférée ?",
        "reference": "Le chatbot ne répond pas aux questions personnelles non liées au profil professionnel. Il préfère garder ses réponses centrées sur le parcours professionnel et les compétences.",
        "intent": "OFF_TOPIC",
    },
    {
        "user_input": "Que penses-tu du président ?",
        "reference": "Le chatbot ne prend pas position sur des sujets politiques, religieux ou personnels. Son objectif est de représenter le profil professionnel.",
        "intent": "OFF_TOPIC",
    },

    # ═══════════════════════════════════════════════════════════════
    # Questions de suivi / reformulation
    # ═══════════════════════════════════════════════════════════════
    {
        "user_input": "Comment gères-tu les défis techniques ?",
        "reference": "Il croit qu'un bon développeur ne se limite pas à écrire du code : il comprend surtout le besoin, structure la solution et anticipe les erreurs possibles. Il aime comprendre le fonctionnement des systèmes complexes et trouver des solutions élégantes.",
        "intent": "VECTOR",
    },
    {
        "user_input": "Tu fais de la documentation ?",
        "reference": "Oui, il a développé un intérêt pour la documentation technique claire et structurée, afin de rendre chaque projet transmissible et durable. Il est à l'aise avec les outils comme la suite Microsoft office.",
        "intent": "VECTOR",
    },
    {
        "user_input": "Combien d'heures par semaine consacres-tu à ta formation ?",
        "reference": "Il consacre actuellement une dizaine d'heures par semaine à sa montée en compétences, notamment en suivant des formations en ligne dans le domaine des TI et même de la gestion de projets.",
        "intent": "SQL",
    },
    {
        "user_input": "Tu préfères Windows ou Linux pour développer ?",
        "reference": "Le chatbot peut répondre à cette question car elle est liée aux préférences techniques. Il devrait partager son avis sur ses outils et environnements de développement préférés.",
        "intent": "VECTOR",
    },
    {
        "user_input": "Es-tu travailleur ?",
        "reference": "Oui, son approche du travail repose sur la rigueur, la planification et la remise en question constante de ses méthodes pour les améliorer. Il consacre une beaucoup de temps à sa montée en compétences.",
        "intent": "VECTOR",
    },
]
