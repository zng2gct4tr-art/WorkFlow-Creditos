"""Configurable, transparent rubric. Automated signals are not analyst judgments."""

import re
from .models import Setting, now
from fastapi import HTTPException

KEYS = {
    "completeness",
    "coherence",
    "analysis",
    "financial_consistency",
    "risk_identification",
    "clarity",
}


def weights(db):
    s = db.get(Setting, "rubric")
    return (
        s.value
        if s
        else {
            "completeness": 20,
            "coherence": 20,
            "analysis": 20,
            "financial_consistency": 20,
            "risk_identification": 10,
            "clarity": 10,
        }
    )


def aggregate(scores, rubric):
    return round(sum(scores.get(k, 0) * w for k, w in rubric.items()) / 100, 2)


def automatic_assessment(db, content, client):
    text = content.lower()
    fields = ["empresa", "solicitud", "financ", "riesgo", "conclusi"]
    metrics = {
        "completeness": sum(term in text for term in fields) / len(fields) * 100,
        "coherence": 70 if len(content.strip()) >= 300 else 30,
        "analysis": sum(
            term in text for term in ["ebitda", "capacidad", "flujo", "deuda"]
        )
        / 4
        * 100,
        "financial_consistency": sum(
            client.financials.get(k) is not None
            for k in ["revenue", "ebitda", "total_debt"]
        )
        / 3
        * 100,
        "risk_identification": sum(
            term in text for term in ["riesgo", "garant", "mitiga"]
        )
        / 3
        * 100,
        "clarity": 100 if len(content.split()) >= 50 and "\n" in content else 40,
    }
    rubric = weights(db)
    return {
        "kind": "automatic",
        "score": aggregate(metrics, rubric),
        "scores": metrics,
        "weights": rubric,
        "explanation": "Señales estructurales y de información disponible. No evalúan veracidad, coherencia semántica ni suficiencia crediticia; requieren evaluación humana.",
        "evaluated_at": now().isoformat(),
    }


def human_assessment(db, scores, actor):
    if (
        set(scores) - KEYS
        or set(scores) != set(weights(db))
        or any(
            not isinstance(v, (int, float)) or isinstance(v, bool) or not 0 <= v <= 100
            for v in scores.values()
        )
    ):
        raise HTTPException(
            422, "Califique cada dimensión de la rúbrica entre 0 y 100."
        )
    rubric = weights(db)
    return {
        "kind": "human",
        "scores": scores,
        "score": aggregate(scores, rubric),
        "weights": rubric,
        "evaluator_id": actor.id,
        "evaluated_at": now().isoformat(),
    }
