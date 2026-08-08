"""OIDC 企业 SSO 认证（A2）。

流程：授权码模式
1. ``GET /auth/sso/login`` → 重定向到 IdP authorize 端点（携带 state）
2. IdP 认证后回调 ``/auth/sso/callback``，携带 code + state
3. 用 code 换 token（token_endpoint），从 ID token/claims 提取用户身份
4. JIT 开户：按 ``external_idp_id``（sub）幂等映射本地用户，首登自动创建

依赖：httpx（项目已使用）。未配置 SSO（enabled=False）时，api.py 不注册路由。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
import urllib.parse

from ..config import SSOConfig

logger = logging.getLogger(__name__)


def _state_secret() -> bytes:
    """state 签名密钥（进程级，重启后失效；生产建议配置 AUTH_TOKEN_SECRET 复用）。"""
    import os
    configured = os.getenv("AUTH_TOKEN_SECRET", "")
    if configured:
        return configured.encode("utf-8")
    return b"insecure-sso-state"


def make_state(payload: str) -> str:
    """生成带 HMAC 签名的 state，防止 CSRF。格式 {payload}.{expires}.{sig}。"""
    expires = int(time.time()) + 600  # 10 分钟有效
    body = f"{payload}.{expires}"
    sig = hmac.new(_state_secret(), body.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def verify_state(state: str) -> str | None:
    """校验 state 签名与有效期，合法返回 payload，否则 None。"""
    if not state:
        return None
    parts = state.rsplit(".", 2)
    if len(parts) != 3:
        return None
    payload, expires_s, sig = parts
    expected = hmac.new(_state_secret(), f"{payload}.{expires_s}".encode("utf-8"),
                        hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    try:
        if int(expires_s) < int(time.time()):
            return None
    except ValueError:
        return None
    return payload


def _discover(cfg: SSOConfig) -> dict:
    """从 issuer 发现 OIDC 端点。失败抛异常。"""
    import httpx
    discovery_url = cfg.issuer.rstrip("/") + "/.well-known/openid-configuration"
    resp = httpx.get(discovery_url, timeout=10.0)
    resp.raise_for_status()
    return resp.json()


def _cached_discovery(cfg: SSOConfig) -> dict:
    """带简单缓存的 OIDC 发现（60 秒）。"""
    import time as _t
    key = cfg.issuer
    entry = _discovery_cache.get(key)
    if entry and entry[0] > _t.monotonic():
        return entry[1]
    data = _discover(cfg)
    _discovery_cache[key] = (_t.monotonic() + 60, data)
    return data


_discovery_cache: dict[str, tuple[float, dict]] = {}


def build_auth_url(cfg: SSOConfig, state: str) -> str:
    """构造重定向到 IdP 的授权 URL。"""
    meta = _cached_discovery(cfg)
    auth_endpoint = meta.get("authorization_endpoint")
    if not auth_endpoint:
        raise RuntimeError(f"OIDC issuer {cfg.issuer} 未提供 authorization_endpoint")
    params = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": cfg.client_id,
        "redirect_uri": cfg.redirect_uri,
        "scope": cfg.scope,
        "state": state,
    })
    return f"{auth_endpoint}?{params}"


def _decode_part(part: str) -> dict:
    """解码 JWT 段（base64url → JSON）。"""
    pad = part + "=" * (-len(part) % 4)
    raw = base64.urlsafe_b64decode(pad)
    return json.loads(raw)


def _extract_claims(cfg: SSOConfig, token_resp: dict) -> dict:
    """从 token 响应提取用户 claims（优先 ID token，其次 userinfo 或 access 解析）。"""
    id_token = token_resp.get("id_token")
    if id_token:
        try:
            return _decode_part(id_token.split(".")[1])
        except Exception as e:
            logger.warning("ID token 解析失败：%s", e)
    if token_resp.get("access_token"):
        # 部分 IdP 把身份信息编码在 access token（JWT）
        try:
            return _decode_part(token_resp["access_token"].split(".")[1])
        except Exception:
            pass
    return {}


def exchange_code(cfg: SSOConfig, code: str) -> dict:
    """用授权码换取 token。返回 token 响应 dict。"""
    import httpx
    meta = _cached_discovery(cfg)
    token_endpoint = meta.get("token_endpoint")
    if not token_endpoint:
        raise RuntimeError(f"OIDC issuer {cfg.issuer} 未提供 token_endpoint")
    resp = httpx.post(
        token_endpoint,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": cfg.redirect_uri,
            "client_id": cfg.client_id,
            "client_secret": cfg.client_secret,
        },
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()


def claims_to_identity(claims: dict) -> dict:
    """从 claims 提取规范化身份字段。"""
    return {
        "sub": claims.get("sub") or "",
        "email": claims.get("email") or "",
        "username": claims.get("preferred_username")
                   or claims.get("email") or claims.get("sub") or "",
        "display_name": claims.get("name") or claims.get("email") or "",
    }


def provision_user(user_store, cfg: SSOConfig, identity: dict, auth_source: str = "oidc"):
    """JIT 开户：按 external_idp_id 幂等返回本地用户，首登自动创建。

    返回 (user, created: bool)。auth_source 用于区分 oidc / ldap。
    """
    sub = identity["sub"]
    if not sub:
        raise ValueError("SSO claims 缺少 sub，无法建立账户映射")
    existing = user_store.get_by_external_idp(sub)
    if existing is not None:
        return existing, False

    from .user_store import User, UserRole
    user = User(
        username=identity["username"] or f"sso_{sub[:8]}",
        display_name=identity["display_name"] or identity["username"],
        email=identity["email"],
        role=UserRole(cfg.default_role or "viewer"),
        project_ids=[],
        is_active=True,
        tenant_id=cfg.default_tenant or "default",
        auth_source=auth_source,
        external_idp_id=sub,
        password_hash="",  # SSO/LDAP 用户无本地密码
    )
    user_store.save(user)
    logger.info("%s JIT 开户：external_idp_id=%s username=%s",
                auth_source.upper(), sub, user.username)
    return user, True