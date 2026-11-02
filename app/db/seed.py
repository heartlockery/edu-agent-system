"""
模块 28 · 种子数据导入
--------------------------------------------------------------------
作用：首次启动时把「班级、学生(180)、教师(5)、课程(7)、课表、成绩 Excel、
      通知、消息、会议、选课、找回申请」灌进数据库，保证打开就能演示。
数据来源：data/*.json 由 scripts/gen_data.py 生成；
          成绩优先读 data 目录下的 Excel，顺便验证「教师上传成绩」的解析链路。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy import func, select

from app.config import DATA_DIR
from app.db.models import (
    Admin,
    ClassInfo,
    Course,
    Enrollment,
    Grade,
    Meeting,
    Message,
    Notification,
    Proctor,
    RecoveryRequest,
    Student,
    Teacher,
    Textbook,
    TimetableEntry,
)
from app.services.curriculum import TEXTBOOKS
from app.db.session import SessionLocal
from app.security import hash_password
from app.services.grades import parse_grade_workbook

logger = logging.getLogger("seed")
DEFAULT_PASSWORD = "123456"

# 22.1 管理员账号：管理员不接入 AI，只做账号管理（账号/密码按需求指定）
ADMIN_ACCOUNT = {"ano": "10214823205", "name": "教务管理员", "role_desc": "系统管理员",
                 "password": "123456"}


def _load_json(name: str) -> list[dict]:
    path = DATA_DIR / name
    if not path.exists():
        logger.warning("缺少数据文件 %s，请先执行 python scripts/gen_data.py", path.name)
        return []
    return json.loads(path.read_text(encoding="utf-8"))


async def seed_if_empty() -> None:
    """22.2 只在库为空时导入，重复启动不会产生重复数据。"""
    async with SessionLocal() as db:
        exists = (await db.execute(select(func.count()).select_from(Student))).scalar_one()
        if exists:
            logger.info("数据库已有 %s 名学生，跳过种子导入", exists)
            return

        # 确保种子文件存在（没有就现场生成，降低首次运行门槛）
        if not (DATA_DIR / "students.json").exists():
            from scripts.gen_data import generate_all

            generate_all()

        # ---- 22.3 管理员 ----
        db.add(Admin(ano=ADMIN_ACCOUNT["ano"], name=ADMIN_ACCOUNT["name"],
                     role_desc=ADMIN_ACCOUNT["role_desc"],
                     password_hash=hash_password(ADMIN_ACCOUNT["password"])))

        # ---- 22.4 班级 + 教师 ----
        class_map: dict[str, ClassInfo] = {}
        for c in _load_json("classes.json"):
            obj = ClassInfo(name=c["name"], grade=c["grade"], major=c["major"], advisor=c["advisor"])
            db.add(obj)
            class_map[c["name"]] = obj

        teacher_map: dict[str, Teacher] = {}
        for t in _load_json("teachers.json"):
            obj = Teacher(tno=t["tno"], name=t["name"], title=t["title"], dept=t["dept"],
                          research=t.get("research", ""), phone=t.get("phone", ""),
                          email=t.get("email", ""), password_hash=hash_password(DEFAULT_PASSWORD))
            db.add(obj)
            teacher_map[t["tno"]] = obj
        await db.flush()          # 拿到自增主键

        # ---- 22.5 学生（60 人/班 × 3 班）----
        student_map: dict[str, Student] = {}
        for s in _load_json("students.json"):
            obj = Student(sno=s["sno"], name=s["name"], gender=s["gender"],
                          class_id=class_map[s["class_name"]].id, major=s["major"],
                          enroll_year=s["enroll_year"], phone=s.get("phone", ""),
                          email=s.get("email", ""), password_hash=hash_password(DEFAULT_PASSWORD))
            db.add(obj)
            student_map[s["sno"]] = obj
        await db.flush()

        # ---- 22.6 本学期课程（7 门 / 5 位教师）----
        course_map: dict[str, Course] = {}
        for c in _load_json("courses.json"):
            obj = Course(code=c["code"], name=c["name"], credit=c["credit"], hours=c["hours"],
                         category=c["category"], teacher_tno=c["teacher_tno"],
                         teacher_name=c["teacher_name"], semester=c["semester"])
            db.add(obj)
            course_map[c["code"]] = obj

        # ---- 22.7 课表（3 个班，每个班 6 个时段）----
        for e in _load_json("timetable.json"):
            db.add(TimetableEntry(class_id=class_map[e["class_name"]].id,
                                  course_code=e["course_code"], course_name=e["course_name"],
                                  teacher_tno=e["teacher_tno"], teacher_name=e["teacher_name"],
                                  weekday=e["weekday"], start_section=e["start_section"],
                                  end_section=e["end_section"], location=e["location"],
                                  weeks=e["weeks"], semester="2024-2025-2"))

        # ---- 22.8 上学期成绩：从 Excel 读，验证真实导入链路 ----
        last_courses = {c["name"]: c for c in _load_json("last_courses.json")}
        grade_file = next(iter(sorted(DATA_DIR.glob("成绩*.xlsx"))), None)
        if grade_file:
            records, _cols = parse_grade_workbook(grade_file)
            for rec in records:
                stu = student_map.get(rec["sno"])
                if not stu:
                    continue
                for course_name, score in rec["grades"].items():
                    meta = last_courses.get(course_name, {"code": course_name, "credit": 3.0})
                    db.add(Grade(student_id=stu.id, course_code=meta["code"], course_name=course_name,
                                 credit=meta["credit"], score=score, semester="2024-2025-1",
                                 exam_type="期末考试", source="系统导入"))
        else:
            logger.warning("未找到成绩 Excel，跳过成绩导入")

        # ---- 22.9 选课记录：本学期 7 门课全部已选 ----
        for sno, stu in student_map.items():
            for course in course_map.values():
                db.add(Enrollment(student_id=stu.id, course_code=course.code,
                                  course_name=course.name, credit=course.credit,
                                  semester="2024-2025-2", status="已选课"))

        # ---- 22.10 通知 / 消息 / 会议 ----
        db.add(Notification(title="2024-2025 学年第二学期开学通知",
                            content="2 月 24 日正式上课，请同学们按课表到课，教材在图书馆一层领取。",
                            category="教务通知", sender_name="教务处"))
        db.add(Notification(title="关于期中教学检查的通知",
                            content="第 9-10 周开展期中教学检查，请各班学习委员配合收集反馈。",
                            category="教务通知", sender_name="教务处"))
        db.add(Notification(title="程序设计基础课程调整",
                            content="本周四实验课调整到实验楼 C302，请带好学生卡。",
                            category="课程通知", sender_tno="T1001", sender_name="张伟",
                            target_class_id=class_map["数据科学2401"].id))

        for sno in list(student_map)[:12]:
            db.add(Message(sender_role="teacher", sender_id="T1001", sender_name="张伟",
                           receiver_role="student", receiver_id=sno, title="作业提醒",
                           content="第二次上机作业请在周五前提交到教学平台。"))
        db.add(Message(sender_role="teacher", sender_id="T1004", sender_name="陈晨",
                       receiver_role="student", receiver_id=list(student_map)[0], title="网络实验分组",
                       content="你被分在第三组，实验课请提前十分钟到实验室。"))

        db.add(Meeting(title="计算机学院教研活动", teacher_tno="T1001",
                       start_time="2025-03-12 14:30", location="学院楼 302",
                       content="讨论本学期课程改革与实验课安排"))
        db.add(Meeting(title="课程组集体备课", teacher_tno="T1001",
                       start_time="2025-03-19 09:00", location="学院楼 205", content="数据结构期中命题"))
        db.add(Meeting(title="学生工作例会", teacher_tno="T1002",
                       start_time="2025-03-13 10:00", location="行政楼 501", content="学业预警学生帮扶"))
        db.add(Meeting(title="思政课集体备课", teacher_tno="T1005",
                       start_time="2025-03-14 15:00", location="文科楼 108", content="专题教学研讨"))

        # ---- 22.10b 教材与监考任务 ----
        for b in TEXTBOOKS:
            db.add(Textbook(course_code=b["course_code"], course_name=b["course_name"],
                            name=b["name"], isbn=b["isbn"], publisher=b["publisher"],
                            price=b["price"], status=b["status"]))

        db.add(Proctor(teacher_tno="T1001", teacher_name="张伟", course_name="数据结构与算法",
                       exam_date="2025-06-23", session="上午 09:00-11:00", room="主楼A203", duty="主监考"))
        db.add(Proctor(teacher_tno="T1001", teacher_name="张伟", course_name="面向对象程序设计",
                       exam_date="2025-06-25", session="下午 14:00-16:00", room="实验楼C302", duty="副监考"))
        db.add(Proctor(teacher_tno="T1002", teacher_name="李强", course_name="数据库原理",
                       exam_date="2025-06-24", session="上午 09:00-11:00", room="主楼A102", duty="主监考"))
        db.add(Proctor(teacher_tno="T1004", teacher_name="陈晨", course_name="计算机网络",
                       exam_date="2025-06-26", session="下午 14:00-16:00", room="主楼B201", duty="主监考"))

        # ---- 22.11 一条待处理的找回申请，方便直接演示管理员审批 ----
        db.add(RecoveryRequest(role="student", name=list(student_map.values())[3].name,
                               class_name="数据科学2401", request_type="密码重置",
                               contact="13800001111", reason="忘记密码，原手机号已停用",
                               status="待处理"))

        await db.commit()
        logger.info("种子数据导入完成：学生 %s 人、教师 %s 人、课程 %s 门",
                    len(student_map), len(teacher_map), len(course_map))
