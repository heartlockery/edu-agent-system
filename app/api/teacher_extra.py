"""\n模块 24 · 教师端新增功能接口
--------------------------------------------------------------------
覆盖：监考安排（查/新增）、教材管理（查/征订/改状态）、调课审批（待审批列表/通过/驳回）。
审批通过后会给申请人发一条站内消息，形成完整闭环。
"""

from __future__ import annotations

import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    ClassInfo,
    Message,
    Proctor,
    ScheduleChangeRequest,
    Teacher,
    Textbook,
    TimetableEntry,
)
from app.db.session import get_db
from app.security import require_role

router = APIRouter(prefix="/api/teacher", tags=["教师端-扩展"])
WEEK_MAP = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5}


async def _me(principal: dict, db: AsyncSession) -> Teacher:
    t = (await db.execute(select(Teacher).where(Teacher.tno == principal["username"]))).scalars().first()
    if not t:
        raise HTTPException(status_code=404, detail="教师不存在")
    return t


# ---------------------------------------------------------------
# 18b.1 监考安排
# ---------------------------------------------------------------
@router.get("/proctor")
async def proctors(principal: dict = Depends(require_role("teacher")),
                   db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Proctor).where(
        Proctor.teacher_tno == principal["username"]).order_by(Proctor.exam_date))).scalars().all()
    return {"items": [{"id": p.id, "course": p.course_name, "date": p.exam_date,
                       "session": p.session, "room": p.room, "duty": p.duty} for p in rows]}


class ProctorIn(BaseModel):
    course_name: str
    exam_date: str = ""
    session: str = "上午 09:00-11:00"
    room: str = ""
    duty: str = "主监考"


@router.post("/proctor")
async def add_proctor(data: ProctorIn, principal: dict = Depends(require_role("teacher")),
                      db: AsyncSession = Depends(get_db)):
    t = await _me(principal, db)
    db.add(Proctor(teacher_tno=t.tno, teacher_name=t.name, course_name=data.course_name,
                   exam_date=data.exam_date or datetime.now().strftime("%Y-%m-%d"),
                   session=data.session, room=data.room, duty=data.duty))
    await db.flush()
    return {"ok": True, "message": "已新增监考任务：" + data.course_name + " " + data.exam_date + " " + data.room}


# ---------------------------------------------------------------
# 18b.2 教材管理
# ---------------------------------------------------------------
@router.get("/textbooks")
async def textbooks(principal: dict = Depends(require_role("teacher")),
                    db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Textbook))).scalars().all()
    return {"items": [{"id": b.id, "course": b.course_name, "name": b.name, "isbn": b.isbn,
                       "publisher": b.publisher, "price": b.price, "status": b.status,
                       "order_count": b.order_count} for b in rows]}


class TextbookIn(BaseModel):
    course_code: str = ""
    course_name: str = ""
    name: str
    isbn: str = ""
    publisher: str = ""
    price: float = 0.0


@router.post("/textbooks")
async def add_textbook(data: TextbookIn, principal: dict = Depends(require_role("teacher")),
                       db: AsyncSession = Depends(get_db)):
    db.add(Textbook(course_code=data.course_code, course_name=data.course_name, name=data.name,
                    isbn=data.isbn, publisher=data.publisher, price=data.price, status="待确认"))
    await db.flush()
    return {"ok": True, "message": "教材《" + data.name + "》已提交征订，等待教务处确认"}


class TextbookStatusIn(BaseModel):
    status: str = Field(default="已征订", description="已征订 / 待确认 / 已停用")


@router.post("/textbooks/{book_id}/status")
async def update_textbook_status(book_id: int, data: TextbookStatusIn,
                                 principal: dict = Depends(require_role("teacher")),
                                 db: AsyncSession = Depends(get_db)):
    book = (await db.execute(select(Textbook).where(Textbook.id == book_id))).scalars().first()
    if not book:
        raise HTTPException(status_code=404, detail="教材不存在")
    book.status = data.status
    await db.flush()
    return {"ok": True, "message": "《" + book.name + "》状态已改为：" + data.status}


# ---------------------------------------------------------------
# 18b.3 调课审批
# ---------------------------------------------------------------
@router.get("/schedule/pending")
async def pending(principal: dict = Depends(require_role("teacher")),
                  db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(ScheduleChangeRequest).where(
        ScheduleChangeRequest.status == "待审批").order_by(ScheduleChangeRequest.id.desc()))).scalars().all()
    return {"items": [{"id": r.id, "teacher": r.teacher_name, "tno": r.teacher_tno,
                       "type": r.change_type, "course": r.course_name, "from": r.from_slot,
                       "to": r.to_slot, "target": r.target_tno, "reason": r.reason,
                       "created_at": r.created_at.strftime("%Y-%m-%d %H:%M")} for r in rows],
            "count": len(rows)}


class ApproveIn(BaseModel):
    action: str = Field(default="approve", description="approve / reject")
    note: str = ""


@router.post("/schedule/{req_id}/approve")
async def approve(req_id: int, data: ApproveIn,
                  principal: dict = Depends(require_role("teacher")),
                  db: AsyncSession = Depends(get_db)):
    """审批调课：通过时同步更新课表（能按「周X第N-M节」解析到原课程时才改）。"""
    req = (await db.execute(select(ScheduleChangeRequest).where(
        ScheduleChangeRequest.id == req_id))).scalars().first()
    if not req:
        raise HTTPException(status_code=404, detail="调课申请不存在")
    if req.status != "待审批":
        raise HTTPException(status_code=400, detail="该申请已处理过")

    t = await _me(principal, db)
    if data.action == "reject":
        req.status = "已驳回"
        db.add(Message(sender_role="teacher", sender_id=t.tno, sender_name=t.name,
                       receiver_role="teacher", receiver_id=req.teacher_tno,
                       title="调课申请被驳回",
                       content="你的《" + req.course_name + "》调课申请未通过："
                               + (data.note or "时间冲突，请重新选择时段")))
        await db.flush()
        return {"ok": True, "status": "已驳回", "message": "已驳回 " + req.teacher_name + " 的调课申请"}

    req.status = "已通过"
    moved = False
    # 尝试从「周三第3-4节」里解析新的星期与节次，解析成功才真正改课表
    matched = re.search(r"周([一二三四五])第?s*(d+)s*[-~到]?s*(d*)", req.to_slot or "")
    entries = (await db.execute(select(TimetableEntry).where(
        TimetableEntry.teacher_tno == req.teacher_tno,
        TimetableEntry.course_name == req.course_name))).scalars().all()
    if entries and matched:
        entry = entries[0]
        entry.weekday = WEEK_MAP[matched.group(1)]
        entry.start_section = int(matched.group(2))
        entry.end_section = int(matched.group(3) or matched.group(2)) + 1
        moved = True
    db.add(Message(sender_role="teacher", sender_id=t.tno, sender_name=t.name,
                   receiver_role="teacher", receiver_id=req.teacher_tno,
                   title="调课申请已通过",
                   content="你的《" + req.course_name + "》" + req.change_type + "已批准："
                           + req.from_slot + " -> " + (req.to_slot or "待定") + "。"))
    await db.flush()
    return {"ok": True, "status": "已通过", "moved": moved,
            "message": "已通过 " + req.teacher_name + " 的《" + req.course_name + "》调课申请"
                       + ("，课表已同步更新" if moved else "，请手动核对课表")}
