"""
模块 26 · AI 对话接口（学生端 / 教师端共用）
--------------------------------------------------------------------
作用：接收一句话 -> 组装登录态上下文 -> 交给 LangGraph Agent -> 返回答案与工具轨迹。
说明：管理员身份直接拒绝（管理员系统按设计不接入大模型）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.graph import run_agent
from app.db.models import ClassInfo, Meeting, ScheduleChangeRequest, Student, Teacher
from app.db.session import get_db
from app.schemas import ChatIn, ChatOut
from app.security import get_principal

router = APIRouter(prefix="/api/chat", tags=["AI 助手"])


async def _build_ctx(principal: dict, db: AsyncSession) -> dict:
    """20.1 把登录态翻译成工具能用的上下文（学号/工号/班级）。"""
    role = principal["role"]
    username = principal["username"]
    if role == "student":
        stu = (await db.execute(select(Student).where(Student.sno == username))).scalars().first()
        if not stu:
            raise HTTPException(status_code=404, detail="学生不存在")
        klass = (await db.execute(select(ClassInfo).where(ClassInfo.id == stu.class_id))).scalar_one_or_none()
        return {"db": db, "role": "student", "sno": stu.sno, "username": username,
                "name": stu.name, "class_id": stu.class_id,
                "class_name": klass.name if klass else ""}

    teacher = (await db.execute(select(Teacher).where(Teacher.tno == username))).scalars().first()
    if not teacher:
        raise HTTPException(status_code=404, detail="教师不存在")
    return {"db": db, "role": "teacher", "tno": teacher.tno, "username": username, "name": teacher.name}


@router.post("", response_model=ChatOut)
async def chat(data: ChatIn, principal: dict = Depends(get_principal),
               db: AsyncSession = Depends(get_db)):
    """20.2 对话主入口：一句话直达功能（查成绩、查课表、预约考试、发通知、导出文件…）。"""
    if principal["role"] == "admin":
        raise HTTPException(status_code=403, detail="管理员系统不提供 AI 助手，请使用后台管理功能")

    # 20.2.1 内容边界：游戏、代刷代考这类请求直接温柔拒绝，不进入大模型
    from app.ai.guard import check

    blocked = check(data.message)
    if blocked:
        return {"answer": blocked, "tool_calls": [], "ui_actions": [], "model": "guard", "trace": ["内容边界拦截"]}

    ctx = await _build_ctx(principal, db)
    result = await run_agent(principal["role"], data.message, data.session_id, db, ctx)

    # 写操作（预约、发通知等）需要提交事务；读操作提交也无副作用
    await db.commit()
    return {
        "answer": result["answer"],
        "tool_calls": result["tool_calls"],
        "ui_actions": result["ui_actions"],
        "model": result["model"],
        "trace": result["trace"],
    }


@router.get("/greeting")
async def greeting(principal: dict = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    """20.2b 教师端打招呼（学生端在 student_extra.greeting，带课表信息）。"""
    if principal["role"] == "student":
        from app.api.student_extra import greeting as student_greeting

        return await student_greeting(principal, db)
    from datetime import datetime

    teacher = (await db.execute(select(Teacher).where(Teacher.tno == principal["username"]))).scalars().first()
    name = teacher.name if teacher else "老师"
    hour = datetime.now().hour
    hello = "早上好" if hour < 11 else ("下午好" if hour < 18 else "晚上好")
    meetings = (await db.execute(select(Meeting).where(
        Meeting.teacher_tno == principal["username"]))).scalars().all()
    next_meeting = ("最近一次会议是 " + meetings[0].start_time + " " + meetings[0].title + "。"
                    if meetings else "近期没有会议安排。")
    pending = (await db.execute(select(ScheduleChangeRequest))).scalars().all()
    pending_count = len([p for p in pending if p.status == "待审批"])
    pending_line = ("还有 " + str(pending_count) + " 条调课申请等你审批哦。"
                    if pending_count else "暂时没有待审批的调课申请。")
    tail = "要查班级成绩、发通知、导出 Excel 或者调课，直接和我说就好。"
    return {"text": hello + "，" + name + " 老师～ " + next_meeting + pending_line + tail, "name": name}


@router.get("/health")
async def health():
    """20.3 自检：告诉前端当前是「在线模型」还是「离线规则模式」。"""
    from app.config import settings
    from app.ai.rag import kb

    await kb.ensure_loaded()
    return {
        "student_model": settings.student_model,
        "student_online": bool(settings.student_api_key),
        "teacher_model": settings.teacher_model,
        "teacher_online": bool(settings.teacher_api_key),
        "langsmith": settings.langsmith_enabled and bool(settings.langsmith_api_key),
        "rag_mode": kb.mode,
        "rag_chunks": len(kb.chunks),
    }
