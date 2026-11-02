"""
模块 27 · 应用入口
--------------------------------------------------------------------
作用：创建 FastAPI 应用、挂载静态页面与文件下载目录、注册全部路由、
      启动时建表 + 灌入种子数据（学生/教师/课程/课表/成绩/通知/会议）。
在 VS Code 里运行： uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

import time
import traceback

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import admin, auth, chat, student, student_extra, teacher, teacher_extra
from app.config import EXPORT_DIR, STATIC_DIR, settings
from app.db.seed import seed_if_empty
from app.db.session import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("edu")
START_TS = time.time()          # 21.0 记录启动时间，健康检查里算运行时长


@asynccontextmanager
async def lifespan(app: FastAPI):
    """21.1 启动钩子：准备目录 -> 建表 -> 灌种子数据 -> 预热 RAG 索引。"""
    settings.ensure_dirs()
    settings.apply_langsmith_env()
    await init_db()
    await seed_if_empty()
    async def _warm_kb() -> None:
        """后台预热知识库：不阻塞服务启动（首次提问时也会自动加载）。"""
        try:
            from app.ai.rag import kb

            await kb.ensure_loaded()
            logger.info("RAG 知识库就绪：%s 条片段（%s 模式）", len(kb.chunks), kb.mode)
        except Exception as exc:
            logger.warning("RAG 预热失败：%s", exc)

    asyncio.create_task(_warm_kb())
    logger.info("服务已启动：%s v%s", settings.app_name, settings.version)
    yield


app = FastAPI(title=settings.app_name, version=settings.version, lifespan=lifespan)

# 21.1.1 静态挂载要求目录必须存在，这里先确保 data/exports、knowledge 等目录就绪
settings.ensure_dirs()

# 21.2 跨域：方便前端分离部署或直接用 Apifox 调试
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# 21.2b 1Mbps 带宽下压缩收益明显：html/css/js/json 统一 gzip
app.add_middleware(GZipMiddleware, minimum_size=800)


@app.middleware("http")
async def timing_middleware(request: Request, call_next):
    """21.2d 请求耗时观测：超过 2 秒的接口记一条慢日志，方便定位卡顿。"""
    start = time.time()
    response = await call_next(request)
    cost_ms = (time.time() - start) * 1000
    response.headers["X-Process-Time-Ms"] = str(round(cost_ms, 1))
    # 21.2e 静态资源长缓存、首页不缓存（保证发版后刷新即生效）
    if request.url.path.startswith("/static"):
        response.headers["Cache-Control"] = "public, max-age=3600"
    elif request.url.path in ("/", "/index.html"):
        response.headers["Cache-Control"] = "no-cache"
    if cost_ms > 2000:
        from app.services.limits import record_slow

        record_slow(request.url.path, cost_ms)
        logger.warning("慢请求 %.0fms %s", cost_ms, request.url.path)
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """21.2c 兜底异常：返回统一 JSON，避免前端拿到一坨 HTML 错误页。"""
    logger.error("未处理异常 %s %s: %s", request.method, request.url.path, exc)
    logger.error(traceback.format_exc()[:2000])
    return JSONResponse(status_code=500, content={"detail": "服务器开小差了，请稍后重试"})


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """21.2d2 404 兜底：只有「路由真的不存在」时才改写，业务里的 404 保留原 detail。

    前端单页路由（非 /api）回退到 index.html，方便以后加前端路由。
    """
    if exc.status_code == 404 and exc.detail in ("Not Found", None):
        if request.url.path.startswith("/api"):
            return JSONResponse(status_code=404, content={"detail": "接口不存在：" + request.url.path})
        return FileResponse(STATIC_DIR / "index.html")
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail},
                        headers=getattr(exc, "headers", None))

# 21.3 路由注册
app.include_router(auth.router)
app.include_router(admin.recovery_router)          # 免登录的账号找回申请
app.include_router(student.router)
app.include_router(student_extra.router)
app.include_router(teacher.router)
app.include_router(teacher_extra.router)
app.include_router(admin.router)
app.include_router(chat.router)


@app.get("/api/health")
async def health():
    """21.4 健康检查：应用存活 + 数据库连通 + 运行时长，探活用。"""
    db_ok = False
    db_ms = None
    try:
        from app.db.session import SessionLocal

        t0 = time.time()
        async with SessionLocal() as session:
            await session.execute(text("select 1"))
        db_ms = round((time.time() - t0) * 1000, 1)
        db_ok = True
    except Exception as exc:                     # 数据库挂了也要能返回 200，方便区分层次
        logger.warning("健康检查：数据库不可用 %s", exc)
    from app.services.limits import slow_requests

    return {"ok": True, "app": settings.app_name, "version": settings.version,
            "database": "up" if db_ok else "down",
            "db_backend": settings.database_url.split(":")[0],
            "db_latency_ms": db_ms,
            "uptime_seconds": round(time.time() - START_TS, 1),
            "ai": {"student_online": bool(settings.student_api_key),
                   "teacher_online": bool(settings.teacher_api_key),
                   "langsmith": settings.langsmith_enabled and bool(settings.langsmith_api_key)},
            "slow_requests": slow_requests()}


# 21.5 静态资源：前端页面 + 导出的 Excel 下载
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/files/export", StaticFiles(directory=str(EXPORT_DIR)), name="export")


@app.get("/")
async def index():
    """21.6 首页直接返回内置的单页前端（登录 + 学生/教师/管理员三种视图）。"""
    return FileResponse(STATIC_DIR / "index.html")
