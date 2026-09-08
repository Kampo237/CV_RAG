"""
Script d'évaluation RAGAS — Baseline du pipeline RAG actuel.

Ce script :
1. Charge le dataset de test (test_dataset.py)
2. Exécute chaque question dans le pipeline RAG complet (run_rag_graph)
3. Génère la réponse via la chaîne de génération
4. Évalue le tout avec les métriques RAGAS
5. Sauvegarde les résultats dans un CSV

Usage :
    cd FastAPIProject
    python -m app.evaluation.run_baseline
"""

import asyncio
import json
import os
import sys
import csv
import time
from datetime import datetime
from dotenv import load_dotenv

# Charger le .env AVANT tout import LangChain
load_dotenv()

from app.Rag.graph import run_rag_graph
from app.Rag.agent import run_rag_agent
from app.Rag.generation import generate_response
from app.evaluation.test_dataset import TEST_DATASET


# ═══════════════════════════════════════════════════════════════
# ÉTAPE 1 — Exécuter le pipeline RAG pour chaque question
# ═══════════════════════════════════════════════════════════════

async def run_pipeline_on_question(question: str) -> dict:
    """
    Exécute le pipeline RAG complet et retourne :
      - context  : le contexte récupéré (ce que le LLM voit)
      - answer   : la réponse générée (tokens concaténés)
      - intent   : l'intent détecté par le routeur
    """
    # Étape A — LangGraph (rephrase → route → retrieve → synthesize)
    final_state = await run_rag_agent(
        question=question,
        session_id="eval-baseline",
        history=[],  # Pas d'historique pour l'évaluation
    )

    context = final_state.get("context", "")
    intent = final_state.get("intent", "UNKNOWN")

    # Étape B — Génération (collecter tous les tokens du stream)
    answer = final_state.get("answer", "")

    return {
        "context": context,
        "answer": answer,
        "intent": intent,
    }


async def collect_pipeline_results() -> list[dict]:
    """
    Exécute le pipeline sur toutes les questions du dataset.
    Retourne une liste de dicts prêts pour RAGAS.
    """
    results = []
    total = len(TEST_DATASET)

    for i, sample in enumerate(TEST_DATASET):
        question = sample["user_input"]
        print(f"\n[{i+1}/{total}] Question : {question[:60]}...")

        try:
            pipeline_result = await run_pipeline_on_question(question)

            results.append({
                "user_input": question,
                "response": pipeline_result["answer"],
                "retrieved_contexts": [pipeline_result["context"]] if pipeline_result["context"] else [],
                "reference": sample["reference"],
                # Métadonnées (pas utilisées par RAGAS mais utiles pour l'analyse)
                "_intent_expected": sample["intent"],
                "_intent_actual": pipeline_result["intent"],
            })

            intent_match = "✅" if sample["intent"] == pipeline_result["intent"] else "❌"
            print(f"         Intent : {pipeline_result['intent']} {intent_match}")
            print(f"         Réponse : {pipeline_result['answer'][:80]}...")

        except Exception as e:
            print(f"         ❌ ERREUR : {e}")
            results.append({
                "user_input": question,
                "response": f"[ERREUR: {e}]",
                "retrieved_contexts": [],
                "reference": sample["reference"],
                "_intent_expected": sample["intent"],
                "_intent_actual": "ERROR",
            })

    return results


# ═══════════════════════════════════════════════════════════════
# ÉTAPE 2 — Évaluation RAGAS
# ═══════════════════════════════════════════════════════════════

def run_ragas_evaluation(results: list[dict]) -> dict:
    """
    Lance l'évaluation RAGAS sur les résultats collectés.

    Métriques utilisées :
      - Faithfulness     : la réponse est-elle fidèle au contexte récupéré ?
      - LLMContextRecall : le retrieval a-t-il trouvé les bonnes informations ?
      - FactualCorrectness : la réponse est-elle factuellement correcte ?
    """
    from ragas import EvaluationDataset, evaluate
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import LLMContextRecall, Faithfulness, FactualCorrectness
    from langchain_openai import ChatOpenAI

    # Préparer les données au format RAGAS
    # On retire les métadonnées internes (_intent_*)
    ragas_data = [
        {
            "user_input": r["user_input"],
            "response": r["response"],
            "retrieved_contexts": r["retrieved_contexts"],
            "reference": r["reference"],
        }
        for r in results
    ]

    # Créer le dataset RAGAS
    eval_dataset = EvaluationDataset.from_list(ragas_data)

    # LLM évaluateur (on utilise OpenAI pour éviter le biais
    # d'évaluer Claude avec Claude)
    evaluator_llm = LangchainLLMWrapper(
        ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0,
            api_key=os.getenv("OPENAI_API_KEY"),
        )
    )

    # Métriques
    metrics = [
        Faithfulness(),
        LLMContextRecall(),
        FactualCorrectness(),
    ]

    print("\n" + "=" * 60)
    print("🔬 Lancement de l'évaluation RAGAS...")
    print("=" * 60)

    # Lancer l'évaluation
    result = evaluate(
        dataset=eval_dataset,
        metrics=metrics,
        llm=evaluator_llm,
    )

    df = result.to_pandas()
    scores = {}
    for col in df.columns:
        if col not in ("user_input", "response", "retrieved_contexts", "reference"):
            try:
                scores[col] = float(df[col].mean())
            except (TypeError, ValueError):
                pass
    print(f"\n📊 Scores RAGAS :")
    for metric, score in scores.items():
        print(f"   {metric:30s} : {score:.4f}")
    return scores


# ═══════════════════════════════════════════════════════════════
# ÉTAPE 3 — Sauvegarde des résultats
# ═══════════════════════════════════════════════════════════════

def save_results(results: list[dict], ragas_scores: dict, label: str = "baseline"):
    """Sauvegarde les résultats dans un CSV horodaté."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join(os.path.dirname(__file__), "results")
    os.makedirs(output_dir, exist_ok=True)

    # CSV détaillé par question
    csv_path = os.path.join(output_dir, f"{label}_{timestamp}.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "user_input", "response", "reference",
            "retrieved_contexts", "_intent_expected", "_intent_actual",
        ])
        writer.writeheader()
        for r in results:
            row = r.copy()
            row["retrieved_contexts"] = json.dumps(row["retrieved_contexts"], ensure_ascii=False)[:500]
            writer.writerow(row)

    # Scores globaux
    scores_path = os.path.join(output_dir, f"{label}_{timestamp}_scores.json")
    with open(scores_path, "w", encoding="utf-8") as f:
        json.dump({
            "label": label,
            "timestamp": timestamp,
            "num_questions": len(results),
            "scores": {k: round(v, 4) if isinstance(v, float) else v for k, v in ragas_scores.items()},
            "intent_accuracy": sum(
                1 for r in results if r["_intent_expected"] == r["_intent_actual"]
            ) / len(results),
        }, f, indent=2, ensure_ascii=False)

    print(f"\n📁 Résultats sauvegardés :")
    print(f"   CSV détaillé : {csv_path}")
    print(f"   Scores       : {scores_path}")

    return csv_path, scores_path


# ═══════════════════════════════════════════════════════════════
# POINT D'ENTRÉE
# ═══════════════════════════════════════════════════════════════

async def main():
    print("=" * 60)
    print("🚀 ÉVALUATION RAGAS — BASELINE")
    print(f"   {len(TEST_DATASET)} questions de test")
    print(f"   Pipeline : LangGraph StateGraph (agent)")
    print("=" * 60)

    # Étape 1 — Exécuter le pipeline
    results = await collect_pipeline_results()

    # Résumé des intents
    intent_correct = sum(1 for r in results if r["_intent_expected"] == r["_intent_actual"])
    print(f"\n📊 Précision du routeur : {intent_correct}/{len(results)} ({intent_correct/len(results)*100:.0f}%)")

    # Étape 2 — Évaluation RAGAS
    try:
        ragas_result = run_ragas_evaluation(results)
        print("   (scores affichés ci-dessus)")
    except Exception as e:
        print(f"\n❌ Erreur RAGAS : {e}")
        print("   (vérifie que ragas et datasets sont installés : pip install ragas datasets)")
        ragas_result = {"error": str(e)}

    # Étape 3 — Sauvegarde
    save_results(results, ragas_result, label="baseline_automate")

    print("\n✅ Évaluation baseline terminée !")


if __name__ == "__main__":
    asyncio.run(main())
