"""auth.tokens 与密码哈希的单元测试。"""

import os
import time

import pytest

from battery_materials_agent.auth.tokens import issue_token, verify_token
from battery_materials_agent.auth.user_store import (
    hash_password,
    is_legacy_hash,
    verify_password,
)


@pytest.fixture(autouse=True)
def _fixed_secret(monkeypatch):
    """测试使用固定密钥，避免进程随机密钥干扰。"""
    monkeypatch.setenv("AUTH_TOKEN_SECRET", "test-secret-key")


class TestTokens:
    def test_issue_and_verify_roundtrip(self):
        token = issue_token("U-ABCD1234")
        assert verify_token(token) == "U-ABCD1234"

    def test_tampered_user_id_rejected(self):
        token = issue_token("U-ABCD1234")
        _, expires, sig = token.split(".")
        forged = f"U-ADMIN999.{expires}.{sig}"
        assert verify_token(forged) is None

    def test_tampered_signature_rejected(self):
        token = issue_token("U-ABCD1234")
        uid, expires, _ = token.split(".")
        forged = f"{uid}.{expires}.{'0' * 64}"
        assert verify_token(forged) is None

    def test_expired_token_rejected(self, monkeypatch):
        monkeypatch.setenv("AUTH_TOKEN_TTL_SECONDS", "-1")
        token = issue_token("U-ABCD1234")
        assert verify_token(token) is None

    def test_malformed_tokens_rejected(self):
        assert verify_token("") is None
        assert verify_token("abc") is None
        assert verify_token("a.b") is None
        assert verify_token("a.b.c.d") is None
        assert verify_token("U-X.notanint." + "0" * 64) is None

    def test_wrong_secret_rejected(self, monkeypatch):
        token = issue_token("U-ABCD1234")
        monkeypatch.setenv("AUTH_TOKEN_SECRET", "another-secret")
        assert verify_token(token) is None


class TestPasswordHashing:
    def test_pbkdf2_roundtrip(self):
        stored = hash_password("s3cret")
        assert stored.startswith("pbkdf2$")
        assert verify_password("s3cret", stored) is True
        assert verify_password("wrong", stored) is False

    def test_salt_randomized(self):
        assert hash_password("same") != hash_password("same")

    def test_legacy_sha256_still_verifies(self):
        # 旧格式 '{salt}${sha256(salt:password)}'
        import hashlib

        salt = "abcd1234"
        digest = hashlib.sha256(f"{salt}:pw".encode()).hexdigest()
        stored = f"{salt}${digest}"
        assert is_legacy_hash(stored) is True
        assert verify_password("pw", stored) is True
        assert verify_password("nope", stored) is False

    def test_new_format_not_legacy(self):
        assert is_legacy_hash(hash_password("x")) is False

    def test_malformed_hash_rejected(self):
        assert verify_password("x", "") is False
        assert verify_password("x", "no-dollar-sign") is False
        assert verify_password("x", "pbkdf2$notanint$salt$digest") is False
