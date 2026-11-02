"""在线模型自检：确认两把 Key 生效、回答语气是否温柔。"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
sys.stdout.reconfigure(encoding="utf-8")

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + (BASE / "data" / "smoke.db").as_posix()

from app.main import app            # noqa: E402
import httpx                        # noqa: E402


async def main() -> int:
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="http://test", timeout=90) as c:
            h = (await c.get("/api/chat/health")).json()
            print("健康检查:", h)

            r = await c.post("/api/auth/login", json={"role": "student", "username": "2024010101", "password": "123456"})
            sh = {"Authorization": "Bearer " + r.json()["token"]}
            r = await c.post("/api/chat", headers=sh, json={"message": "我上学期高数考了多少分呀", "session_id": "o1"})
            d = r.json()
            print("\n[学生] 模型=", d.get("model"), " 工具=", [t["tool"] for t in d.get("tool_calls", [])])
            print("  回答：", d.get("answer", "")[:300])
            print("  过程：", " / ".join(d.get("trace", [])))

            r = await c.post("/api/auth/login", json={"role": "teacher", "username": "T1001", "password": "123456"})
            th = {"Authorization": "Bearer " + r.json()["token"]}
            r = await c.post("/api/chat", headers=th, json={"message": "2401班这次考试平均分怎么样", "session_id": "o2"})
            d = r.json()
            print("\n[教师] 模型=", d.get("model"), " 工具=", [t["tool"] for t in d.get("tool_calls", [])])
            print("  回答：", d.get("answer", "")[:300])

            r = await c.post("/api/chat", headers=sh, json={"message": "推荐几个学 Python 的网站", "session_id": "o3"})
            d = r.json()
            print("\n[联网] 工具=", [t["tool"] for t in d.get("tool_calls", [])])
            print("  回答：", d.get("answer", "")[:260])
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
