"""
isittho — API backend

Wraps the same clustering logic proven out in query_similar.py into a
real HTTP API, so a future frontend (web, mobile) can call it instead of
running a script by hand.

Setup (same env vars as before):
    export VOYAGE_API_KEY=...
    export DATABASE_URL=postgresql://isittho:isittho_dev_password@localhost:5432/isittho

    pip install fastapi uvicorn

Run locally:
    uvicorn main:app --reload

Then visit http://localhost:8000/docs for an interactive API tester —
FastAPI generates this automatically from the code below.
"""

import os
from collections import Counter
from typing import Optional

import psycopg
import voyageai
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

EMBED_MODEL = "voyage-3"
TOP_K = 10

app = FastAPI(title="isittho API", version="0.1")

# Allows a frontend running on a different port/domain (e.g. localhost:3000)
# to call this API during development. Tighten this to your real domain
# before going to production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_voyage_client: Optional[voyageai.Client] = None


def get_voyage_client():
    global _voyage_client
    if _voyage_client is None:
        key = os.environ.get("VOYAGE_API_KEY")
        if not key:
            raise HTTPException(status_code=500, detail="VOYAGE_API_KEY not set on server")
        _voyage_client = voyageai.Client(api_key=key)
    return _voyage_client


def get_db_connection():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise HTTPException(status_code=500, detail="DATABASE_URL not set on server")
    return psycopg.connect(database_url)


# Categories where a red_flag result should surface support resources
# rather than just a stats breakdown. This is a coarse, keyword-level
# starting point — not a substitute for real moderation/classification
# work before this handles real user submissions.
SENSITIVE_CATEGORIES = {"sex and intimacy", "jealousy and trust"}


class CheckRequest(BaseModel):
    text: str = Field(..., min_length=10, max_length=2000, description="The situation to check")


class SimilarSubmission(BaseModel):
    text_preview: str
    category: str
    outcome_label: str
    similarity: float


class CheckResponse(BaseModel):
    query: str
    similar_submissions: list[SimilarSubmission]
    verdict_breakdown: dict
    top_label: str
    needs_support_resources: bool


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/check", response_model=CheckResponse)
def check_situation(request: CheckRequest):
    vo_client = get_voyage_client()

    try:
        result = vo_client.embed([request.text], model=EMBED_MODEL, input_type="query")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Embedding request failed: {e}")

    query_embedding = result.embeddings[0]

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT text, category, outcome_label,
                           1 - (embedding <=> %s::vector) AS similarity
                    FROM submissions
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (query_embedding, query_embedding, TOP_K),
                )
                rows = cur.fetchall()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Database query failed: {e}")

    if not rows:
        raise HTTPException(status_code=404, detail="No submissions in database yet")

    labels = Counter()
    similar = []
    for text, category, label, similarity in rows:
        labels[label] += 1
        preview = text[:200] + ("..." if len(text) > 200 else "")
        similar.append(
            SimilarSubmission(
                text_preview=preview,
                category=category,
                outcome_label=label,
                similarity=round(similarity, 3),
            )
        )

    top_label, top_count = labels.most_common(1)[0]

    # Flag for support resources if the top result is a red flag AND it
    # falls in a sensitive category. This is intentionally conservative
    # and coarse — refine before handling real user submissions.
    top_categories = {s.category for s in similar[:3]}
    needs_support = top_label == "red_flag" and bool(top_categories & SENSITIVE_CATEGORIES)

    return CheckResponse(
        query=request.text,
        similar_submissions=similar,
        verdict_breakdown=dict(labels),
        top_label=top_label,
        needs_support_resources=needs_support,
    )
