import time

import jwt
import pytest

from app.auth.passwords import hash_password, verify_password
from app.auth.tokens import TokenError, create_access_token, decode_access_token
from app.core.config import get_settings


def test_hash_password_is_not_the_plaintext():
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert hashed.startswith("$argon2")


def test_verify_password_accepts_the_right_password():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed) is True


def test_verify_password_rejects_the_wrong_password():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("wrong password", hashed) is False


def test_access_token_round_trips_the_user_id():
    token = create_access_token("user-123")
    assert decode_access_token(token) == "user-123"


def test_access_token_rejects_a_tampered_signature():
    token = create_access_token("user-123")
    tampered = token[:-4] + "abcd"
    with pytest.raises(TokenError):
        decode_access_token(tampered)


def test_access_token_rejects_expiry(monkeypatch):
    settings = get_settings()
    payload = {"sub": "user-123", "iat": time.time() - 120, "exp": time.time() - 60}
    expired_token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    with pytest.raises(TokenError):
        decode_access_token(expired_token)


def test_access_token_rejects_a_missing_sub_claim():
    settings = get_settings()
    payload = {"iat": time.time(), "exp": time.time() + 60}
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    with pytest.raises(TokenError):
        decode_access_token(token)
