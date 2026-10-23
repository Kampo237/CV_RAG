"""
Évaluation RAGAS — qualité des réponses du chat, tel qu'il tourne en production.

Complète app/evaluation/run_scenarios.py (comportements) par une note de
qualité : fidélité au contexte, rappel du contexte, exactitude factuelle.

Pour chaque question de test_dataset.py :
  1. le routeur décide comme en production : chemin rapide (Haiku) ou agent (Sonnet 5) ;
  2. on garde la réponse ET le contexte réellement donné au modèle
     (données de la base pour le chemin rapide, résultats d'outils pour l'agent) ;
  3. RAGAS note le tout avec un juge Claude Opus 5 — un autre modèle que ceux
     évalués, pour éviter qu'un modèle note ses propres réponses.

Usage :
    python -m app.evaluation.run_baseline              # tout le jeu (≈ quelques dollars de juge)
    python -m app.evaluation.run_baseline --limit 3    # essai rapide

Rien n'est écrit dans chat_sessions ; aucun message n'est envoyé.
Résultats : app/evaluation/results/ragas_<horodatage>.csv et _scores.json
"""
import os
import re
import sys
import csv
import json
import asyncio
import logging
from collections import defaultdict
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()  # avant tout import LangChain
logging.disable(logging.CRITICAL)

from app.Rag import fast_path  # noqa: E402
from app.Rag.agent import run_rag_agent  # noqa: E402
from app.evaluation.test_dataset import TEST_DATASET  # noqa: E402

JUDGE_MODEL = os.getenv("RAGAS_JUDGE_MODEL", "claude-opus-5")
GUIDE_LINE = re.compile(r"\[\[guide\]\].*$", re.S)


# ═══════════════════════════════════════════════════════════════
# 1. Réponse et contexte, comme en production
# ═══════════════════════════════════════════════════════════════

async def answer_like_production(question: str) -> dict:
    """Route la question comme /chat/ (sans historique) et renvoie réponse, contexte et chemin."""
    route = await fast_path.route_question(question)
    if route:
        captured: dict = {}
        original = fast_path._stream_llm

        async def spy(q, data, history, nav_hint):
            # Contexte réellement vu par Haiku : résumé du portfolio + données de la route
            captured["context"] = f"{await fast_path.portfolio_brief()}\n\n{data}"
            async for token in original(q, data, history, nav_hint):
                yield token

        fast_path._stream_llm = spy
        try:
            fast = await fast_path.prepare_fast_answer(route, question, [], {})
        finally:
            fast_path._stream_llm = original
        if fast:
            text = "".join([token async for token in fast.stream])
            text = GUIDE_LINE.sub("", text).strip()
            # Réponse fixe (CV, langues…) : construite depuis la base, elle est son propre contexte
            return {"answer": text, "context": captured.get("context") or text, "path": "rapide", "route": fast.label}

    result = await run_rag_agent(question=question, session_id="eval-ragas", history=[])
    return {"answer": result.get("answer", ""), "context": result.get("context", ""), "path": "agent", "route": "agent"}


async def collect(dataset: list[dict]) -> list[dict]:
    rows = []
    for i, sample in enumerate(dataset, 1):
        q = sample["user_input"]
        print(f"[{i}/{len(dataset)}] {q}")
        try:
            out = await answer_like_production(q)
        except Exception as e:
            out = {"answer": f"[ERREUR : {type(e).__name__}: {e}]", "context": "", "path": "erreur", "route": "erreur"}
        flag = "" if out["path"] == sample.get("path") else f"  (chemin attendu : {sample.get('path')})"
        print(f"      → {out['path']} [{out['route']}]{flag} : {out['answer'][:90]}")
        rows.append({
            "user_input": q,
            "response": out["answer"],
            "retrieved_contexts": [out["context"]] if out["context"] else [],
            "reference": sample["reference"],
            "theme": sample.get("theme", ""),
            "path_expected": sample.get("path", ""),
            "path": out["path"],
            "route": out["route"],
        })
    return rows


# ═══════════════════════════════════════════════════════════════
# 2. Notation RAGAS (juge Claude Opus 5)
# ═══════════════════════════════════════════════════════════════

def judge_llm():
    from langchain_anthropic import ChatAnthropic
    from ragas.llms import LangchainLLMWrapper

    llm = ChatAnthropic(
        model_name=JUDGE_MODEL,
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        max_tokens=8000,
        # Repli côté serveur si les classifieurs de sécurité refusent une requête de notation
        betas=["server-side-fallback-2026-07-01"],
        # Opus 5 refuse temperature ; effort bas pour un juge (coût, latence)
        model_kwargs={"extra_body": {"output_config": {"effort": "low"}, "fallbacks": "default"}},
    )
    # bypass_* : RAGAS n'envoie ni temperature ni n (refusés par ce modèle)
    return LangchainLLMWrapper(llm, bypass_temperature=True, bypass_n=True)


def score(rows: list[dict]) -> list[dict]:
    from ragas import EvaluationDataset, evaluate
    from ragas.metrics import Faithfulness, FactualCorrectness, LLMContextRecall

    dataset = EvaluationDataset.from_list([
        {k: r[k] for k in ("user_input", "response", "retrieved_contexts", "reference")} for r in rows
    ])
    print(f"\n🔬 Notation RAGAS (juge : {JUDGE_MODEL})…")
    result = evaluate(dataset=dataset, metrics=[Faithfulness(), LLMContextRecall(), FactualCorrectness()],
                      llm=judge_llm(), show_progress=True)
    df = result.to_pandas()
    metric_cols = [c for c in df.columns if c not in ("user_input", "response", "retrieved_contexts", "reference")]
    for row, (_, scores) in zip(rows, df[metric_cols].iterrows()):
        row["scores"] = {c: (None if scores[c] != scores[c] else round(float(scores[c]), 4)) for c in metric_cols}
    return rows


def summarize(rows: list[dict]) -> dict:
    def mean(values):
        values = [v for v in values if v is not None]
        return round(sum(values) / len(values), 4) if values else None

    metrics = sorted({m for r in rows for m in r.get("scores", {})})
    groups = {"global": rows}
    for key in ("path", "theme"):
        for r in rows:
            groups.setdefault(f"{key}:{r[key]}", []).append(r)
    summary = {name: {m: mean([r["scores"].get(m) for r in group]) for m in metrics} | {"n": len(group)}
               for name, group in groups.items()}
    summary["routage_attendu"] = round(sum(r["path"] == r["path_expected"] for r in rows) / len(rows), 4)
    return summary


# ═══════════════════════════════════════════════════════════════
# 3. Sauvegarde
# ═══════════════════════════════════════════════════════════════

def save(rows: list[dict], summary: dict) -> None:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(os.path.dirname(__file__), "results")
    os.makedirs(out_dir, exist_ok=True)
    csv_path = os.path.join(out_dir, f"ragas_{stamp}.csv")
    metrics = sorted({m for r in rows for m in r.get("scores", {})})
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["user_input", "theme", "path_expected", "path", "route", *metrics, "response", "reference"])
        for r in rows:
            writer.writerow([r["user_input"], r["theme"], r["path_expected"], r["path"], r["route"],
                             *[r.get("scores", {}).get(m) for m in metrics], r["response"], r["reference"]])
    json_path = os.path.join(out_dir, f"ragas_{stamp}_scores.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"timestamp": stamp, "judge": JUDGE_MODEL, "num_questions": len(rows), "summary": summary},
                  f, indent=2, ensure_ascii=False)
    print(f"\n📁 {csv_path}\n📁 {json_path}")


async def main() -> None:
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    dataset = TEST_DATASET[:limit] if limit else TEST_DATASET
    print(f"🚀 Évaluation RAGAS — {len(dataset)} questions, pipeline de production, juge {JUDGE_MODEL}\n")
    rows = score(await collect(dataset))
    summary = summarize(rows)
    print("\n📊 Scores")
    for name in ("global", "path:rapide", "path:agent"):
        if name in summary:
            print(f"   {name:<12} " + "  ".join(f"{k}={v}" for k, v in summary[name].items()))
    print(f"   routage conforme à l'attendu : {summary['routage_attendu']:.0%}")
    save(rows, summary)


if __name__ == "__main__":
    asyncio.run(main())
