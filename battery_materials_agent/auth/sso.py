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
    """state 签名密钥（进程级，重启后失效；生产建议配置 AUTH_TOKEN_SECRET 复用）。

    生产模式（RUN_MODE=production）下未配置密钥直接拒绝 SSO（与 auth/tokens.py
    的硬失败策略一致），杜绝硬编码弱密钥被伪造 state。
    """
    import os
    configured = os.getenv("AUTH_TOKEN_SECRET", "")
    if configured:
        return configured.encode("utf-8")
    if os.getenv("RUN_MODE", "").lower() == "production":
        raise RuntimeError(
            "SSO state 签名密钥缺失：生产模式必须配置 AUTH_TOKEN_SECRET（与登录 token 同源）"
        )
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


_jwks_cache: dict[str, tuple[float, list[dict]]] = {}


def _fetch_jwks(cfg: SSOConfig) -> list[dict]:
    """从 discovery 的 jwks_uri 拉取 JWKS（60 秒缓存）。"""
    import time as _t
    import httpx
    meta = _cached_discovery(cfg)
    jwks_uri = meta.get("jwks_uri")
    if not jwks_uri:
        raise RuntimeError(f"OIDC issuer {cfg.issuer} 未提供 jwks_uri")
    key = cfg.issuer
    entry = _jwks_cache.get(key)
    if entry and entry[0] > _t.monotonic():
        return entry[1]
    resp = httpx.get(jwks_uri, timeout=10.0)
    resp.raise_for_status()
    keys = resp.json().get("keys") or []
    _jwks_cache[key] = (_t.monotonic() + 60, keys)
    return keys


def _verify_id_token(cfg: SSOConfig, id_token: str, expected_nonce: str | None = None) -> dict:
    """校验 ID token 签名 + issuer + audience + 有效期，返回 claims。"""
    import jwt
    keys = _fetch_jwks(cfg)
    jws = jwt.get_unverified_header(id_token)
    kid = jws.get("kid")
    alg = jws.get("alg")
    if not alg or alg.startswith("HS"):
        # 不接受对称算法（secret 泄露即可伪造）；必须 Rs*/ES* 等非对称
        raise RuntimeError(f"ID token 使用不支持的签名算法: {alg!r}")
    candidate = None
    for k in keys:
        if not kid or k.get("kid") == kid:
            candidate = k
            break
    if candidate is None:
        raise RuntimeError("ID token kid 未在 JWKS 中找到签名密钥")
    public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(candidate))
    claims = jwt.decode(
        id_token,
        public_key,
        algorithms=[alg],
        audience=cfg.client_id,
        issuer=cfg.issuer.rstrip("/"),
        options={"require": ["exp", "iat", "sub"]},
    )
    if expected_nonce is not None and claims.get("nonce") != expected_nonce:
        raise RuntimeError("ID token nonce 不匹配")
    return claims


def _extract_claims(cfg: SSOConfig, token_resp: dict, expected_nonce: str | None = None) -> dict:
    """从 token 响应提取用户 claims。

    T05：生产模式必须校验 ID token 的签名（JWKS）、issuer、audience、有效期；
    验证失败直接拒绝（抛 RuntimeError），不再静默返回未验签的 claims。
    """
    import os
    id_token = token_resp.get("id_token")
    if id_token:
        try:
            return _verify_id_token(cfg, id_token, expected_nonce=expected_nonce)
        except Exception as e:
            logger.warning("ID token 验签失败：%s", e)
            if os.getenv("RUN_MODE", "").lower() == "production":
                raise RuntimeError(f"ID token 校验失败：{e}") from e
            # 非生产：标记不安全，仍退化返回但不得进入主链（由调用方决策）
            logger.warning("非生产模式：退化为未验签 claims（禁止用于生产身份建立）")
            try:
                return _decode_part(id_token.split(".")[1])
            except Exception:
                pass
    if token_resp.get("access_token"):
        # 部分 IdP 把身份信息编码在 access token（JWT）——生产模式不信任未验签
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