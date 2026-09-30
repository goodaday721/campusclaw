"""JWT issuing and verification (HS256) for the Bearer-token auth scheme.

The token is only a tamper-proof envelope for the user id: the payload holds
``sub`` (user id), ``jti`` (session id registered server-side), ``iat`` and
``exp``. Role and class are NEVER embedded — they are read from the users
table on every request so that database changes take effect immediately.
"""
import uuid
from datetime import datetime, timedelta, timezone

import jwt


class TokenInvalid(Exception):
    """Raised when a token is malformed, tampered with or expired."""


def issue(config, user_id: int) -> tuple[str, str, datetime]:
    """Issue a signed JWT.

    Returns ``(token, jti, expires_at)``; ``jti``/``expires_at`` must be
    persisted in the sessions table so the token can be revoked.
    """
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=config.session_ttl_hours)
    jti = uuid.uuid4().hex
    payload = {
        "sub": str(user_id),
        "jti": jti,
        "iat": now,
        "exp": expires_at,
    }
    token = jwt.encode(payload, config.jwt_secret, algorithm="HS256")
    return token, jti, expires_at


def verify(config, token: str) -> dict:
    """Verify signature and expiry; return the payload dict.

    Raises TokenInvalid for any malformed, tampered, or expired token.
    """
    try:
        return jwt.decode(
            token,
            config.jwt_secret,
            algorithms=["HS256"],
            options={"require": ["exp", "sub", "jti"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenInvalid(str(exc)) from exc
