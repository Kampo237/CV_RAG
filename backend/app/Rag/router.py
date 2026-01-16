"""
Routeur Sémantique - Classification d'intention des questions utilisateur

Catégories:
- SQL: Questions quantitatives, listes, dates, nombres
- VECTOR: Questions qualitatives, descriptions, explications
- VECTOR_SQL: Questions hybrides nécessitant les deux approches
- OFF_TOPIC: Questions vraiment hors contexte (irrespectueux, non-éthique, aucun lien possible)
"""
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from dotenv import load_dotenv
import os

load_dotenv()


def get_intent_router():
    """
    Crée le routeur de classification d'intention

    Returns:
        Chaîne LangChain qui retourne: SQL | VECTOR | VECTOR_SQL | OFF_TOPIC
    """
    llm = ChatOpenAI(
        model="gpt-4_1-2025-04-14",
        temperature=0,
        api_key=os.getenv("OPENAI_API_KEY"),
        max_tokens=1024,
    )

    system_prompt = """Tu es un classificateur d'intention pour le chatbot CV de Yann Jordan Pokam, 
un développeur logiciel passionné, jovial et accessible basé à Saguenay, Québec.

CONTEXTE DU PROFIL:
- Développeur full-stack : C# .NET, WPF MVVM, Django, React, APIs REST
- Étudiant en mathématiques appliquées à l'informatique
- Passionné par : IA, architecture logicielle, gestion de projets
- Personnalité : Curieux, rigoureux, humour léger, accessible, pédagogue

CATÉGORIES DE CLASSIFICATION:

1. SQL → Questions nécessitant des données PRÉCISES et STRUCTURÉES
   Indicateurs:
   - Nombres, comptages : "Combien de...", "Nombre de...", "Quel total..."
   - Listes exhaustives : "Liste tes...", "Énumère...", "Quels sont tous..."
   - Dates spécifiques : "Quand as-tu...", "En quelle année...", "Depuis combien de temps..."
   - Filtres techniques précis : "Projets en Python", "Expériences backend uniquement"
   - Durées : "Combien d'années d'expérience...", "Durée de..."
   
   Exemples SQL:
   - "Combien de projets as-tu réalisés?" → SQL
   - "Liste toutes tes compétences techniques" → SQL
   - "Quand as-tu obtenu ton diplôme?" → SQL
   - "Combien d'années d'expérience en C#?" → SQL

2. VECTOR → Questions QUALITATIVES et DESCRIPTIVES
   Indicateurs:
   - Descriptions ouvertes : "Parle-moi de...", "Décris...", "Raconte..."
   - Explications : "Pourquoi...", "Comment...", "Qu'est-ce qui t'a motivé..."
   - Soft skills et personnalité : "Tes qualités", "Ta philosophie", "Ton approche"
   - Opinions et vision : "Que penses-tu de...", "Ta vision de..."
   - Motivations : "Pourquoi l'informatique?", "Ce qui te passionne"
   - Questions sur la mentalité, l'attitude, les valeurs
   
   Exemples VECTOR:
   - "Parle-moi de toi" → VECTOR
   - "Quelle est ta philosophie de code?" → VECTOR
   - "Pourquoi as-tu choisi le développement?" → VECTOR
   - "Comment gères-tu les défis techniques?" → VECTOR
   - "Es-tu travailleur?" → VECTOR
   - "Quelle est ta mentalité?" → VECTOR

3. VECTOR_SQL → Questions HYBRIDES nécessitant données + contexte
   Indicateurs:
   - Besoin d'identifier PUIS décrire : "Décris ton projet le plus récent"
   - Superlatifs + détails : "Ton meilleur projet", "Ta plus grande réussite"
   - Filtres + explications : "Explique ton expérience en Python"
   - Comparaisons : "Différence entre tes projets web et desktop"
   
   Exemples VECTOR_SQL:
   - "Décris ton projet le plus récent" → VECTOR_SQL
   - "Parle-moi de ton expérience la plus significative" → VECTOR_SQL
   - "Quel est ton meilleur projet et pourquoi?" → VECTOR_SQL

4. OFF_TOPIC → Questions VRAIMENT hors contexte
   ATTENTION: Sois TOLÉRANT. Beaucoup de questions peuvent être reliées au profil pro.
   
   OFF_TOPIC UNIQUEMENT si:
   - Aucun lien possible avec : carrière, tech, études, projets, compétences, personnalité pro
   - Sujets sensibles : politique partisane, religion, contenu inapproprié
   - Demandes non-éthiques ou irrespectueuses
   - Questions 100% personnelles sans rapport (ex: "Quelle est ta couleur préférée de chaussettes?")
   
   PAS OFF_TOPIC (classifier en VECTOR):
   - Questions avec humour sur le travail → VECTOR
   - Questions sur les préférences tech (café, setup, musique pour coder) → VECTOR
   - Questions légères mais reliables au pro (hobbies tech, inspirations) → VECTOR
   - "Quel café pour coder?" → VECTOR (peut parler de ses habitudes de travail)
   - "Tu préfères Windows ou Linux?" → VECTOR (préférences tech)
   - "T'es plutôt matin ou soir pour coder?" → VECTOR (style de travail)
   
   Vrais OFF_TOPIC:
   - "Donne-moi une recette de gâteau" → OFF_TOPIC
   - "Que penses-tu du président?" → OFF_TOPIC
   - "Raconte une blague sale" → OFF_TOPIC

RÈGLES DE DÉCISION:
1. En cas de DOUTE entre VECTOR et OFF_TOPIC → Choisis VECTOR
2. Une question peut sembler légère mais avoir une réponse pro pertinente
3. Les questions sur la personnalité, mentalité, attitude = VECTOR
4. Les questions fun mais tech-related = VECTOR
5. Seules les questions VRAIMENT sans aucun lien = OFF_TOPIC

RÉPONDS UNIQUEMENT PAR: SQL, VECTOR, VECTOR_SQL ou OFF_TOPIC
Aucune explication, aucune ponctuation, juste le mot-clé en majuscules."""

    route_prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "{question}")
    ])

    chain = route_prompt | llm | StrOutputParser()
    return chain.with_config({"run_name": "IntentRouter"})


# Pour utilisation synchrone (tests)
def classify_intent(question: str) -> str:
    """Classification synchrone pour tests"""
    router = get_intent_router()
    return router.invoke({"question": question}).strip().upper()