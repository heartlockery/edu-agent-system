"""
模块 21 · 学生端接口
--------------------------------------------------------------------
作用：菜单、个人信息、成绩、课表、考试、通知、消息、空闲教室、选课、功能状态。
      这些接口同时也是 AI 工具的数据来源，保证「网页看到的数据」和「AI 说的数据」一致。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    ClassInfo,
    Enrollment,
    ExamAppointment,
    Grade,
    Message,
    Notification,
    Student,
    TimetableEntry,
)
from app.db.session import get_db
from app.schemas import ExamReserveIn, ProfileUpdateIn
from app.security import require_role
from app.services.exam_plan import all_exams, find_exam
from app.services.grades import grade_point
from app.services.registry import find_feature, menu_for

router = APIRouter(prefix="/api/student", tags=["学生端"])


async def _me(principal: dict, db: AsyncSession) -> Student:
    """17.1 取当前登录学生。"""
    row = (await db.execute(select(Student).where(Student.sno == principal["username"]))).scalars().first()
    if not row:
        raise HTTPException(status_code=404, detail="学生不存在")
    return row


@router.get("/menu")
async def menu(principal: dict = Depends(require_role("student"))):
    return {"role": "student", "menus": menu_for("student")}


@router.get("/profile")
async def profile(principal: dict = Depends(require_role("student")), db: AsyncSession = Depends(get_db)):
    """17.2 个人信息（含班级与辅导员）。"""
    stu = await _me(principal, db)
    klass = (await db.execute(select(ClassInfo).where(ClassInfo.id == stu.class_id))).scalar_one_or_none()
    return {"sno": stu.sno, "name": stu.name, "gender": stu.gender, "major": stu.major,
            "enroll_year": stu.enroll_year, "phone": stu.phone, "email": stu.email,
            "class_name": klass.name if klass else "", "advisor": klass.advisor if klass else ""}


@router.put("/profile")
async def update_profile(data: ProfileUpdateIn,
                         principal: dict = Depends(require_role("student")),
                         db: AsyncSession = Depends(get_db)):
    """17.3 个人信息维护：只允许改手机号和邮箱。"""
    stu = await _me(principal, db)
    if data.phone is not None:
        stu.phone = data.phone
    if data.email is not None:
        stu.email = data.email
    await db.flush()
    return {"ok": True, "message": "个人信息已更新"}


@router.get("/grades")
async def grades(semester: str = Query(default=""),
                 principal: dict = Depends(require_role("student")),
                 db: AsyncSession = Depends(get_db)):
    """17.4 成绩查询：返回明细 + 汇总（总分/平均分/绩点）。"""
    stu = await _me(principal, db)
    stmt = select(Grade).where(Grade.student_id == stu.id)
    if semester:
        stmt = stmt.where(Grade.semester == semester)
    rows = (await db.execute(stmt)).scalars().all()
    items = [{"course_code": g.course_code, "course_name": g.course_name, "credit": g.credit,
              "score": g.score, "gpa": grade_point(g.score), "semester": g.semester} for g in rows]
    credits = round(sum(g.credit for g in rows), 1)
    avg = round(sum(g.score for g in rows) / len(rows), 1) if rows else 0
    gpa = round(sum(grade_point(g.score) * g.credit for g in rows) / credits, 2) if credits else 0
    return {"items": items, "summary": {"count": len(rows), "avg": avg, "gpa": gpa, "credits": credits}}


@router.get("/timetable")
async def timetable(weekday: int = Query(default=0, ge=0, le=5),
                    principal: dict = Depends(require_role("student")),
                    db: AsyncSession = Depends(get_db)):
    """17.5 课表查询（个人/班级同一份数据，前端按星期渲染成表格）。"""
    stu = await _me(principal, db)
    stmt = select(TimetableEntry).where(TimetableEntry.class_id == stu.class_id)
    if weekday:
        stmt = stmt.where(TimetableEntry.weekday == weekday)
    rows = (await db.execute(stmt.order_by(TimetableEntry.weekday, TimetableEntry.start_section))).scalars().all()
    return {"class_name": (await db.execute(select(ClassInfo.name).where(ClassInfo.id == stu.class_id))).scalar_one_or_none(),
            "items": [{"weekday": e.weekday, "course": e.course_name, "teacher": e.teacher_name,
                       "start": e.start_section, "end": e.end_section, "location": e.location,
                       "weeks": e.weeks} for e in rows]}


@router.get("/exams")
async def exams(principal: dict = Depends(require_role("student")), db: AsyncSession = Depends(get_db)):
    """17.6 考试信息 + 本人预约状态。"""
    stu = await _me(principal, db)
    booked = (await db.execute(select(ExamAppointment).where(ExamAppointment.student_id == stu.id))).scalars().all()
    booked_map = {b.course_code: b.status for b in booked}
    items = []
    for e in all_exams():
        items.append({**e, "reserved": booked_map.get(e["course_code"], "")})
    return {"items": items, "sessions": ["上午", "下午", "晚上"]}


@router.post("/exams/reserve")
async def reserve_exam(data: ExamReserveIn,
                       principal: dict = Depends(require_role("student")),
                       db: AsyncSession = Depends(get_db)):
    """17.7 考试预约（网页和 AI 走同一段逻辑）。"""
    exam = find_exam(data.course_code)
    if not exam:
        raise HTTPException(status_code=404, detail="没有这门课的考试安排")
    stu = await _me(principal, db)
    exists = (await db.execute(select(ExamAppointment).where(
        ExamAppointment.student_id == stu.id, ExamAppointment.course_code == exam["course_code"]))).scalars().first()
    if exists:
        return {"ok": True, "message": "你已经预约过这门考试", "status": exists.status}
    db.add(ExamAppointment(student_id=stu.id, course_code=exam["course_code"],
                           course_name=exam["course_name"], exam_date=exam["exam_date"],
                           session=data.session, room=exam["room"], status="已预约"))
    await db.flush()
    return {"ok": True, "message": "预约成功", "exam": exam, "session": data.session}


@router.get("/notifications")
async def notifications(principal: dict = Depends(require_role("student")),
                        db: AsyncSession = Depends(get_db)):
    """17.8 通知公告：全校通知 + 本班通知。"""
    stu = await _me(principal, db)
    rows = (await db.execute(select(Notification).where(
        (Notification.target_class_id.is_(None)) | (Notification.target_class_id == stu.class_id)
    ).order_by(Notification.id.desc()))).scalars().all()
    return {"items": [{"id": n.id, "title": n.title, "content": n.content, "category": n.category,
                       "sender": n.sender_name, "created_at": n.created_at.strftime("%Y-%m-%d %H:%M")}
                      for n in rows]}


@router.get("/messages")
async def messages(principal: dict = Depends(require_role("student")),
                   db: AsyncSession = Depends(get_db)):
    """17.9 消息列表（教师点对点消息）。"""
    rows = (await db.execute(select(Message).where(Message.receiver_id == principal["username"])
                             .order_by(Message.id.desc()))).scalars().all()
    return {"items": [{"id": m.id, "title": m.title, "content": m.content, "sender": m.sender_name,
                       "is_read": m.is_read, "created_at": m.created_at.strftime("%Y-%m-%d %H:%M")}
                      for m in rows],
            "unread": len([m for m in rows if not m.is_read])}


@router.post("/messages/{message_id}/read")
async def read_message(message_id: int, principal: dict = Depends(require_role("student")),
                       db: AsyncSession = Depends(get_db)):
    msg = (await db.execute(select(Message).where(Message.id == message_id))).scalars().first()
    if msg and msg.receiver_id == principal["username"]:
        msg.is_read = True
        await db.flush()
    return {"ok": True}


@router.get("/free-classrooms")
async def free_classrooms(weekday: int = Query(default=1, ge=1, le=5), section: int = Query(default=1, ge=1, le=10),
                          principal: dict = Depends(require_role("student")),
                          db: AsyncSession = Depends(get_db)):
    """17.10 空闲教室：排查同一时间被占用的教室。"""
    from app.ai.tools_student import ROOM_POOL

    busy = (await db.execute(select(TimetableEntry.location).where(
        TimetableEntry.weekday == weekday, TimetableEntry.start_section <= section,
        TimetableEntry.end_section >= section))).scalars().all()
    busy_set = {b for b in busy if b}
    return {"weekday": weekday, "section": section,
            "items": [{"room": r, "status": "空闲"} for r in ROOM_POOL if r not in busy_set],
            "busy": sorted(busy_set)}


@router.get("/enrollments")
async def enrollments(principal: dict = Depends(require_role("student")),
                      db: AsyncSession = Depends(get_db)):
    """17.11 选课情况确认。"""
    stu = await _me(principal, db)
    rows = (await db.execute(select(Enrollment).where(Enrollment.student_id == stu.id))).scalars().all()
    return {"items": [{"course_code": e.course_code, "course_name": e.course_name,
                       "credit": e.credit, "status": e.status, "semester": e.semester} for e in rows],
            "total_credit": round(sum(e.credit for e in rows), 1)}


@router.get("/feature/{key}")
async def feature_status(key: str, principal: dict = Depends(require_role("student"))):
    """17.12 未实现功能统一返回「系统正在开发中」（前端据此弹提示）。"""
    item = find_feature(key)
    if not item:
        raise HTTPException(status_code=404, detail="功能不存在")
    if item["status"] != "ready":
        return {"status": "developing", "name": item["name"], "message": "系统正在开发中，敬请期待"}
    return {"status": "ready", "name": item["name"], "endpoint": item["endpoint"]}
