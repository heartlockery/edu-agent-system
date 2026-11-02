"""
模块 25 · 管理员端接口（无 AI 能力）
--------------------------------------------------------------------
作用：学生/教师账号的增删查、重置密码、处理「账号找回」申请、数据总览。
      管理员系统刻意不接入大模型：账号与权限操作必须可审计、可回滚。
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import DEFAULT_PASSWORD
from app.config import DATA_DIR
from app.db.models import (
    Admin,
    Application,
    ClassInfo,
    Grade,
    Message,
    RecoveryRequest,
    Student,
    Teacher,
    TimetableEntry,
)
from app.db.session import get_db
from app.security import hash_password, require_role
from app.services.registry import menu_for

router = APIRouter(prefix="/api/admin", tags=["管理员"])


# ---------------------------------------------------------------
# 19.1 请求模型
# ---------------------------------------------------------------
class StudentCreateIn(BaseModel):
    sno: str
    name: str
    class_name: str = "数据科学2401"
    gender: str = "男"
    phone: str = ""
    email: str = ""
    password: str = DEFAULT_PASSWORD


class TeacherCreateIn(BaseModel):
    tno: str
    name: str
    title: str = "讲师"
    dept: str = "计算机学院"
    phone: str = ""
    email: str = ""
    password: str = DEFAULT_PASSWORD


class RecoveryIn(BaseModel):
    """免登录提交找回申请（放在 auth 路由也行，这里统一放管理员域）。"""

    role: str = Field(default="student")
    name: str
    class_name: str = ""
    contact: str = ""
    request_type: str = "找回账号"
    reason: str = ""


class HandleIn(BaseModel):
    action: str = Field(default="approve", description="approve 或 reject")
    admin_note: str = ""
    new_password: str = DEFAULT_PASSWORD


@router.get("/menu")
async def menu(principal: dict = Depends(require_role("admin"))):
    return {"role": "admin", "menus": menu_for("admin")}


@router.get("/stats")
async def stats(principal: dict = Depends(require_role("admin")), db: AsyncSession = Depends(get_db)):
    """19.2 数据总览：一眼看出库里的规模，方便验收。"""
    async def count(model):
        return (await db.execute(select(func.count()).select_from(model))).scalar_one()

    pending = (await db.execute(select(func.count()).select_from(RecoveryRequest)
                               .where(RecoveryRequest.status == "待处理"))).scalar_one()
    pending_app = (await db.execute(select(func.count()).select_from(Application)
                                    .where(Application.status == "已提交"))).scalar_one()
    return {"students": await count(Student), "teachers": await count(Teacher),
            "classes": await count(ClassInfo), "grades": await count(Grade),
            "timetable": await count(TimetableEntry), "pending_recovery": pending,
            "pending_applications": pending_app}


# ---------------------------------------------------------------
# 19.3 学生账号管理
# ---------------------------------------------------------------
@router.get("/students")
async def list_students(keyword: str = Query(default=""), class_name: str = Query(default=""),
                        principal: dict = Depends(require_role("admin")),
                        db: AsyncSession = Depends(get_db)):
    stmt = select(Student, ClassInfo.name).join(ClassInfo, ClassInfo.id == Student.class_id)
    if keyword:
        stmt = stmt.where((Student.sno.contains(keyword)) | (Student.name.contains(keyword)))
    if class_name:
        stmt = stmt.where(ClassInfo.name.contains(class_name))
    rows = (await db.execute(stmt.limit(500))).all()
    return {"items": [{"sno": s.sno, "name": s.name, "gender": s.gender, "class_name": cn,
                       "phone": s.phone, "email": s.email} for s, cn in rows], "total": len(rows)}


@router.post("/students")
async def create_student(data: StudentCreateIn, principal: dict = Depends(require_role("admin")),
                         db: AsyncSession = Depends(get_db)):
    if (await db.execute(select(Student).where(Student.sno == data.sno))).scalars().first():
        raise HTTPException(status_code=400, detail="学号已存在")
    klass = (await db.execute(select(ClassInfo).where(ClassInfo.name == data.class_name))).scalars().first()
    if not klass:
        raise HTTPException(status_code=400, detail="班级不存在，请先选择已有班级")
    db.add(Student(sno=data.sno, name=data.name, gender=data.gender, class_id=klass.id,
                   major=klass.major, enroll_year=klass.grade, phone=data.phone, email=data.email,
                   password_hash=hash_password(data.password)))
    await db.flush()
    return {"ok": True, "message": "已创建学生账号 " + data.sno + "，初始密码 " + data.password}


@router.delete("/students/{sno}")
async def delete_student(sno: str, principal: dict = Depends(require_role("admin")),
                         db: AsyncSession = Depends(get_db)):
    stu = (await db.execute(select(Student).where(Student.sno == sno))).scalars().first()
    if not stu:
        raise HTTPException(status_code=404, detail="学生不存在")
    await db.delete(stu)
    await db.flush()
    return {"ok": True, "message": "已删除学生 " + sno}


@router.post("/students/{sno}/reset-password")
async def reset_student_password(sno: str, principal: dict = Depends(require_role("admin")),
                                 db: AsyncSession = Depends(get_db)):
    stu = (await db.execute(select(Student).where(Student.sno == sno))).scalars().first()
    if not stu:
        raise HTTPException(status_code=404, detail="学生不存在")
    stu.password_hash = hash_password(DEFAULT_PASSWORD)
    await db.flush()
    return {"ok": True, "message": "已将 " + sno + " 的密码重置为 " + DEFAULT_PASSWORD}


@router.post("/students/import")
async def import_students(file: UploadFile = File(...),
                          principal: dict = Depends(require_role("admin")),
                          db: AsyncSession = Depends(get_db)):
    """19.3b 批量导入学生账号：Excel 表头 学号/姓名/班级/性别/手机/邮箱。

    已存在的学号跳过；班级不存在则记入错误列表（不自动建班，避免脏数据）。
    """
    from openpyxl import load_workbook

    raw = await file.read()
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件超过 5MB")
    tmp = DATA_DIR / "uploads"
    tmp.mkdir(parents=True, exist_ok=True)
    path = tmp / ("import_students_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".xlsx")
    path.write_bytes(raw)

    try:
        ws = load_workbook(filename=str(path), data_only=True).active
        rows = list(ws.iter_rows(values_only=True))
    except Exception:
        raise HTTPException(status_code=400, detail="无法解析该文件，请使用 .xlsx 模板")
    if not rows:
        raise HTTPException(status_code=400, detail="文件是空的")

    classes = {c.name: c for c in (await db.execute(select(ClassInfo))).scalars().all()}
    created, skipped = 0, 0
    errors: list[str] = []
    for row in rows[1:]:
        if not row or row[0] is None:
            continue
        sno = str(row[0]).strip()
        name = str(row[1]).strip() if len(row) > 1 and row[1] else ""
        cname = str(row[2]).strip() if len(row) > 2 and row[2] else ""
        gender = str(row[3]).strip() if len(row) > 3 and row[3] else "男"
        phone = str(row[4]).strip() if len(row) > 4 and row[4] else ""
        email = str(row[5]).strip() if len(row) > 5 and row[5] else ""
        if not sno or not name:
            errors.append("第 " + str(len(errors) + 2) + " 行缺少学号或姓名")
            continue
        if (await db.execute(select(Student).where(Student.sno == sno))).scalars().first():
            skipped += 1
            continue
        if cname not in classes:
            errors.append(sno + " 的班级「" + cname + "」不存在")
            continue
        klass = classes[cname]
        db.add(Student(sno=sno, name=name, gender=gender, class_id=klass.id,
                       major=klass.major, enroll_year=klass.grade, phone=phone, email=email,
                       password_hash=hash_password(DEFAULT_PASSWORD)))
        created += 1
    await db.flush()
    return {"ok": True, "created": created, "skipped": skipped, "errors": errors[:10],
            "message": "导入完成：新增 " + str(created) + " 人，跳过已存在 " + str(skipped)
                       + " 人" + ("，" + str(len(errors)) + " 条异常" if errors else "")}


# ---------------------------------------------------------------
# 19.4 教师账号管理
# ---------------------------------------------------------------
@router.get("/teachers")
async def list_teachers(principal: dict = Depends(require_role("admin")),
                        db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Teacher))).scalars().all()
    return {"items": [{"tno": t.tno, "name": t.name, "title": t.title, "dept": t.dept,
                       "phone": t.phone, "email": t.email} for t in rows]}


@router.post("/teachers")
async def create_teacher(data: TeacherCreateIn, principal: dict = Depends(require_role("admin")),
                         db: AsyncSession = Depends(get_db)):
    if (await db.execute(select(Teacher).where(Teacher.tno == data.tno))).scalars().first():
        raise HTTPException(status_code=400, detail="工号已存在")
    db.add(Teacher(tno=data.tno, name=data.name, title=data.title, dept=data.dept,
                   phone=data.phone, email=data.email, password_hash=hash_password(data.password)))
    await db.flush()
    return {"ok": True, "message": "已创建教师账号 " + data.tno}


@router.delete("/teachers/{tno}")
async def delete_teacher(tno: str, principal: dict = Depends(require_role("admin")),
                         db: AsyncSession = Depends(get_db)):
    t = (await db.execute(select(Teacher).where(Teacher.tno == tno))).scalars().first()
    if not t:
        raise HTTPException(status_code=404, detail="教师不存在")
    await db.delete(t)
    await db.flush()
    return {"ok": True, "message": "已删除教师 " + tno}


@router.post("/teachers/{tno}/reset-password")
async def reset_teacher_password(tno: str, principal: dict = Depends(require_role("admin")),
                                 db: AsyncSession = Depends(get_db)):
    t = (await db.execute(select(Teacher).where(Teacher.tno == tno))).scalars().first()
    if not t:
        raise HTTPException(status_code=404, detail="教师不存在")
    t.password_hash = hash_password(DEFAULT_PASSWORD)
    await db.flush()
    return {"ok": True, "message": "已将 " + tno + " 的密码重置为 " + DEFAULT_PASSWORD}


# ---------------------------------------------------------------
# 19.5 找回申请：列表 + 处理（通过=重置为默认密码并回填学号）
# ---------------------------------------------------------------
@router.get("/recovery")
async def list_recovery(status: str = Query(default=""),
                        principal: dict = Depends(require_role("admin")),
                        db: AsyncSession = Depends(get_db)):
    stmt = select(RecoveryRequest)
    if status:
        stmt = stmt.where(RecoveryRequest.status == status)
    rows = (await db.execute(stmt.order_by(RecoveryRequest.id.desc()))).scalars().all()
    return {"items": [{"id": r.id, "role": r.role, "name": r.name, "class_name": r.class_name,
                       "sno": r.sno, "request_type": r.request_type, "contact": r.contact,
                       "reason": r.reason, "status": r.status, "note": r.admin_note,
                       "created_at": r.created_at.strftime("%Y-%m-%d %H:%M")} for r in rows]}


@router.post("/recovery/{req_id}/handle")
async def handle_recovery(req_id: int, data: HandleIn,
                          principal: dict = Depends(require_role("admin")),
                          db: AsyncSession = Depends(get_db)):
    """19.6 处理申请：通过则按「姓名 + 班级」定位账号并重置密码。"""
    req = (await db.execute(select(RecoveryRequest).where(RecoveryRequest.id == req_id))).scalars().first()
    if not req:
        raise HTTPException(status_code=404, detail="申请不存在")
    if req.status != "待处理":
        raise HTTPException(status_code=400, detail="该申请已处理")

    if data.action == "reject":
        req.status = "已驳回"
        req.admin_note = data.admin_note or "信息不匹配，请携带学生证到教务处核实"
        req.handled_at = datetime.now()
        await db.flush()
        return {"ok": True, "message": "已驳回该申请"}

    if req.role == "teacher":
        target = (await db.execute(select(Teacher).where(Teacher.name == req.name))).scalars().first()
    else:
        stmt = (select(Student).join(ClassInfo, ClassInfo.id == Student.class_id)
                .where(Student.name == req.name))
        if req.class_name:
            stmt = stmt.where(ClassInfo.name.contains(req.class_name[-4:]))
        target = (await db.execute(stmt)).scalars().first()

    if not target:
        req.status = "已驳回"
        req.admin_note = "按姓名与班级未匹配到账号，请核对后重新提交"
        req.handled_at = datetime.now()
        await db.flush()
        return {"ok": False, "message": "未匹配到账号，已标记驳回"}

    target.password_hash = hash_password(data.new_password or DEFAULT_PASSWORD)
    req.sno = target.sno if req.role == "student" else target.tno
    req.status = "已处理"
    req.admin_note = data.admin_note or ("已重置为默认密码 " + (data.new_password or DEFAULT_PASSWORD))
    req.handled_at = datetime.now()
    await db.flush()
    return {"ok": True, "account": req.sno, "password": data.new_password or DEFAULT_PASSWORD,
            "message": "已重置 " + req.name + " 的账号 " + req.sno + "，密码 " + (data.new_password or DEFAULT_PASSWORD)}


# ---------------------------------------------------------------
# 19.5b 班级概览：各班人数、平均分、及格率，供管理员一眼看全局
# ---------------------------------------------------------------
@router.get("/classes-overview")
async def classes_overview(principal: dict = Depends(require_role("admin")),
                           db: AsyncSession = Depends(get_db)):
    from collections import defaultdict

    rows = (await db.execute(
        select(ClassInfo.name, Student.sno, Grade.score, Grade.credit)
        .join(Student, Student.class_id == ClassInfo.id)
        .outerjoin(Grade, Grade.student_id == Student.id))).all()
    buckets: dict[str, dict] = {}
    for cname, sno, score, credit in rows:
        b = buckets.setdefault(cname, {"class_name": cname, "students": set(),
                                       "scores": [], "credits": 0.0})
        b["students"].add(sno)
        if score is not None:
            b["scores"].append(float(score))
            b["credits"] += float(credit or 0)
    items = []
    for b in buckets.values():
        scores = b["scores"]
        items.append({
            "class_name": b["class_name"],
            "students": len(b["students"]),
            "avg": round(sum(scores) / len(scores), 1) if scores else 0,
            "pass_rate": round(len([s for s in scores if s >= 60]) / len(scores) * 100, 1) if scores else 0,
            "failed": len([s for s in scores if s < 60]),
            "credits": round(b["credits"], 1),
        })
    items.sort(key=lambda x: x["class_name"])
    return {"items": items}


# ---------------------------------------------------------------
# 19.6b 学生申请审批（补考确认/学分认定/教材预订等）
# ---------------------------------------------------------------
@router.get("/applications")
async def list_applications(status: str = Query(default=""), app_type: str = Query(default=""),
                            principal: dict = Depends(require_role("admin")),
                            db: AsyncSession = Depends(get_db)):
    stmt = (select(Application, Student.name, Student.sno, ClassInfo.name)
            .join(Student, Student.id == Application.student_id)
            .join(ClassInfo, ClassInfo.id == Student.class_id))
    if status:
        stmt = stmt.where(Application.status == status)
    if app_type:
        stmt = stmt.where(Application.app_type.contains(app_type))
    rows = (await db.execute(stmt.order_by(Application.id.desc()).limit(300))).all()
    return {"items": [{"id": a.id, "type": a.app_type, "title": a.title, "detail": a.detail,
                       "status": a.status, "name": sname, "sno": sno, "class_name": cname,
                       "created_at": a.created_at.strftime("%Y-%m-%d %H:%M")}
                      for a, sname, sno, cname in rows]}


class ApplicationHandleIn(BaseModel):
    action: str = Field(default="approve", description="approve / reject")
    note: str = ""


@router.post("/applications/{app_id}/handle")
async def handle_application(app_id: int, data: ApplicationHandleIn,
                             principal: dict = Depends(require_role("admin")),
                             db: AsyncSession = Depends(get_db)):
    """审批学生申请：通过/驳回，并给学生发一条站内消息。"""
    app = (await db.execute(select(Application).where(Application.id == app_id))).scalars().first()
    if not app:
        raise HTTPException(status_code=404, detail="申请不存在")
    if app.status not in ("已提交", "审核中"):
        raise HTTPException(status_code=400, detail="该申请已处理")
    stu = (await db.execute(select(Student).where(Student.id == app.student_id))).scalars().first()
    ok = data.action == "approve"
    app.status = "已通过" if ok else "已驳回"
    db.add(Message(sender_role="teacher", sender_id="admin", sender_name="教务处",
                   receiver_role="student", receiver_id=stu.sno if stu else "",
                   title="申请" + app.status, content="你的「" + app.app_type + "」申请"
                   + ("已通过" if ok else "被驳回") + ("：" + data.note if data.note else "")))
    await db.flush()
    return {"ok": True, "status": app.status, "message": "已" + ("通过" if ok else "驳回") + "该申请"}


# ---------------------------------------------------------------
# 19.7 免登录的找回申请提交（学生/教师忘记账号时用）
# ---------------------------------------------------------------
recovery_router = APIRouter(prefix="/api/auth", tags=["认证"])


@recovery_router.post("/recovery")
async def submit_recovery(data: RecoveryIn, db: AsyncSession = Depends(get_db)):
    db.add(RecoveryRequest(role=data.role, name=data.name, class_name=data.class_name,
                           request_type=data.request_type, contact=data.contact,
                           reason=data.reason, status="待处理"))
    await db.flush()
    return {"ok": True, "message": "申请已提交，管理员处理后会重置为默认密码 " + DEFAULT_PASSWORD
                                   + "，请用学号登录后立即修改密码。"}
