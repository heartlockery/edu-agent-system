"""
模块 4 · 认证与鉴权
--------------------------------------------------------------------
作用：密码哈希（PBKDF2）、无状态令牌（HMAC-SHA256 签名）、FastAPI 依赖。
说明：不引入 pyjwt，仅用标准库实现 JWT 风格的 token，减少依赖、方便教学演示；
      token 载荷包含 role(学生/教师)、uid、username 和过期时间。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

from fastapi import Depends, Header, HTTPException

from app.config import settings


# ---------------------------------------------------------------
# 4.1 密码：pbkdf2_sha256 + 每用户随机盐，数据库里绝不存明文
# ---------------------------------------------------------------
def hash_password(raw: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(8)
    digest = hashlib.pbkdf2_hmac("sha256", raw.encode(), salt.encode(), 120_000).hex()
    return "pbkdf2_sha256$120000$" + salt + "$" + digest


def verify_password(raw: str, stored: str) -> bool:
    try:
        _algo, _round, salt, _digest = stored.split("$")
    except ValueError:
        return False
    return hmac.compare_digest(hash_password(raw, salt), stored)


# ---------------------------------------------------------------
# 4.2 令牌：base64url(payload).签名
# ---------------------------------------------------------------
def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def create_token(role: str, uid: int, username: str) -> str:
    payload = {
        "role": role,
        "uid": uid,
        "username": username,
        "exp": int(time.time()) + settings.token_expire_minutes * 60,
    }
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode())
    sign = hmac.new(settings.secret_key.encode(), body.encode(), hashlib.sha256).hexdigest()[:32]
    return body + "." + sign


def decode_token(token: str) -> dict:
    try:
        body, sign = token.split(".")
    except ValueError:
        raise HTTPException(status_code=401, detail="令牌格式错误")
    expect = hmac.new(settings.secret_key.encode(), body.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(sign, expect):
        raise HTTPException(status_code=401, detail="令牌签名校验失败")
    payload = json.loads(_b64d(body))
    if payload.get("exp", 0) < time.time():
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    return payload


# ---------------------------------------------------------------
# 4.3 FastAPI 依赖：从 Authorization: Bearer xxx 中解析出当前身份
# ---------------------------------------------------------------
async def get_principal(authorization: str = Header(default="")) -> dict:
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="缺少登录令牌")
    return decode_token(authorization[7:].strip())


def require_role(role: str):
    """用法：Depends(require_role("student"))，越权直接 403。"""

    async def _checker(principal: dict = Depends(get_principal)) -> dict:
        if principal.get("role") != role:
            raise HTTPException(status_code=403, detail="当前身份无权访问该接口")
        return principal

    return _checker
