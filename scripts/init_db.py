"""
模块 31 · 数据库初始化命令（服务器上用）
--------------------------------------------------------------------
作用：在云服务器上建表 + 灌种子数据，一条命令搞定，不用启动 Web 服务。
用法：
    python scripts/init_db.py            # 建表 + 导入种子数据（库为空时）
    python scripts/init_db.py --reset    # 先删表再重建（危险）
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from app.config import DATA_DIR, settings            # noqa: E402
from app.db.models import Base                        # noqa: E402
from app.db.seed import seed_if_empty                 # noqa: E402
from app.db.session import engine                     # noqa: E402


async def main(reset: bool = False) -> int:
    print("数据库连接：" + settings.database_url.split("@")[-1])
    if not (DATA_DIR / "students.json").exists():
        from scripts.gen_data import generate_all

        print("未找到种子文件，先生成模拟数据...")
        generate_all()

    if reset:
        print("正在删除全部表...")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("建表完成")

    await seed_if_empty()
    print("种子数据导入完成，可以启动服务了：uvicorn app.main:app --host 0.0.0.0 --port 8000")
    await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main("--reset" in sys.argv)))
