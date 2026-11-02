"""
模块 34 · 轻量压测（验证 1Mbps / 2 核实例的并发表现）
--------------------------------------------------------------------
用法：
    python scripts/load_test.py                    # 打本地 127.0.0.1:8000
    BASE=http://119.45.248.158:8000 python scripts/load_test.py
指标：并发数、请求数、成功率、平均/95 分位延迟、最慢一次。
"""

from __future__ import annotations

import asyncio
import os
import statistics
import sys
import time

import httpx

BASE = os.environ.get("BASE", "http://127.0.0.1:8000")
CONCURRENCY = int(os.environ.get("CONC", "12"))
ROUNDS = int(os.environ.get("ROUNDS", "3"))

PATHS = ["/api/health", "/", "/api/chat/health"]


async def hit(client: httpx.AsyncClient, path: str, token: str | None) -> tuple[str, int, float]:
    headers = {"Authorization": "Bearer " + token} if token else {}
    t0 = time.time()
    try:
        r = await client.get(BASE + path, headers=headers)
        return path, r.status_code, (time.time() - t0) * 1000
    except Exception:
        return path, 0, (time.time() - t0) * 1000


async def main() -> int:
    async with httpx.AsyncClient(timeout=30) as client:
        token = None
        try:
            r = await client.post(BASE + "/api/auth/login",
                                  json={"role": "student", "username": "2024010101", "password": "123456"})
            if r.status_code == 200:
                token = r.json()["token"]
            paths = PATHS + (["/api/student/grades", "/api/student/timetable"] if token else [])
        except Exception as exc:
            print("服务不可达：", exc)
            return 2

        results: list[tuple[str, int, float]] = []
        start = time.time()
        for _ in range(ROUNDS):
            tasks = []
            for i in range(CONCURRENCY):
                tasks.append(hit(client, paths[i % len(paths)], token))
            results.extend(await asyncio.gather(*tasks))
        cost = time.time() - start

    ok = [r for r in results if 200 <= r[1] < 300]
    bad = [r for r in results if not (200 <= r[1] < 300)]
    lat = sorted(r[2] for r in results)
    p95 = lat[int(len(lat) * 0.95) - 1] if lat else 0
    print("并发 " + str(CONCURRENCY) + " × " + str(ROUNDS) + " 轮，共 " + str(len(results)) + " 次请求，耗时 "
          + str(round(cost, 2)) + "s")
    print("成功 " + str(len(ok)) + " / 失败 " + str(len(bad)))
    print("平均 " + str(round(statistics.mean(lat), 1)) + "ms，P95 " + str(round(p95, 1))
          + "ms，最快 " + str(round(lat[0], 1)) + "ms，最慢 " + str(round(lat[-1], 1)) + "ms")
    if bad:
        print("失败明细：", [(b[0], b[1]) for b in bad][:5])
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
