import hmac
import hashlib
import os

_SECRET = os.environ.get('SECRET_KEY', '').encode()


def _sign(email: str) -> str:
    return hmac.new(_SECRET, email.lower().encode(), hashlib.sha256).hexdigest()


def signed_url(base_url: str, email: str, path: str) -> str:
    token = _sign(email)
    return f"{base_url}{path}?email={email}&token={token}"


def verify(email: str, token: str) -> bool:
    if not email or not token:
        return False
    expected = _sign(email)
    return hmac.compare_digest(expected, token)
