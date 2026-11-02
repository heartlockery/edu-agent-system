"""
模块 3 · 异步数据库会话
--------------------------------------------------------------------
作用：创建异步引擎（SQLite / MySQL 自动识别）、提供 FastAPI 依赖 get_db、
      提供建表函数 init_db。所有接口与 AI 工具都通过这里拿连接。
要点：SQLite 下关闭同线程检查；MySQL 下开启连接池预检，避免云服务器空闲断连。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.db.models import Base

# 3.1 引擎：SQLite 走文件，MySQL 走连接池
_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
_engine_kwargs: dict = {"echo": False, "future": True, "connect_args": _connect_args}
if not settings.database_url.startswith("sqlite"):
    _engine_kwargs.update(pool_size=10, max_overflow=20, pool_recycle=1800, pool_pre_ping=True)

engine = create_async_engine(settings.database_url, **_engine_kwargs)

# 3.2 会话工厂：expire_on_commit=False，让 ORM 对象在提交后仍可读
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """3.3 FastAPI 依赖注入：每个请求一个会话，异常自动回滚。"""
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """3.4 启动时建表（生产环境可换成 Alembic 迁移）。"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
