"""可选 LDAP 绑定认证（A2）。

流程：用服务账号绑定搜索用户 DN → 用用户密码绑定校验 → 返回规范化身份。
未配置（LDAPConfig.enabled=False）时不注册路由。

依赖：``ldap3`` 为非强制依赖，首次调用时导入；缺失时抛出带安装提示的异常。
"""
from __future__ import annotations

import logging

from ..config import LDAPConfig

logger = logging.getLogger(__name__)


def _ldap3():
    try:
        import ldap3  # type: ignore
        return ldap3
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "LDAP 认证需要安装 ldap3：pip install ldap3"
        ) from e


# RFC4515 搜索过滤器特殊字符转义，防过滤器注入（如 `*)(uid=*))(|(uid=`）
def _escape_filter_value(value: str) -> str:
    return "".join(
        f"\\{ord(ch):02x}" if ch in "*()\\\x00" else ch
        for ch in value
    )


# RFC4514 DN 特殊字符转义，防用户名拼接 DN 时绑定到非预期条目
def _escape_dn_value(value: str) -> str:
    return "".join(
        f"\\{ch}" if ch in ',+"\\<>;=#' or (idx == 0 and ch in " #") or (idx == len(value) - 1 and ch == " ") else ch
        for idx, ch in enumerate(value)
    )


def authenticate(cfg: LDAPConfig, username: str, password: str) -> dict | None:
    """LDAP 绑定认证。成功返回规范化身份 dict，失败返回 None。

    身份字段：sub（用 username 充当）、email、username、display_name。
    """
    if not cfg.server or not username or not password:
        return None
    ldap3 = _ldap3()
    from ldap3 import Connection, Server  # noqa: F811

    server = Server(cfg.server, port=cfg.port, use_ssl=cfg.use_tls)
    # 1. 服务账号绑定（用于搜索用户 DN）
    if cfg.bind_dn:
        conn = Connection(server, user=cfg.bind_dn, password=cfg.bind_password, auto_bind=True)
        try:
            search_filter = (cfg.search_filter or "(uid={username})").format(
                username=_escape_filter_value(username)
            )
        except KeyError:
            search_filter = cfg.search_filter or "(uid={username})"
        conn.search(cfg.search_base, search_filter, attributes=["mail", "cn", "uid"])
        if not conn.entries:
            logger.info("LDAP 未找到用户：%s", username)
            return None
        entry = conn.entries[0]
        user_dn = entry.entry_dn
        mail = str(entry.mail.value) if hasattr(entry, "mail") and entry.mail.value else ""
        cn = str(entry.cn.value) if hasattr(entry, "cn") and entry.cn.value else ""
        conn.unbind()
    else:
        # 无服务账号：直接尝试用户 DN 绑定（需配置 bind_dn 模板）
        user_dn = (cfg.bind_dn or "").format(username=_escape_dn_value(username))
        mail, cn = "", ""

    # 2. 用用户密码绑定校验
    verify = Connection(server, user=user_dn, password=password, auto_bind=True)
    verify.unbind()

    return {
        "sub": f"ldap:{username}",
        "email": mail,
        "username": username,
        "display_name": cn or username,
    }