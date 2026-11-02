"""
模块 10 · 轻量防护与观测
--------------------------------------------------------------------
作用（基础服务层）：
  1) 登录失败计数：同一 IP + 账号 5 分钟内失败 8 次即锁定，防爆破；
  2) 请求耗时统计：记录慢请求（默认 >2s），便于发现大模型或数据库卡顿。
实现：进程内字典 + 锁，单实例够用；多实例部署时换成 Redis 即可。
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict

LOCK = asyncio.Lock()
_MAX_FAILS = 8
_WINDOW = 300          # 5 分钟

_fails: dict[str, list[float]] = defaultdict(list)

_slow_log: list[dict] = []


async def too_many_fails(key: str) -> bool:
    """27b.1 是否超过失败阈值（key = ip + 账号）。"""
    now = time.time()
    async with LOCK:
        hits = [t for t in _fails.get(key, []) if now - t < _WINDOW]
        _fails[key] = hits
        return len(hits) >= _MAX_FAILS


async def mark_fail(key: str) -> int:
    """27b.2 记录一次失败，返回窗口内失败次数。"""
    now = time.time()
    async with LOCK:
        hits = [t for t in _fails.get(key, []) if now - t < _WINDOW]
        hits.append(now)
        _fails[key] = hits
        return len(hits)


async def clear_fails(key: str) -> None:
    async with LOCK:
        _fails.pop(key, None)


def record_slow(path: str, cost_ms: float) -> None:
    """27b.3 记录慢请求（只保留最近 50 条，供 /api/health 展示）。"""
    _slow_log.append({"path": path, "ms": round(cost_ms, 1), "at": time.strftime("%H:%M:%S")})
    del _slow_log[:-50]


def slow_requests(limit: int = 5) -> list[dict]:
    return list(reversed(_slow_log[-limit:]))
