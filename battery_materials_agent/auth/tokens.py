"""服务端签名认证 token（HMAC-SHA256，含过期时间）。

格式：``{user_id}.{expires_at_unix}.{hmac_hex}``

密钥来源：环境变量 ``AUTH_TOKEN_SECRET``。未设置时使用进程级随机密钥
（所有 token 在服务重启后失效）并输出醒目告警；生产环境必须显式配置。
有效期：环境变量 ``AUTH_TOKEN_TTL_SECONDS``，默认 12 小时。
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time

logger = logging.getLogger(__name__)

_DEFAULT_TTL_SECONDS = 12 * 3600

_fallback_secret: bytes | None = None


def _secret() -> bytes:
    global _fallback_secret
    configured = os.getenv("AUTH_TOKEN_SECRET", "")
    if configured:
        return configured.encode("utf-8")
    if os.getenv("RUN_MODE", "demo").lower() == "production":
        raise RuntimeError(
            "RUN_MODE=production 时必须通过环境变量 AUTH_TOKEN_SECRET "
            "显式设置签名密钥，禁止使用进程级随机密钥（重启后所有登录态失效）。"
        )
    if _fallback_secret is None:
        _fallback_secret = secrets.token_bytes(32)
        logger.warning(
            "AUTH_TOKEN_SECRET 未设置：已生成进程级随机密钥，所有登录态将在服务重启后失效。"
            "生产环境请务必配置 AUTH_TOKEN_SECRET。"
        )
    return _fallback_secret


def _ttl_seconds() -> int:
    try:
        return int(os.getenv("AUTH_TOKEN_TTL_SECONDS", str(_DEFAULT_TTL_SECONDS)))
    except ValueError:
        return _DEFAULT_TTL_SECONDS


def issue_token(user_id: str) -> str:
    """为指定用户签发带签名与过期时间的 token。"""
    expires = int(time.time()) + _ttl_seconds()
    payload = f"{user_id}.{expires}"
    sig = hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def verify_token(token: str) -> str | None:
    """校验 token 签名与有效期，合法则返回 user_id，否则返回 None。

    token 格式：{user_id}.{expires}.{hmac}，用 rsplit 拆分后两段，
    user_id 允许包含点号（兼容邮箱/OIDC sub 等格式）。
    """
    if not token:
        return None
    parts = token.rsplit(".", 2)
    if len(parts) != 3:
        return None
    user_id, expires_s, sig = parts
    payload = f"{user_id}.{expires_s}"
    expected = hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    try:
        expires = int(expires_s)
    except ValueError:
        logger.warning("Token expires_s not integer: %s", expires_s[:20])
        return None
    if expires < int(time.time()):
        return None
    return user_id
