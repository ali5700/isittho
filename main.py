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
import uuid
from collections import Counter
from typing import Optional

import psycopg
import voyageai
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

import auth

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


GENDERS = {"woman", "man", "non-binary", "prefer not to say"}
RELATIONSHIP_STATUSES = {
    "single", "dating", "in a relationship", "engaged", "married",
    "separated", "divorced", "it's complicated",
}


class SignupRequest(BaseModel):
    email: str
    password: str = Field(..., min_length=8)
    exact_age: int = Field(..., ge=13, le=120)
    gender: str
    relationship_status: str


class LoginRequest(BaseModel):
    email: str
    password: str


class SocialSignInRequest(BaseModel):
    identity_token: str = Field(..., description="The token returned by Apple/Google's native sign-in SDK")
    client_id: str = Field(..., description="Your app's bundle ID (Apple) or OAuth client ID (Google)")
    # Only needed the first time this person signs in — ignored on
    # subsequent logins once the account already has these on file.
    exact_age: Optional[int] = Field(None, ge=13, le=120)
    gender: Optional[str] = None
    relationship_status: Optional[str] = None


class AuthResponse(BaseModel):
    token: str
    user_id: int
    is_new_account: bool


def _validate_profile_fields(gender: str, relationship_status: str):
    if gender not in GENDERS:
        raise HTTPException(status_code=400, detail=f"gender must be one of {sorted(GENDERS)}")
    if relationship_status not in RELATIONSHIP_STATUSES:
        raise HTTPException(status_code=400, detail=f"relationship_status must be one of {sorted(RELATIONSHIP_STATUSES)}")


@app.post("/auth/signup", response_model=AuthResponse)
def signup(request: SignupRequest):
    _validate_profile_fields(request.gender, request.relationship_status)
    password_hash = auth.hash_password(request.password)

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM users WHERE email = %s", (request.email,))
                if cur.fetchone():
                    raise HTTPException(status_code=409, detail="An account with this email already exists")

                cur.execute(
                    """
                    INSERT INTO users (email, password_hash, exact_age, gender, relationship_status)
                    VALUES (%s, %s, %s, %s, %s) RETURNING id
                    """,
                    (request.email, password_hash, request.exact_age, request.gender, request.relationship_status),
                )
                user_id = cur.fetchone()[0]
            conn.commit()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Signup failed: {e}")

    return AuthResponse(token=auth.issue_token(user_id), user_id=user_id, is_new_account=True)


@app.post("/auth/login", response_model=AuthResponse)
def login(request: LoginRequest):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, password_hash FROM users WHERE email = %s", (request.email,))
                row = cur.fetchone()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Login failed: {e}")

    if not row or not row[1] or not auth.verify_password(request.password, row[1]):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    return AuthResponse(token=auth.issue_token(row[0]), user_id=row[0], is_new_account=False)


def _social_sign_in(sub: str, provider_column: str, request: SocialSignInRequest):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT id FROM users WHERE {provider_column} = %s", (sub,))
                row = cur.fetchone()

                if row:
                    return AuthResponse(token=auth.issue_token(row[0]), user_id=row[0], is_new_account=False)

                # New account — profile fields are required on first sign-in.
                if not (request.exact_age and request.gender and request.relationship_status):
                    raise HTTPException(
                        status_code=400,
                        detail="First-time sign-in requires exact_age, gender, and relationship_status",
                    )
                _validate_profile_fields(request.gender, request.relationship_status)

                cur.execute(
                    f"""
                    INSERT INTO users ({provider_column}, exact_age, gender, relationship_status)
                    VALUES (%s, %s, %s, %s) RETURNING id
                    """,
                    (sub, request.exact_age, request.gender, request.relationship_status),
                )
                user_id = cur.fetchone()[0]
            conn.commit()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Sign-in failed: {e}")

    return AuthResponse(token=auth.issue_token(user_id), user_id=user_id, is_new_account=True)


@app.post("/auth/apple", response_model=AuthResponse)
def apple_sign_in(request: SocialSignInRequest):
    sub = auth.verify_apple_identity_token(request.identity_token, request.client_id)
    return _social_sign_in(sub, "apple_sub", request)


@app.post("/auth/google", response_model=AuthResponse)
def google_sign_in(request: SocialSignInRequest):
    sub = auth.verify_google_identity_token(request.identity_token, request.client_id)
    return _social_sign_in(sub, "google_sub", request)


# Google's OAuth "Web application" client type requires a real HTTPS
# redirect URI (custom app schemes like isittho:// are rejected outright).
# This page exists purely so Google has somewhere to send the browser back
# to — expo-auth-session intercepts that navigation (URL, fragment and
# all) at the WebView/browser level before this page's own script would
# even run, so the redirect below is just a courtesy fallback for anyone
# who ends up here outside of that in-app auth flow.
@app.get("/auth/google-redirect", response_class=HTMLResponse)
def google_auth_redirect():
    return """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Signing in…</title></head>
<body style="font-family: -apple-system, sans-serif; text-align: center; padding-top: 80px; color: #111827;">
  <p>Signing you in…</p>
  <p style="color: #6B7280; font-size: 14px;">You can close this window if it doesn't return automatically.</p>
  <script>
    var hash = new URLSearchParams(window.location.hash.substring(1));
    var query = new URLSearchParams(window.location.search);
    var merged = new URLSearchParams();
    query.forEach(function (v, k) { merged.set(k, v); });
    hash.forEach(function (v, k) { merged.set(k, v); });
    window.location.replace("isittho://google-auth-callback?" + merged.toString());
  </script>
</body>
</html>"""


class UpdateProfileRequest(BaseModel):
    exact_age: Optional[int] = Field(None, ge=13, le=120)
    gender: Optional[str] = None
    relationship_status: Optional[str] = None


class UpdateProfileResponse(BaseModel):
    exact_age: Optional[int]
    gender: Optional[str]
    relationship_status: Optional[str]


@app.patch("/account", response_model=UpdateProfileResponse)
def update_profile(request: UpdateProfileRequest, user_id: int = Depends(auth.get_current_user_id)):
    """Updates only the fields provided — anything left as null is unchanged."""
    if request.gender is not None and request.gender not in GENDERS:
        raise HTTPException(status_code=400, detail=f"gender must be one of {sorted(GENDERS)}")
    if request.relationship_status is not None and request.relationship_status not in RELATIONSHIP_STATUSES:
        raise HTTPException(status_code=400, detail=f"relationship_status must be one of {sorted(RELATIONSHIP_STATUSES)}")

    updates = request.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided to update")

    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [user_id]

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE users SET {set_clause} WHERE id = %s "
                    "RETURNING exact_age, gender, relationship_status",
                    values,
                )
                row = cur.fetchone()
            conn.commit()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Update failed: {e}")

    if not row:
        raise HTTPException(status_code=404, detail="Account not found")

    return UpdateProfileResponse(exact_age=row[0], gender=row[1], relationship_status=row[2])


@app.delete("/account")
def delete_account(user_id: int = Depends(auth.get_current_user_id)):
    """Deletes the account. Submissions stay (they're already anonymous —
    no text tied to identity is ever shown to other users) but their
    user_id link is cleared, so nothing connects them to this person
    anymore."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE submissions SET user_id = NULL WHERE user_id = %s", (user_id,))
                cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
            conn.commit()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Delete failed: {e}")

    return {"message": "Account deleted."}


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8)


@app.post("/auth/forgot-password")
def forgot_password(request: ForgotPasswordRequest):
    """Always returns the same generic message, whether or not the email
    exists — this avoids leaking which emails have accounts."""
    generic_response = {"message": "If an account exists for that email, a reset link has been sent."}

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM users WHERE email = %s", (request.email,))
                row = cur.fetchone()
                if not row:
                    return generic_response

                user_id = row[0]
                token = uuid.uuid4().hex
                cur.execute(
                    """
                    INSERT INTO password_reset_tokens (token, user_id, expires_at)
                    VALUES (%s, %s, now() + interval '1 hour')
                    """,
                    (token, user_id),
                )
            conn.commit()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Request failed: {e}")

    auth.send_password_reset_email(request.email, token)
    return generic_response


@app.post("/auth/reset-password")
def reset_password(request: ResetPasswordRequest):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT user_id FROM password_reset_tokens
                    WHERE token = %s AND used = false AND expires_at > now()
                    """,
                    (request.token,),
                )
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=400, detail="Invalid or expired reset link")

                user_id = row[0]
                password_hash = auth.hash_password(request.new_password)
                cur.execute("UPDATE users SET password_hash = %s WHERE id = %s", (password_hash, user_id))
                cur.execute("UPDATE password_reset_tokens SET used = true WHERE token = %s", (request.token,))
            conn.commit()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Reset failed: {e}")

    return {"message": "Password updated. You can now log in with your new password."}


# Categories where a red_flag result should surface support resources
# rather than just a stats breakdown. This is a coarse, keyword-level
# starting point — not a substitute for real moderation/classification
# work before this handles real user submissions.
SENSITIVE_CATEGORIES = {"sex and intimacy", "jealousy and trust"}

# Independent backstop: nearest-neighbor majority vote is matching on
# phrasing similarity, not severity, so it can miss genuinely concerning
# content when similar-sounding examples in the dataset happen to be
# labeled less severely. Any of these phrases forces the support-resources
# flag on regardless of what the vote says. Deliberately broad/imperfect —
# false positives here (showing a resource someone didn't need) are a much
# smaller cost than false negatives.
SAFETY_KEYWORDS = [
    "hit me", "hits me", "hitting me", "grabbed my", "grabbed me",
    "pushed me", "shoved me", "choked me", "strangled", "punched",
    "slapped", "threw me", "threw something at me", "afraid of him",
    "afraid of her", "scared of him", "scared of her", "scared he'll",
    "scared she'll", "threatened to hurt", "threatened me", "won't let me leave",
    "locked me in", "locked me out", "took my phone away", "controls my money",
    "forced me", "force me", "hurt me", "hurts me", "bruise", "bruises",
]


def contains_safety_keyword(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in SAFETY_KEYWORDS)


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
    check_id: str
    query: str
    similar_submissions: list[SimilarSubmission]
    verdict_breakdown: dict
    top_label: str
    needs_support_resources: bool


class ConfirmSubmitRequest(BaseModel):
    check_id: str = Field(..., description="The check_id returned by a prior /check call")


class ConfirmSubmitResponse(BaseModel):
    id: int
    needs_support_resources: bool
    message: str


class SubmitRequest(BaseModel):
    text: str = Field(..., min_length=10, max_length=2000, description="The situation to submit")
    category: Optional[str] = Field(None, description="One of the known categories; inferred from similar submissions if omitted")


class SubmitResponse(BaseModel):
    id: int
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


MOODS = {"good", "neutral", "rough"}


class CheckinRequest(BaseModel):
    mood: str = Field(..., description="One of: good, neutral, rough")
    note: Optional[str] = Field(None, max_length=500)


class CheckinResponse(BaseModel):
    id: int
    mood: str
    note: Optional[str]
    checkin_date: str
    streak: int


class CheckinHistoryEntry(BaseModel):
    mood: str
    note: Optional[str]
    checkin_date: str


def _compute_streak(cur, user_id: int) -> int:
    """Consecutive days ending today (or yesterday, so missing *today's*
    entry doesn't zero out a real streak while there's still time to log it)."""
    cur.execute(
        "SELECT checkin_date FROM mood_checkins WHERE user_id = %s ORDER BY checkin_date DESC",
        (user_id,),
    )
    dates = [row[0] for row in cur.fetchall()]
    if not dates:
        return 0

    from datetime import date, timedelta
    today = date.today()
    streak = 0
    expected = today if dates[0] == today else today - timedelta(days=1)
    for d in dates:
        if d == expected:
            streak += 1
            expected -= timedelta(days=1)
        elif d < expected:
            break
    return streak


@app.post("/checkins", response_model=CheckinResponse)
def log_checkin(request: CheckinRequest, user_id: int = Depends(auth.get_current_user_id)):
    """Logs (or updates) today's mood check-in. One per user per day —
    submitting again today overwrites today's entry rather than
    duplicating it."""
    if request.mood not in MOODS:
        raise HTTPException(status_code=400, detail=f"mood must be one of {sorted(MOODS)}")

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO mood_checkins (user_id, mood, note, checkin_date)
                    VALUES (%s, %s, %s, CURRENT_DATE)
                    ON CONFLICT (user_id, checkin_date)
                    DO UPDATE SET mood = EXCLUDED.mood, note = EXCLUDED.note
                    RETURNING id, mood, note, checkin_date
                    """,
                    (user_id, request.mood, request.note),
                )
                row = cur.fetchone()
                streak = _compute_streak(cur, user_id)
            conn.commit()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Check-in failed: {e}")

    return CheckinResponse(
        id=row[0], mood=row[1], note=row[2], checkin_date=str(row[3]), streak=streak,
    )


@app.get("/checkins/history", response_model=list[CheckinHistoryEntry])
def checkin_history(days: int = 30, user_id: int = Depends(auth.get_current_user_id)):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT mood, note, checkin_date FROM mood_checkins
                    WHERE user_id = %s AND checkin_date >= CURRENT_DATE - %s::int
                    ORDER BY checkin_date DESC
                    """,
                    (user_id, days),
                )
                rows = cur.fetchall()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"History fetch failed: {e}")

    return [CheckinHistoryEntry(mood=r[0], note=r[1], checkin_date=str(r[2])) for r in rows]


@app.get("/checkins/streak")
def checkin_streak(user_id: int = Depends(auth.get_current_user_id)):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                streak = _compute_streak(cur, user_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Streak fetch failed: {e}")

    return {"streak": streak}


@app.get("/health")
def health():
    return {"status": "ok"}



@app.post("/check", response_model=CheckResponse)
def check_situation(request: CheckRequest, user_id: int = Depends(auth.get_current_user_id)):
    embedding, rows = find_similar(request.text, input_type="query")

    if not rows:
        raise HTTPException(status_code=404, detail="No submissions in database yet")

    labels, similar, top_label, top_categories = compute_verdict(rows)

    # Flag for support resources if the top result is a red flag AND it
    # falls in a sensitive category, OR the text itself contains explicit
    # safety-keyword language — this second check catches cases the
    # similarity vote misses (see contains_safety_keyword docstring above).
    needs_support = (
        (top_label == "red_flag" and bool(top_categories & SENSITIVE_CATEGORIES))
        or contains_safety_keyword(request.text)
    )

    inferred_category = similar[0].category if similar else "communication"
    stored_label = "red_flag" if needs_support else top_label
    check_id = str(uuid.uuid4())

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO pending_checks
                        (id, text, category, outcome_label, needs_support_resources, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (check_id, request.text, inferred_category, stored_label, needs_support, embedding),
                )
            conn.commit()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Database insert failed: {e}")

    return CheckResponse(
        check_id=check_id,
        query=request.text,
        similar_submissions=similar,
        verdict_breakdown=dict(labels),
        top_label=top_label,
        needs_support_resources=needs_support,
    )


@app.post("/confirm_submit", response_model=ConfirmSubmitResponse)
def confirm_submit(request: ConfirmSubmitRequest, user_id: int = Depends(auth.get_current_user_id)):
    """Redeems a check_id from a prior /check call, adding that same text
    to the submissions pool without re-embedding or asking the person to
    retype anything. This is the "Add to the pool?" follow-up shown after
    a Check result."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT text, category, outcome_label, needs_support_resources, embedding
                    FROM pending_checks WHERE id = %s
                    """,
                    (request.check_id,),
                )
                row = cur.fetchone()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Database query failed: {e}")

    if not row:
        raise HTTPException(
            status_code=404,
            detail="check_id not found or expired — run /check again before confirming",
        )

    text, category, outcome_label, needs_support, embedding = row
    visible = not needs_support

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO submissions
                        (text, category, outcome_label, label_is_provisional,
                         visible, source, embedding, user_id)
                    VALUES (%s, %s, %s, true, %s, 'user', %s, %s)
                    RETURNING id
                    """,
                    (text, category, outcome_label, visible, embedding, user_id),
                )
                new_id = cur.fetchone()[0]
                # One-time use — remove the pending row now that it's redeemed.
                cur.execute("DELETE FROM pending_checks WHERE id = %s", (request.check_id,))
            conn.commit()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Database insert failed: {e}")

    message = (
        "Thanks for sharing. This situation touches on something sensitive, "
        "so it'll be reviewed before appearing in others' results."
        if needs_support else
        "Thanks for sharing — this is now part of the pool other people will see."
    )

    return ConfirmSubmitResponse(
        id=new_id,
        needs_support_resources=needs_support,
        message=message,
    )


@app.post("/submit", response_model=SubmitResponse)
def submit_situation(request: SubmitRequest, user_id: int = Depends(auth.get_current_user_id)):
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
        needs_support = (
            (top_label == "red_flag" and bool(top_categories & SENSITIVE_CATEGORIES))
            or contains_safety_keyword(request.text)
        )
    else:
        # Empty database edge case — store as an unlabeled yellow_flag
        # rather than failing the submission outright.
        top_label = "yellow_flag"
        inferred_category = request.category or "communication"
        needs_support = contains_safety_keyword(request.text)

    if request.category and request.category not in CATEGORIES:
        raise HTTPException(status_code=400, detail=f"category must be one of {CATEGORIES}")

    if needs_support:
        top_label = "red_flag"

    visible = not needs_support

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO submissions
                        (text, category, outcome_label, label_is_provisional,
                         visible, source, embedding, user_id)
                    VALUES (%s, %s, %s, true, %s, 'user', %s, %s)
                    RETURNING id
                    """,
                    (request.text, inferred_category, top_label, visible, embedding, user_id),
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
        needs_support_resources=needs_support,
        message=message,
    )
