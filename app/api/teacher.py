"""
模块 23 · 教师端接口
--------------------------------------------------------------------
作用：发送通知/消息、查询班级与学生成绩、上传桌面 Excel 成绩表、导出成绩文件、
      我的课表、会议安排、调课申请。教师端的写操作与 AI 工具共用同一套表。
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import DATA_DIR, EXPORT_DIR
from app.db.models import (
    ClassInfo,
    Course,
    Grade,
    Meeting,
    Message,
    Notification,
    ScheduleChangeRequest,
    Student,
    Teacher,
    TimetableEntry,
)
from app.db.session import get_db
from app.schemas import MessageIn, NotificationIn, ScheduleChangeIn
from app.security import require_role
from app.services.grades import export_grades_async, parse_grade_workbook, summarize
from app.services.registry import menu_for

router = APIRouter(prefix="/api/teacher", tags=["教师端"])


async def _me(principal: dict, db: AsyncSession) -> Teacher:
    row = (await db.execute(select(Teacher).where(Teacher.tno == principal["username"]))).scalars().first()
    if not row:
        raise HTTPException(status_code=404, detail="教师不存在")
    return row


async def _class_by_name(db: AsyncSession, class_name: str) -> ClassInfo | None:
    """18.1 班级名解析：既支持全名，也支持「2401」这种简写。"""
    if not class_name:
        return None
    key = class_name.strip()
    if key.isdigit() and len(key) == 4:
        key = "数据科学" + key
    rows = (await db.execute(select(ClassInfo))).scalars().all()
    for k in rows:
        if key in k.name or k.name in key:
            return k
    return None


async def _collect_rows(db: AsyncSession, class_name: str = "", course_name: str = "",
                        sno: str = "") -> list[dict]:
    """18.2 汇总「学生 + 课程 + 分数」，供查询/导出/分析复用。"""
    stmt = (select(Student.sno, Student.name, ClassInfo.name, Grade.course_name,
                   Grade.course_code, Grade.score, Grade.credit, Grade.semester)
            .join(Grade, Grade.student_id == Student.id)
            .join(ClassInfo, ClassInfo.id == Student.class_id))
    klass = await _class_by_name(db, class_name)
    if klass:
        stmt = stmt.where(ClassInfo.id == klass.id)
    if sno:
        stmt = stmt.where(Student.sno == sno)
    if course_name:
        stmt = stmt.where(Grade.course_name.contains(course_name))
    rows = (await db.execute(stmt)).all()

    buckets: dict[str, dict] = {}
    for r in rows:
        bucket = buckets.setdefault(r[0], {"sno": r[0], "name": r[1], "class_name": r[2],
                                           "grades": {}, "credits": {}})
        bucket["grades"][r[3]] = r[5]
        bucket["credits"][r[3]] = r[6]
    return list(buckets.values())


@router.get("/menu")
async def menu(principal: dict = Depends(require_role("teacher"))):
    return {"role": "teacher", "menus": menu_for("teacher")}


@router.get("/profile")
async def profile(principal: dict = Depends(require_role("teacher")), db: AsyncSession = Depends(get_db)):
    t = await _me(principal, db)
    return {"tno": t.tno, "name": t.name, "title": t.title, "dept": t.dept,
            "research": t.research, "phone": t.phone, "email": t.email}


@router.get("/classes")
async def classes(principal: dict = Depends(require_role("teacher")), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(ClassInfo))).scalars().all()
    out = []
    for c in rows:
        count = len((await db.execute(select(Student.id).where(Student.class_id == c.id))).scalars().all())
        out.append({"id": c.id, "name": c.name, "grade": c.grade, "major": c.major,
                    "advisor": c.advisor, "student_count": count})
    return {"items": out}


@router.get("/students")
async def students(class_name: str = Query(default=""),
                   principal: dict = Depends(require_role("teacher")),
                   db: AsyncSession = Depends(get_db)):
    """18.3 学生名单（可按班级过滤）。"""
    klass = await _class_by_name(db, class_name)
    stmt = select(Student, ClassInfo.name).join(ClassInfo, ClassInfo.id == Student.class_id)
    if klass:
        stmt = stmt.where(Student.class_id == klass.id)
    rows = (await db.execute(stmt)).all()
    return {"items": [{"sno": s.sno, "name": s.name, "gender": s.gender, "class_name": cn,
                       "phone": s.phone, "email": s.email} for s, cn in rows], "total": len(rows)}


@router.get("/grades")
async def grades(class_name: str = Query(default=""), course_name: str = Query(default=""),
                 sno: str = Query(default=""),
                 principal: dict = Depends(require_role("teacher")),
                 db: AsyncSession = Depends(get_db)):
    rows = await _collect_rows(db, class_name, course_name, sno)
    return {"items": rows, "stats": summarize(rows)}


@router.get("/grades/analysis")
async def analysis(class_name: str = Query(default=""),
                   principal: dict = Depends(require_role("teacher")),
                   db: AsyncSession = Depends(get_db)):
    """18.4 班级成绩分析：按课程输出平均分/及格率/最高最低。"""
    rows = await _collect_rows(db, class_name)
    by_course: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        for course, score in r["grades"].items():
            by_course[course].append(float(score))
    items = []
    for course, scores in by_course.items():
        items.append({"course": course, "avg": round(sum(scores) / len(scores), 1),
                      "pass_rate": round(len([s for s in scores if s >= 60]) / len(scores) * 100, 1),
                      "max": max(scores), "min": min(scores), "count": len(scores)})
    return {"items": items, "students": len(rows)}


@router.get("/timetable")
async def timetable(weekday: int = Query(default=0, ge=0, le=5),
                    principal: dict = Depends(require_role("teacher")),
                    db: AsyncSession = Depends(get_db)):
    """18.5 我的课程表。"""
    stmt = select(TimetableEntry).where(TimetableEntry.teacher_tno == principal["username"])
    if weekday:
        stmt = stmt.where(TimetableEntry.weekday == weekday)
    rows = (await db.execute(stmt.order_by(TimetableEntry.weekday, TimetableEntry.start_section))).scalars().all()
    class_map = {c.id: c.name for c in (await db.execute(select(ClassInfo))).scalars().all()}
    return {"items": [{"weekday": e.weekday, "course": e.course_name, "class_name": class_map.get(e.class_id, ""),
                       "start": e.start_section, "end": e.end_section, "location": e.location,
                       "weeks": e.weeks} for e in rows]}


@router.get("/meetings")
async def meetings(principal: dict = Depends(require_role("teacher")), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Meeting).where(Meeting.teacher_tno == principal["username"])
                             .order_by(Meeting.start_time))).scalars().all()
    return {"items": [{"title": m.title, "start_time": m.start_time, "location": m.location,
                       "content": m.content} for m in rows]}


@router.post("/notifications")
async def send_notification(data: NotificationIn,
                            principal: dict = Depends(require_role("teacher")),
                            db: AsyncSession = Depends(get_db)):
    """18.6 发通知：同时给目标班级每个学生写一条站内消息。"""
    t = await _me(principal, db)
    klass = await _class_by_name(db, data.class_name or "")
    db.add(Notification(title=data.title, content=data.content or data.title,
                        category=data.category, sender_tno=t.tno, sender_name=t.name,
                        target_class_id=klass.id if klass else None))
    stmt = select(Student)
    if klass:
        stmt = stmt.where(Student.class_id == klass.id)
    targets = (await db.execute(stmt)).scalars().all()
    for s in targets:
        db.add(Message(sender_role="teacher", sender_id=t.tno, sender_name=t.name,
                       receiver_role="student", receiver_id=s.sno,
                       title=data.title, content=data.content or data.title))
    await db.flush()
    return {"ok": True, "scope": klass.name if klass else "全体学生", "count": len(targets)}


@router.post("/messages")
async def send_message(data: MessageIn,
                       principal: dict = Depends(require_role("teacher")),
                       db: AsyncSession = Depends(get_db)):
    """18.7 点对点消息。"""
    t = await _me(principal, db)
    stu = (await db.execute(select(Student).where(Student.sno == data.sno))).scalars().first()
    if not stu:
        raise HTTPException(status_code=404, detail="学号不存在")
    db.add(Message(sender_role="teacher", sender_id=t.tno, sender_name=t.name,
                   receiver_role="student", receiver_id=stu.sno,
                   title=data.title or "教师消息", content=data.content))
    await db.flush()
    return {"ok": True, "message": "已发送给 " + stu.name}


@router.get("/messages")
async def inbox(principal: dict = Depends(require_role("teacher")), db: AsyncSession = Depends(get_db)):
    """18.8 教师收到的消息（例如同事的互换调课申请）。"""
    rows = (await db.execute(
        select(Message).where(Message.receiver_id == principal["username"])
        .order_by(Message.id.desc()))).scalars().all()
    return {"items": [{"id": m.id, "title": m.title, "content": m.content, "sender": m.sender_name,
                       "created_at": m.created_at.strftime("%Y-%m-%d %H:%M")} for m in rows]}


@router.get("/grades/template")
async def grade_template(principal: dict = Depends(require_role("teacher")),
                         db: AsyncSession = Depends(get_db)):
    """18.9 下载成绩上传模板（表头与解析逻辑严格一致，避免格式踩坑）。"""
    courses = (await db.execute(select(Course).where(Course.semester == "2024-2025-1"))).scalars().all()
    if not courses:
        courses = (await db.execute(select(Course))).scalars().all()
    headers = [c.name for c in courses]
    rows = [{"sno": "2024010101", "name": "示例学生", "class_name": "数据科学2401",
             "grades": {h: 85 for h in headers}}]
    path = await export_grades_async(rows, headers, filename="成绩上传模板.xlsx")
    return FileResponse(path, filename=path.name)


@router.post("/grades/upload")
async def upload_grades(file: UploadFile = File(...),
                        principal: dict = Depends(require_role("teacher")),
                        db: AsyncSession = Depends(get_db)):
    """18.10 上传成绩 Excel：落盘 -> 解析 -> 按学号+课程 upsert 进数据库。"""
    if not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="只支持 .xlsx 文件")
    raw = await file.read()
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件超过 5MB，请拆分后再上传")
    upload_dir = DATA_DIR / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / (datetime.now().strftime("%Y%m%d_%H%M%S_") + file.filename)
    dest.write_bytes(raw)

    records, course_names = await asyncio.to_thread(parse_grade_workbook, dest)
    if not records:
        raise HTTPException(status_code=400, detail="解析不到成绩数据，请确认表头为 学号/姓名/班级/课程...")

    course_map = {c.name: c for c in (await db.execute(select(Course).where(Course.name.in_(course_names)))).scalars().all()}
    teacher = await _me(principal, db)
    touched_students, touched_records = 0, 0

    for rec in records:
        stu = (await db.execute(select(Student).where(Student.sno == rec["sno"]))).scalars().first()
        if not stu:
            continue
        touched_students += 1
        for course_name, score in rec["grades"].items():
            course = course_map.get(course_name)
            code = course.code if course else course_name
            credit = course.credit if course else 3.0
            exists = (await db.execute(select(Grade).where(
                Grade.student_id == stu.id, Grade.course_code == code,
                Grade.semester == "2024-2025-1"))).scalars().first()
            if exists:
                exists.score = score
                exists.source = "教师上传"
            else:
                db.add(Grade(student_id=stu.id, course_code=code, course_name=course_name,
                             credit=credit, score=score, semester="2024-2025-1",
                             source="教师上传"))
            touched_records += 1
    await db.flush()
    return {"ok": True, "file": dest.name, "students": touched_students,
            "records": touched_records, "courses": course_names,
            "message": "已导入 " + str(touched_students) + " 名学生、" + str(touched_records) + " 条成绩"}


@router.get("/grades/export")
async def export_grades(class_name: str = Query(default=""), course_name: str = Query(default=""),
                        principal: dict = Depends(require_role("teacher")),
                        db: AsyncSession = Depends(get_db)):
    """18.11 导出成绩 Excel，浏览器直接下载。"""
    rows = await _collect_rows(db, class_name, course_name)
    if not rows:
        raise HTTPException(status_code=404, detail="没有可导出的数据")
    courses = sorted({c for r in rows for c in r["grades"]})
    label = class_name or "全部班级"
    path = await export_grades_async(rows, courses,
                                     filename="成绩_" + label + "_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".xlsx")
    return FileResponse(path, filename=path.name)


@router.post("/schedule/change")
async def schedule_change(data: ScheduleChangeIn,
                          principal: dict = Depends(require_role("teacher")),
                          db: AsyncSession = Depends(get_db)):
    """18.12 调课申请：单独调课 / 教师互换（互换时给对方发消息）。"""
    t = await _me(principal, db)
    db.add(ScheduleChangeRequest(teacher_tno=t.tno, teacher_name=t.name,
                                 change_type=data.change_type, course_name=data.course_name,
                                 from_slot=data.from_slot, to_slot=data.to_slot,
                                 target_tno=data.target_tno, reason=data.reason, status="待审批"))
    if data.change_type == "教师互换调课" and data.target_tno:
        target = (await db.execute(select(Teacher).where(Teacher.tno == data.target_tno))).scalars().first()
        db.add(Message(sender_role="teacher", sender_id=t.tno, sender_name=t.name,
                       receiver_role="teacher", receiver_id=data.target_tno,
                       title="调课申请通知",
                       content=t.name + " 申请与你互换《" + data.course_name + "》课程，原时间 "
                               + data.from_slot + "，拟调整到 " + data.to_slot + "，请审批。"))
        await db.flush()
        return {"ok": True, "status": "待审批", "target": target.name if target else data.target_tno,
                "message": "互换申请已提交，并已通知 " + (target.name if target else data.target_tno)}
    await db.flush()
    return {"ok": True, "status": "待审批", "message": "调课申请已提交"}


@router.get("/schedule/requests")
async def schedule_requests(principal: dict = Depends(require_role("teacher")),
                            db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(ScheduleChangeRequest)
                             .where(ScheduleChangeRequest.teacher_tno == principal["username"])
                             .order_by(ScheduleChangeRequest.id.desc()))).scalars().all()
    return {"items": [{"id": r.id, "type": r.change_type, "course": r.course_name,
                       "from": r.from_slot, "to": r.to_slot, "status": r.status,
                       "created_at": r.created_at.strftime("%Y-%m-%d %H:%M")} for r in rows]}
