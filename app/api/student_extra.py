"""\n模块 22 · 学生端新增功能接口
--------------------------------------------------------------------
覆盖：首页日历、AI 打招呼、补考确认、通用报名申请、培养方案、
      教材明细/费用/预订、自主选课、学业情况、选课名单。
设计：所有写操作都落到既有表（Enrollment / Application），不新增散表。
"""

from __future__ import annotations

import calendar as pycalendar
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Application,
    ClassInfo,
    Enrollment,
    ExamAppointment,
    Grade,
    Message,
    Student,
    Textbook,
    TimetableEntry,
)
from app.db.session import get_db
from app.schemas import ProfileUpdateIn  # noqa: F401  （保持模块导入一致性）
from app.security import require_role
from app.services.curriculum import ELECTIVES, TEXTBOOKS, TRAINING_PLAN, total_credits
from app.services.exam_plan import all_exams
from app.services.grades import grade_point

router = APIRouter(prefix="/api/student", tags=["学生端-扩展"])

WEEK_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


async def _me(principal: dict, db: AsyncSession) -> Student:
    stu = (await db.execute(select(Student).where(Student.sno == principal["username"]))).scalars().first()
    if not stu:
        raise HTTPException(status_code=404, detail="学生不存在")
    return stu


# ---------------------------------------------------------------
# 17b.1 首页日历：本月每天上什么课、有没有考试
# ---------------------------------------------------------------
@router.get("/calendar")
async def calendar(year: int = Query(default=0), month: int = Query(default=0),
                   principal: dict = Depends(require_role("student")),
                   db: AsyncSession = Depends(get_db)):
    today = date.today()
    year, month = (year or today.year), (month or today.month)
    if not 1 <= month <= 12:
        raise HTTPException(status_code=400, detail="月份不合法")

    stu = await _me(principal, db)
    entries = (await db.execute(
        select(TimetableEntry).where(TimetableEntry.class_id == stu.class_id))).scalars().all()
    exams = all_exams()
    booked = {(a.course_code): a.status for a in (await db.execute(
        select(ExamAppointment).where(ExamAppointment.student_id == stu.id))).scalars().all()}

    days = []
    for day in range(1, pycalendar.monthrange(year, month)[1] + 1):
        d = date(year, month, day)
        courses = []
        if d.weekday() < 5:
            for e in entries:
                if e.weekday == d.weekday() + 1:
                    courses.append({"name": e.course_name, "sections": str(e.start_section) + "-" + str(e.end_section),
                                    "time": e.location, "teacher": e.teacher_name})
        day_exams = [{"name": x["course_name"], "time": x["session"], "room": x["room"],
                      "reserved": booked.get(x["course_code"], "")}
                     for x in exams if x["exam_date"] == d.isoformat()]
        days.append({"date": d.isoformat(), "day": day, "weekday": WEEK_CN[d.weekday()],
                     "is_today": d == today, "courses": courses, "exams": day_exams})
    return {"year": year, "month": month, "today": today.isoformat(), "days": days}


# ---------------------------------------------------------------
# 17b.2 打招呼：登录后 AI 先开口（模板生成，快且稳定）
# ---------------------------------------------------------------
@router.get("/greeting")
async def greeting(principal: dict = Depends(require_role("student")),
                   db: AsyncSession = Depends(get_db)):
    stu = await _me(principal, db)
    klass = (await db.execute(select(ClassInfo).where(ClassInfo.id == stu.class_id))).scalar_one_or_none()
    now = datetime.now()
    hour = now.hour
    if hour < 6:
        hello = "夜深啦，还在学习吗？记得早点休息呀～"
    elif hour < 11:
        hello = "早上好呀"
    elif hour < 14:
        hello = "中午好呀"
    elif hour < 18:
        hello = "下午好呀"
    else:
        hello = "晚上好呀"

    entries = (await db.execute(select(TimetableEntry).where(
        TimetableEntry.class_id == stu.class_id,
        TimetableEntry.weekday == now.isoweekday()))).scalars().all()
    today_line = ("今天你有 " + str(len(entries)) + " 节课：" + "、".join(e.course_name for e in entries) + "。"
                  if entries else "今天你没有排课，可以安心自习或者查漏补缺～")

    unread = len((await db.execute(select(Message).where(
        Message.receiver_id == stu.sno, Message.is_read.is_(False)))).scalars().all())
    unread_line = ("还有 " + str(unread) + " 条老师的消息没看哦。" if unread else "消息都看完啦，很勤快～")

    text = (hello + "，" + stu.name + " 同学，我是你的教务小助手。"
            + today_line + unread_line
            + "\n想查成绩、看课表、预约考试，直接和我说就行，也可以问我学习上的问题～")
    return {"text": text, "name": stu.name, "class_name": klass.name if klass else ""}


# ---------------------------------------------------------------
# 17b.2b 首页待办聚合：一次请求拿到申请进度、未读消息、补考、近期考试
# ---------------------------------------------------------------
@router.get("/todos")
async def todos(principal: dict = Depends(require_role("student")),
                db: AsyncSession = Depends(get_db)):
    stu = await _me(principal, db)
    apps = (await db.execute(select(Application).where(
        Application.student_id == stu.id).order_by(Application.id.desc()).limit(5))).scalars().all()
    unread = len((await db.execute(select(Message).where(
        Message.receiver_id == stu.sno, Message.is_read.is_(False)))).scalars().all())
    failed = (await db.execute(select(Grade).where(
        Grade.student_id == stu.id, Grade.score < 60))).scalars().all()
    confirmed = {a.title for a in (await db.execute(select(Application).where(
        Application.student_id == stu.id, Application.app_type == "补考确认"))).scalars().all()}
    makeup_pending = [g.course_name for g in failed if g.course_name not in confirmed]
    exams = [e for e in all_exams()][:3]
    return {"applications": [{"type": a.app_type, "title": a.title, "status": a.status,
                              "created_at": a.created_at.strftime("%m-%d %H:%M")} for a in apps],
            "unread_messages": unread,
            "makeup_pending": makeup_pending,
            "upcoming_exams": [{"course": e["course_name"], "date": e["exam_date"],
                                "session": e["session"], "room": e["room"]} for e in exams]}


# ---------------------------------------------------------------
# 17b.3 补考确认：先列出不及格课程，再一键确认
# ---------------------------------------------------------------
@router.get("/makeup")
async def makeup_list(principal: dict = Depends(require_role("student")),
                      db: AsyncSession = Depends(get_db)):
    stu = await _me(principal, db)
    rows = (await db.execute(select(Grade).where(
        Grade.student_id == stu.id, Grade.score < 60))).scalars().all()
    submitted = (await db.execute(select(Application).where(
        Application.student_id == stu.id, Application.app_type == "补考确认"))).scalars().all()
    done = {a.title for a in submitted}
    return {"items": [{"course_code": g.course_code, "course_name": g.course_name, "score": g.score,
                       "confirmed": g.course_name in done} for g in rows],
            "count": len(rows), "confirmed_count": len(done)}


class MakeupIn(BaseModel):
    course_codes: list[str] = Field(default_factory=list)


@router.post("/makeup/confirm")
async def makeup_confirm(data: MakeupIn, principal: dict = Depends(require_role("student")),
                         db: AsyncSession = Depends(get_db)):
    stu = await _me(principal, db)
    failed = (await db.execute(select(Grade).where(
        Grade.student_id == stu.id, Grade.score < 60))).scalars().all()
    if not failed:
        return {"ok": True, "count": 0, "message": "你没有不及格的课程，不需要补考，继续保持呀～"}
    targets = [g for g in failed if not data.course_codes or g.course_code in data.course_codes]
    if not targets:
        return {"ok": False, "count": 0, "message": "没有匹配到要确认的课程。"}
    for g in targets:
        db.add(Application(student_id=stu.id, app_type="补考确认", title=g.course_name,
                           detail="成绩 " + str(g.score) + " 分，申请参加补考", status="已提交"))
    await db.flush()
    return {"ok": True, "count": len(targets),
            "message": "已为你确认 " + str(len(targets)) + " 门补考：" + "、".join(g.course_name for g in targets)}


# ---------------------------------------------------------------
# 17b.4 通用报名申请（学籍异动/重修/转专业/学分认定/创新创业…）
# ---------------------------------------------------------------
class ApplicationIn(BaseModel):
    app_type: str
    title: str = ""
    detail: str = ""


@router.get("/applications")
async def list_applications(app_type: str = Query(default=""),
                            principal: dict = Depends(require_role("student")),
                            db: AsyncSession = Depends(get_db)):
    stu = await _me(principal, db)
    stmt = select(Application).where(Application.student_id == stu.id)
    if app_type:
        stmt = stmt.where(Application.app_type == app_type)
    rows = (await db.execute(stmt.order_by(Application.id.desc()))).scalars().all()
    return {"app_type": app_type,
            "items": [{"id": a.id, "type": a.app_type, "title": a.title, "detail": a.detail,
                       "status": a.status, "created_at": a.created_at.strftime("%Y-%m-%d %H:%M")}
                      for a in rows]}


@router.post("/applications")
async def create_application(data: ApplicationIn,
                             principal: dict = Depends(require_role("student")),
                             db: AsyncSession = Depends(get_db)):
    stu = await _me(principal, db)
    if not data.app_type:
        raise HTTPException(status_code=400, detail="请选择申请类型")
    db.add(Application(student_id=stu.id, app_type=data.app_type,
                       title=data.title or data.app_type, detail=data.detail, status="已提交"))
    await db.flush()
    return {"ok": True, "message": "「" + data.app_type + "」已提交，辅导员审核后可在本页查看进度。"}


# ---------------------------------------------------------------
# 17b.5 培养方案：八学期课程 + 已修学分
# ---------------------------------------------------------------
@router.get("/training-plan")
async def training_plan(principal: dict = Depends(require_role("student")),
                        db: AsyncSession = Depends(get_db)):
    stu = await _me(principal, db)
    grades = (await db.execute(select(Grade).where(Grade.student_id == stu.id))).scalars().all()
    earned = round(sum(g.credit for g in grades if g.score >= 60), 1)
    plan = [{"semester": s["semester"],
             "courses": [{"name": n, "credit": c} for n, c in s["courses"]],
             "credits": round(sum(c for _, c in s["courses"]), 1)} for s in TRAINING_PLAN]
    return {"plan": plan, "total_credits": total_credits(), "earned_credits": earned,
            "class_name": (await db.execute(select(ClassInfo.name).where(
                ClassInfo.id == stu.class_id))).scalar_one_or_none()}


# ---------------------------------------------------------------
# 17b.6 教材明细 / 费用 / 预订
# ---------------------------------------------------------------
@router.get("/textbooks")
async def textbooks(principal: dict = Depends(require_role("student")),
                    db: AsyncSession = Depends(get_db)):
    stu = await _me(principal, db)
    books = (await db.execute(select(Textbook))).scalars().all()
    ordered = {a.title for a in (await db.execute(select(Application).where(
        Application.student_id == stu.id, Application.app_type == "教材预订"))).scalars().all()}
    items = [{"id": b.id, "course": b.course_name, "name": b.name, "isbn": b.isbn,
              "publisher": b.publisher, "price": b.price, "status": b.status,
              "ordered": b.name in ordered} for b in books]
    return {"items": items, "total_fee": round(sum(b.price for b in books), 1),
            "ordered_fee": round(sum(i["price"] for i in items if i["ordered"]), 1)}


class TextbookOrderIn(BaseModel):
    textbook_ids: list[int] = Field(default_factory=list)


@router.post("/textbooks/order")
async def order_textbooks(data: TextbookOrderIn,
                          principal: dict = Depends(require_role("student")),
                          db: AsyncSession = Depends(get_db)):
    stu = await _me(principal, db)
    books = (await db.execute(select(Textbook))).scalars().all()
    enrolled = {e.course_name for e in (await db.execute(
        select(Enrollment).where(Enrollment.student_id == stu.id))).scalars().all()}
    picked = [b for b in books if not data.textbook_ids or b.id in data.textbook_ids]
    targets = [b for b in picked if b.course_name in enrolled]
    if not targets:
        return {"ok": False, "message": "这些教材对应的课程你还没选，先去「自主选课」选上再预订～"}
    for b in targets:
        db.add(Application(student_id=stu.id, app_type="教材预订", title=b.name,
                           detail=b.course_name + " 教材，¥" + str(b.price), status="已提交"))
        b.order_count += 1
    await db.flush()
    fee = round(sum(b.price for b in targets), 1)
    return {"ok": True, "count": len(targets), "fee": fee,
            "message": "已预订 " + str(len(targets)) + " 本教材，合计 ¥" + str(fee) + "，开学后到图书馆一层领取。"}


# ---------------------------------------------------------------
# 17b.7 自主选课
# ---------------------------------------------------------------
@router.get("/electives")
async def electives(principal: dict = Depends(require_role("student")),
                    db: AsyncSession = Depends(get_db)):
    stu = await _me(principal, db)
    mine = {(e.course_code, e.course_name) for e in (await db.execute(select(Enrollment).where(
        Enrollment.student_id == stu.id))).scalars().all()}
    items = []
    for e in ELECTIVES:
        selected = any(e["name"] in name for _, name in mine)
        items.append({**e, "selected": selected})
    return {"items": items, "selected_credit": round(sum(
        i["credit"] for i in items if i["selected"]), 1)}


class ElectiveIn(BaseModel):
    course_name: str


def _parse_time(text: str) -> tuple[int, int, int] | None:
    """17b.7b 解析「周三第7-8节」-> (星期, 起始节, 结束节)。"""
    import re

    m = re.search(r"周([一二三四五])第?\s*(\d+)\s*-\s*(\d+)", text or "")
    if not m:
        return None
    day = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5}[m.group(1)]
    return day, int(m.group(2)), int(m.group(3))


@router.post("/electives/select")
async def select_elective(data: ElectiveIn,
                          principal: dict = Depends(require_role("student")),
                          db: AsyncSession = Depends(get_db)):
    stu = await _me(principal, db)
    course = next((e for e in ELECTIVES if e["name"] == data.course_name), None)
    if not course:
        return {"ok": False, "message": "没有找到这门选修课，请刷新页面重试。"}
    exists = (await db.execute(select(Enrollment).where(
        Enrollment.student_id == stu.id, Enrollment.course_name == course["name"]))).scalars().first()
    if exists:
        return {"ok": True, "message": "你已经选过《" + course["name"] + "》啦～"}

    # 容量校验：统计已选同一门选修课的人数
    picked = len((await db.execute(select(Enrollment).where(
        Enrollment.course_name == course["name"]))).scalars().all())
    if picked >= int(course.get("capacity", 999)):
        return {"ok": False, "message": "《" + course["name"] + "》已经选满了（" + str(picked)
                                        + "/" + str(course["capacity"]) + "），换一门试试呀～"}

    # 时间冲突校验：与本学期课表比较星期与节次
    slot = _parse_time(course.get("time", ""))
    if slot:
        day, start, end = slot
        table = (await db.execute(select(TimetableEntry).where(
            TimetableEntry.class_id == stu.class_id,
            TimetableEntry.weekday == day))).scalars().all()
        for e in table:
            if not (end < e.start_section or start > e.end_section):
                return {"ok": False, "message": "时间冲突啦：《" + course["name"] + "》是 " + course["time"]
                                                + "，和你的《" + e.course_name + "》（第" + str(e.start_section)
                                                + "-" + str(e.end_section) + "节）重叠了。"}

    db.add(Enrollment(student_id=stu.id, course_code=course["code"], course_name=course["name"],
                      credit=course["credit"], semester="2024-2025-2", status="已选课"))
    await db.flush()
    return {"ok": True, "message": "选课成功：《" + course["name"] + "》" + str(course["credit"])
                                   + " 学分，" + course["time"] + "，" + course["location"]}


# ---------------------------------------------------------------
# 17b.8 学业情况 + 选课名单
# ---------------------------------------------------------------
@router.get("/academic-status")
async def academic_status(principal: dict = Depends(require_role("student")),
                          db: AsyncSession = Depends(get_db)):
    stu = await _me(principal, db)
    grades = (await db.execute(select(Grade).where(Grade.student_id == stu.id))).scalars().all()
    earned = round(sum(g.credit for g in grades if g.score >= 60), 1)
    total = round(sum(g.credit for g in grades), 1)
    gpa = round(sum(grade_point(g.score) * g.credit for g in grades) / total, 2) if total else 0
    failed_credits = round(sum(g.credit for g in grades if g.score < 60), 1)
    if failed_credits >= 12:
        warning = "累计不及格 " + str(failed_credits) + " 学分，已触发学业预警，请联系辅导员"
    elif failed_credits >= 6:
        warning = "本学期不及格 " + str(failed_credits) + " 学分，接近预警线，建议尽快补考"
    else:
        warning = "暂无学业预警，状态良好"
    return {"earned_credits": earned, "total_credits": total, "gpa": gpa,
            "failed_credits": failed_credits, "warning": warning,
            "need_credits": round(max(0, total_credits() - earned), 1)}


@router.get("/selection-list")
async def selection_list(principal: dict = Depends(require_role("student")),
                         db: AsyncSession = Depends(get_db)):
    stu = await _me(principal, db)
    mates = (await db.execute(select(Student).where(Student.class_id == stu.class_id))).scalars().all()
    rows = (await db.execute(select(Enrollment))).scalars().all()
    by_student: dict[int, list[str]] = {}
    for e in rows:
        by_student.setdefault(e.student_id, []).append(e.course_name)
    items = [{"sno": s.sno, "name": s.name, "courses": by_student.get(s.id, [])} for s in mates]
    return {"class_count": len(mates), "items": items}
