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


CATEGORIES = [
    "finances", "jealousy and trust", "in-laws and family",
    "communication", "boundaries and privacy", "long-distance",
    "chores and labor", "new relationship pacing", "breakup grey areas",
    "sex and intimacy", "friendships outside the relationship",
]


class CheckRequest(BaseModel):
    text: str = Field(..., min_length=10, max_length=2000, description="The situation to check")


class SimilarSubmission(BaseModel):
    text: str
    category: str
    outcome_label: str
    similarity: float


class CheckResponse(BaseModel):
    query: str
    similar_submissions: list[SimilarSubmission]
    verdict_breakdown: dict
    top_label: str
    needs_support_resources: bool


class SubmitRequest(BaseModel):
    text: str = Field(..., min_length=10, max_length=2000, description="The situation to submit")
    category: Optional[str] = Field(None, description="One of the known categories; inferred from similar submissions if omitted")


class SubmitResponse(BaseModel):
    id: int
    category: str
    provisional_label: str
    visible: bool
    needs_support_resources: bool
    message: str


def find_similar(text: str, input_type: str = "query"):
    """Embed text and return (embedding, rows) of the TOP_K nearest visible
    submissions. Shared by /check and /submit so both use identical logic."""
    vo_client = get_voyage_client()
    try:
        result = vo_client.embed([text], model=EMBED_MODEL, input_type=input_type)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Embedding request failed: {e}")

    embedding = result.embeddings[0]

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT text, category, outcome_label,
                           1 - (embedding <=> %s::vector) AS similarity
                    FROM submissions
                    WHERE visible = true
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (embedding, embedding, TOP_K),
                )
                rows = cur.fetchall()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Database query failed: {e}")

    return embedding, rows


def compute_verdict(rows):
    """Given (text, category, label, similarity) rows, return the label
    counts, a formatted similar_submissions list, the top label, and the
    top 3 categories (used for the safety-flag check)."""
    labels = Counter()
    similar = []
    for text, category, label, similarity in rows:
        labels[label] += 1
        similar.append(
            SimilarSubmission(
                text=text,
                category=category,
                outcome_label=label,
                similarity=round(similarity, 3),
            )
        )
    top_label, _ = labels.most_common(1)[0]
    top_categories = {s.category for s in similar[:3]}
    return labels, similar, top_label, top_categories


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/check", response_model=CheckResponse)
def check_situation(request: CheckRequest):
    _, rows = find_similar(request.text, input_type="query")

    if not rows:
        raise HTTPException(status_code=404, detail="No submissions in database yet")

    labels, similar, top_label, top_categories = compute_verdict(rows)

    # Flag for support resources if the top result is a red flag AND it
    # falls in a sensitive category. This is intentionally conservative
    # and coarse — refine before handling real user submissions.
    needs_support = top_label == "red_flag" and bool(top_categories & SENSITIVE_CATEGORIES)

    return CheckResponse(
        query=request.text,
        similar_submissions=similar,
        verdict_breakdown=dict(labels),
        top_label=top_label,
        needs_support_resources=needs_support,
    )


@app.post("/submit", response_model=SubmitResponse)
def submit_situation(request: SubmitRequest):
    """Adds a real user's situation to the database.

    A provisional label and category are derived from nearest existing
    submissions at write time (the same logic /check uses), since a
    submitter can't reliably self-label their own situation. Anything
    that looks sensitive (red flag in a sensitive category) is stored
    with visible=false — held out of other users' clustering results
    until a human reviews it, so one concerning post can't immediately
    distort what everyone else sees.
    """
    # input_type="document" here since this text is being stored, not
    # just searched — matches how the seed data was embedded.
    embedding, rows = find_similar(request.text, input_type="document")

    if rows:
        labels, similar, top_label, top_categories = compute_verdict(rows)
        inferred_category = request.category or similar[0].category
        needs_support = top_label == "red_flag" and bool(top_categories & SENSITIVE_CATEGORIES)
    else:
        # Empty database edge case — store as an unlabeled yellow_flag
        # rather than failing the submission outright.
        top_label = "yellow_flag"
        inferred_category = request.category or "communication"
        needs_support = False

    if request.category and request.category not in CATEGORIES:
        raise HTTPException(status_code=400, detail=f"category must be one of {CATEGORIES}")

    visible = not needs_support

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO submissions
                        (text, category, outcome_label, label_is_provisional,
                         visible, source, embedding)
                    VALUES (%s, %s, %s, true, %s, 'user', %s)
                    RETURNING id
                    """,
                    (request.text, inferred_category, top_label, visible, embedding),
                )
                new_id = cur.fetchone()[0]
            conn.commit()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Database insert failed: {e}")

    message = (
        "Thanks for sharing. This situation touches on something sensitive, "
        "so it'll be reviewed before appearing in others' results."
        if needs_support else
        "Thanks for sharing — this is now part of the pool other people will see."
    )

    return SubmitResponse(
        id=new_id,
        category=inferred_category,
        provisional_label=top_label,
        visible=visible,
        needs_support_resources=needs_support,
        message=message,
    )
