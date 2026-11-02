import asyncio
import sys
from collections import Counter

sys.path.insert(0, r"D:\desktop\edu-agent-system")
sys.stdout.reconfigure(encoding="utf-8")
from app.ai.rag import kb


async def main():
    await kb.ensure_loaded()
    print("总片段数:", len(kb.chunks), "| 模式:", kb.mode)
    for title, n in Counter(ch["title"] for ch in kb.chunks).items():
        print("   ", title, n, "段")
    print("各片段字数:", [len(ch["content"]) for ch in kb.chunks])
    for q in ["转专业需要什么条件", "补考怎么安排", "调课要提前几天"]:
        print()
        print("查询:", q)
        for h in await kb.search(q, k=3):
            print("   分数", h["score"], "|", h["title"], "|", h["content"][:46].replace("\n", " "))


asyncio.run(main())
