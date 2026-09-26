"""
isittho — auth module

Three ways to get an account, all producing the same thing: a row in
`users` and a JWT the app attaches to every other request.

  - Email + password (bcrypt hashed, never stored in plain text)
  - Sign in with Apple (verifies Apple's identity token against Apple's
    public keys — no password, no email required from Apple's side)
  - Sign in with Google (same idea, verified via google-auth)

None of this makes submission content less anonymous to OTHER users —
similar_submissions never includes any user info. This is purely
internal: demographics, abuse prevention, and a hook for subscriptions
later.
"""

import os
import time
from datetime import datetime, timedelta, timezone

import jwt
import requests
import bcrypt
import resend
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests

JWT_SECRET = os.environ.get("JWT_SECRET")
JWT_ALGORITHM = "HS256"
JWT_EXPIRES_DAYS = 90

bearer_scheme = HTTPBearer()

# The app should deep-link this into its reset-password screen, passing
# the token along (e.g. isittho://reset-password?token=...). Set this to
# your actual app scheme/domain once the app side is wired up.
RESET_LINK_BASE = os.environ.get("PASSWORD_RESET_LINK_BASE", "https://isittho.co/reset-password")


def send_password_reset_email(to_email: str, token: str):
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        # Fails loudly in logs rather than silently pretending an email
        # was sent — worth noticing during setup, not in production use.
        print(f"WARNING: RESEND_API_KEY not set — reset email to {to_email} not sent. Token: {token}")
        return

    resend.api_key = api_key
    reset_url = f"{RESET_LINK_BASE}?token={token}"
    resend.Emails.send({
        "from": os.environ.get("RESEND_FROM_EMAIL", "isittho <noreply@isittho.co>"),
        "to": to_email,
        "subject": "Reset your isittho password",
        "html": (
            f"<p>Someone requested a password reset for your isittho account.</p>"
            f"<p><a href='{reset_url}'>Reset your password</a></p>"
            f"<p>This link expires in 1 hour. If you didn't request this, you can ignore this email.</p>"
        ),
    })

# Apple's public keys, cached and refreshed occasionally rather than
# fetched on every request.
_apple_keys_cache = {"keys": None, "fetched_at": 0}
APPLE_KEYS_URL = "https://appleid.apple.com/auth/keys"
APPLE_ISSUER = "https://appleid.apple.com"


def require_jwt_secret():
    if not JWT_SECRET:
        raise HTTPException(status_code=500, detail="JWT_SECRET not set on server")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def issue_token(user_id: int) -> str:
    require_jwt_secret()
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRES_DAYS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> int:
    """FastAPI dependency — attach with `user_id: int = Depends(get_current_user_id)`
    on any endpoint that should require a signed-in user."""
    require_jwt_secret()
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return int(payload["sub"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired — please sign in again")
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")


def _get_apple_public_keys():
    now = time.time()
    if _apple_keys_cache["keys"] is None or now - _apple_keys_cache["fetched_at"] > 3600:
        resp = requests.get(APPLE_KEYS_URL, timeout=10)
        resp.raise_for_status()
        _apple_keys_cache["keys"] = resp.json()["keys"]
        _apple_keys_cache["fetched_at"] = now
    return _apple_keys_cache["keys"]


def verify_apple_identity_token(identity_token: str, expected_audience: str) -> str:
    """Verifies an Apple identity token and returns the Apple `sub`
    (a stable, unique id for that person, not their real email/name)."""
    try:
        header = jwt.get_unverified_header(identity_token)
        keys = _get_apple_public_keys()
        matching_key = next((k for k in keys if k["kid"] == header["kid"]), None)
        if not matching_key:
            raise HTTPException(status_code=401, detail="Apple token: no matching key")

        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(matching_key)
        payload = jwt.decode(
            identity_token,
            public_key,
            algorithms=["RS256"],
            audience=expected_audience,
            issuer=APPLE_ISSUER,
        )
        return payload["sub"]
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid Apple token: {e}")


def verify_google_identity_token(identity_token: str, expected_audience: str) -> str:
    """Verifies a Google identity token and returns the Google `sub`."""
    try:
        payload = google_id_token.verify_oauth2_token(
            identity_token, google_requests.Request(), expected_audience
        )
        return payload["sub"]
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid Google token: {e}")
