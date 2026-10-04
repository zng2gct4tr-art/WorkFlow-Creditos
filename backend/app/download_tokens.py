import base64, hashlib, hmac, json, os, time
from fastapi import HTTPException


def secret():
    return os.getenv(
        "SESSION_SECRET", "development-only-session-pepper-change-before-production"
    ).encode()


def token_for(document, user, session_id, ttl=120):
    payload = {
        "document": document,
        "user": user,
        "session": session_id,
        "expires": int(time.time()) + min(ttl, 300),
    }
    encoded = (
        base64.urlsafe_b64encode(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        )
        .decode()
        .rstrip("=")
    )
    signature = hmac.new(secret(), encoded.encode(), hashlib.sha256).hexdigest()
    return encoded + "." + signature


def verify_token(token, document, user, session_id):
    try:
        encoded, signature = token.split(".")
        if not hmac.compare_digest(
            signature, hmac.new(secret(), encoded.encode(), hashlib.sha256).hexdigest()
        ):
            raise ValueError()
        payload = json.loads(
            base64.urlsafe_b64decode(encoded + "=" * ((-len(encoded)) % 4))
        )
        if (
            payload["document"] != document
            or payload["user"] != user
            or payload["session"] != session_id
            or payload["expires"] <= time.time()
        ):
            raise ValueError()
    except (ValueError, KeyError, TypeError):
        raise HTTPException(
            403,
            "El acceso temporal al documento venció o no corresponde a esta sesión.",
        )
