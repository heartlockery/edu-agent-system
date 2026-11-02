"""\n模块 17 · 学生端工具集（Agent 的「手」）
--------------------------------------------------------------------
作用：把学生端的每个业务动作包装成一个可被大模型调用的工具：
      查询类（成绩/课表/考试/通知/消息/教室/选课/个人信息）、
      操作类（考试预约、个人信息维护）、
      知识类（RAG 检索、学习建议）、状态类（功能开发进度）。
约定：每个工具返回 dict：{ok, data, message, ui?}
      message 是给人看的短句，离线模式下直接拼成答案。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from app.ai.rag import kb
from app.db.models import (
    Application,
    ClassInfo,
    Course,
    Enrollment,
    ExamAppointment,
    Grade,
    Message,
    Notification,
    Student,
    Textbook,
    TimetableEntry,
)
from app.services.exam_plan import find_exam
from app.services.grades import grade_point
from app.services.registry import find_feature

# 13.1 空闲教室池：真实系统来自教室占用表，这里用常量模拟
ROOM_POOL = ["主楼A101", "主楼A102", "主楼A203", "主楼A301", "主楼B201", "外语楼B201", "实验楼C302"]
from app.ai.coerce import section_num, weekday_num

WEEKDAY_CN = {1: "周一", 2: "周二", 3: "周三", 4: "周四", 5: "周五", 0: "今天"}


async def _student(ctx: dict) -> Student | None:
    """13.2 通用取数：根据登录态里的学号拿学生对象。"""
    res = await ctx["db"].execute(select(Student).where(Student.sno == ctx["sno"]))
    return res.scalar_one_or_none()


async def _query_grades(ctx: dict, course_name: str = "", semester: str = "") -> dict:
    """13.3 成绩查询：支持按课程名模糊匹配，返回单科分、总分、平均分、绩点。"""
    stu = await _student(ctx)
    if not stu:
        return {"ok": False, "data": [], "message": "没有找到你的学籍信息，请联系教务处。"}

    stmt = select(Grade).where(Grade.student_id == stu.id)
    if semester:
        stmt = stmt.where(Grade.semester == semester)
    rows = (await ctx["db"].execute(stmt)).scalars().all()
    if not rows:
        return {"ok": True, "data": [], "message": "系统里还没有你的成绩记录，可能尚未录入。"}

    if course_name:
        rows = [g for g in rows if course_name in g.course_name or course_name in g.course_code]
        if not rows:
            available = "、".join(sorted({g.course_name for g in (await ctx["db"].execute(stmt)).scalars().all()}))
            return {"ok": True, "data": [], "message": "没有查到「" + course_name + "」的成绩。你上学期修的课程有：" + available}

    total = round(sum(g.score for g in rows), 1)
    credits = round(sum(g.credit for g in rows), 1)
    avg = round(total / len(rows), 1)
    gpa = round(sum(grade_point(g.score) * g.credit for g in rows) / credits, 2) if credits else 0

    detail = "；".join(g.course_name + " " + str(g.score) + " 分（" + str(g.credit) + " 学分）" for g in rows)
    message = "查到你的成绩：" + detail + "。合计 " + str(total) + " 分，平均 " + str(avg) + " 分，总学分 " + str(credits) + "，平均绩点 " + str(gpa) + "。"
    if len(rows) == 1 and rows[0].score < 60:
        message += " 这门课没及格，建议关注补考安排。"
    return {"ok": True, "data": [{"course": g.course_name, "score": g.score, "credit": g.credit,
                                  "semester": g.semester} for g in rows],
            "message": message, "summary": {"total": total, "avg": avg, "gpa": gpa, "credits": credits}}


async def _query_timetable(ctx: dict, weekday: int = 0) -> dict:
    """13.4 课表查询：按星期过滤；weekday=0 表示查整周。

    注意：模型可能把 weekday 抽成"周三""星期三"，这里必须先归一化成数字，
    否则 SQL 拿字符串去比较整数列，会查不到任何数据，用户就会听到"没有排课"的假信息。
    """
    weekday = weekday_num(weekday, 0)
    stmt = select(TimetableEntry).where(TimetableEntry.class_id == ctx["class_id"])
    if weekday:
        stmt = stmt.where(TimetableEntry.weekday == weekday)
    entries = (await ctx["db"].execute(stmt.order_by(TimetableEntry.weekday, TimetableEntry.start_section))).scalars().all()
    if not entries:
        return {"ok": True, "data": [], "message": "这个时间段你本班没有排课，可以去自习。"}

    group: dict[int, list[TimetableEntry]] = {}
    for e in entries:
        group.setdefault(e.weekday, []).append(e)
    lines = []
    for day in sorted(group):
        items = "；".join(
            e.course_name + " 第" + str(e.start_section) + "-" + str(e.end_section) + "节 "
            + e.location + "（" + e.teacher_name + "）" for e in group[day]
        )
        lines.append(WEEKDAY_CN.get(day, "周" + str(day)) + "：" + items)
    head = "这是你本周的课表：" if not weekday else "你" + WEEKDAY_CN.get(weekday, "") + "的课程是："
    return {"ok": True, "data": [e.course_name + "|" + str(e.weekday) + "|" + str(e.start_section) + "-" + str(e.end_section) + "|" + e.location for e in entries],
            "message": head + "\n" + "\n".join(lines),
            "ui": [{"type": "navigate", "page": "timetable", "label": "课表页面"}]}


async def _query_exams(ctx: dict) -> dict:
    """13.5 考试信息：只返回学生已修课程的考试安排。"""
    stu = await _student(ctx)
    courses = set((await ctx["db"].execute(
        select(Grade.course_name).where(Grade.student_id == stu.id))).scalars().all()) if stu else set()
    from app.services.exam_plan import all_exams

    exams = [e for e in all_exams() if not courses or e["course_name"] in courses]
    if not exams:
        return {"ok": True, "data": [], "message": "暂时没有查到你的考试安排。"}
    lines = [e["course_name"] + "：" + e["exam_date"] + " " + e["session"] + "，" + e["room"] for e in exams]
    return {"ok": True, "data": exams, "message": "你的考试安排如下：\n" + "\n".join(lines),
            "ui": [{"type": "navigate", "page": "exams", "label": "考试信息"}]}


async def _list_notifications(ctx: dict, limit: int = 5) -> dict:
    """13.6 通知公告：本班通知 + 全校通知。"""
    stmt = (select(Notification)
            .where((Notification.target_class_id.is_(None)) | (Notification.target_class_id == ctx["class_id"]))
            .order_by(Notification.id.desc()).limit(limit))
    rows = (await ctx["db"].execute(stmt)).scalars().all()
    if not rows:
        return {"ok": True, "data": [], "message": "目前没有新的通知。"}
    lines = [n.created_at.strftime("%m-%d") + " " + n.title + "（" + n.sender_name + "）" for n in rows]
    return {"ok": True, "data": [{"title": n.title, "content": n.content} for n in rows],
            "message": "最近 " + str(len(rows)) + " 条通知：\n" + "\n".join(lines),
            "ui": [{"type": "navigate", "page": "notifications", "label": "通知公告"}]}


async def _list_messages(ctx: dict, limit: int = 10) -> dict:
    """13.7 消息列表：教师点对点消息，含未读数。"""
    stmt = (select(Message).where(Message.receiver_id == ctx["sno"])
            .order_by(Message.id.desc()).limit(limit))
    rows = (await ctx["db"].execute(stmt)).scalars().all()
    unread = len([m for m in rows if not m.is_read])
    if not rows:
        return {"ok": True, "data": [], "message": "暂时没有老师发来的消息。"}
    lines = [m.created_at.strftime("%m-%d") + " " + (m.title or "消息") + "：" + m.content[:40] for m in rows]
    return {"ok": True, "data": [{"title": m.title, "content": m.content, "read": m.is_read} for m in rows],
            "message": "你有 " + str(unread) + " 条未读消息，共 " + str(len(rows)) + " 条：\n" + "\n".join(lines),
            "ui": [{"type": "navigate", "page": "messages", "label": "消息列表"}]}


async def _reserve_exam(ctx: dict, course_name: str = "", session: str = "上午") -> dict:
    """13.8 考试预约：写入预约表，重复预约会提示。"""
    exam = find_exam(course_name) if course_name else None
    if not exam:
        return {"ok": False, "data": [], "message": "没找到这门课的考试安排，请告诉我要预约哪一门课（如：大学英语）。"}
    stu = await _student(ctx)
    if not stu:
        return {"ok": False, "data": [], "message": "学籍信息异常，无法预约。"}

    exists = (await ctx["db"].execute(
        select(ExamAppointment).where(ExamAppointment.student_id == stu.id,
                                     ExamAppointment.course_code == exam["course_code"])
    )).scalars().first()
    if exists:
        return {"ok": True, "data": [{"course": exam["course_name"], "status": exists.status}],
                "message": "你已经预约过《" + exam["course_name"] + "》了，状态是「" + exists.status + "」。"}

    ctx["db"].add(ExamAppointment(
        student_id=stu.id, course_code=exam["course_code"], course_name=exam["course_name"],
        exam_date=exam["exam_date"], session=session, room=exam["room"], status="已预约",
    ))
    await ctx["db"].flush()
    return {"ok": True, "data": [exam],
            "message": "已帮你预约《" + exam["course_name"] + "》的考试："
                       + exam["exam_date"] + " " + session + "，考场 " + exam["room"] + "，状态「已预约」。",
            "ui": [{"type": "navigate", "page": "exams", "label": "考试预约"}]}


async def _query_free_classrooms(ctx: dict, weekday: int = 1, section: int = 1) -> dict:
    """13.9 空闲教室：从课表里排掉被占用的教室。"""
    weekday = weekday_num(weekday, 1) or 1
    section = section_num(section, 1)
    section = int(section or 1)
    busy = (await ctx["db"].execute(
        select(TimetableEntry.location).where(
            TimetableEntry.weekday == weekday,
            TimetableEntry.start_section <= section,
            TimetableEntry.end_section >= section,
        )
    )).scalars().all()
    busy_set = {b for b in busy if b}
    free = [r for r in ROOM_POOL if r not in busy_set]
    if not free:
        return {"ok": True, "data": [], "message": WEEKDAY_CN.get(weekday, "") + "第" + str(section) + "节全部教室都被占用了。"}
    return {"ok": True, "data": free,
            "message": WEEKDAY_CN.get(weekday, "周" + str(weekday)) + "第" + str(section) + "节空闲教室（" + str(len(free)) + " 间）："
                       + "、".join(free[:6]) + "。",
            "ui": [{"type": "navigate", "page": "classrooms", "label": "空闲教室"}]}


async def _my_enrollments(ctx: dict) -> dict:
    """13.10 选课情况确认。"""
    stu = await _student(ctx)
    rows = (await ctx["db"].execute(select(Enrollment).where(Enrollment.student_id == stu.id))).scalars().all()
    if not rows:
        return {"ok": True, "data": [], "message": "本学期还没有选课记录。"}
    lines = [e.course_name + "（" + str(e.credit) + " 学分，" + e.status + "）" for e in rows]
    total = round(sum(e.credit for e in rows), 1)
    return {"ok": True, "data": [{"course": e.course_name, "credit": e.credit, "status": e.status} for e in rows],
            "message": "你本学期选了 " + str(len(rows)) + " 门课，共 " + str(total) + " 学分：\n" + "\n".join(lines),
            "ui": [{"type": "navigate", "page": "enrollments", "label": "选课情况"}]}


async def _my_profile(ctx: dict) -> dict:
    """13.11 个人信息（含辅导员，学生常问「我辅导员是谁」）。"""
    stu = await _student(ctx)
    if not stu:
        return {"ok": False, "data": [], "message": "学籍信息异常。"}
    klass = (await ctx["db"].execute(select(ClassInfo).where(ClassInfo.id == stu.class_id))).scalar_one_or_none()
    return {"ok": True,
            "data": {"sno": stu.sno, "name": stu.name, "class": klass.name if klass else "",
                     "major": stu.major, "phone": stu.phone, "email": stu.email,
                     "advisor": klass.advisor if klass else ""},
            "message": "你叫 " + stu.name + "，学号 " + stu.sno + "，" + (klass.name if klass else "") + "。"
                       + "手机 " + (stu.phone or "未填写") + "，邮箱 " + (stu.email or "未填写")
                       + "，辅导员是 " + ((klass.advisor if klass else "") or "未设置") + "。"}


async def _rag_search(ctx: dict, question: str = "") -> dict:
    """13.12 规章检索（RAG）：返回命中的规章片段，供模型作答或直接展示。"""
    hits = await kb.search(question or "教务规章")
    if not hits:
        return {"ok": True, "data": [], "message": "知识库里暂时没有相关规定，建议咨询辅导员或教务处。"}
    snippets = [h["content"][:160].replace("\n", " ") for h in hits[:3]]
    return {"ok": True, "data": [{"title": h["title"], "content": h["content"], "score": h["score"]} for h in hits],
            "message": "根据教务处规定：\n" + "\n".join("· " + s for s in snippets)}


async def _study_advice(ctx: dict, question: str = "") -> dict:
    """13.13 学习建议：结合本人成绩短板 + 规章，给出可执行建议。"""
    stu = await _student(ctx)
    rows = (await ctx["db"].execute(select(Grade).where(Grade.student_id == stu.id))).scalars().all() if stu else []
    advice: list[str] = []
    if rows:
        weakest = min(rows, key=lambda g: g.score)
        advice.append("先把《" + weakest.course_name + "》补起来（当前 " + str(weakest.score) + " 分），每周固定 3 次、每次 1 小时的专项练习。")
        advice.append("成绩在 80 分以上的课程保持节奏即可，把时间向短板课程倾斜。")
    else:
        advice.append("先建立固定作息：每天 2 小时专业课 + 1 小时英语，避免期末突击。")
    advice.append("遇到连续两周听不懂的内容，当天就去问任课老师或辅导员，不要累积。")
    advice.append("每学期至少参加一次学科竞赛或项目实践，对保研和就业都加分。")
    return {"ok": True, "data": advice, "message": "给你几条学习建议：\n" + "\n".join("· " + a for a in advice)}


async def _check_feature(ctx: dict, feature_name: str = "") -> dict:
    """13.14 功能状态：回答「这个功能能不能用」。"""
    item = find_feature(feature_name)
    if not item:
        return {"ok": True, "data": [], "message": "没有找到叫「" + feature_name + "」的功能，你可以在左侧菜单里看看。"}
    if item["status"] == "ready":
        return {"ok": True, "data": [item], "message": "「" + item["name"] + "」已经可以使用：" + item["desc"],
                "ui": [{"type": "navigate", "page": item["key"], "label": item["name"]}]}
    return {"ok": True, "data": [item], "message": "「" + item["name"] + "」系统正在开发中，敬请期待。"}


async def _query_course_teacher(ctx: dict, course_name: str = "") -> dict:
    """13.14b 查任课老师：从本学期课程表里取（学生常问「我的高数老师是谁」）。"""
    stmt = select(Course).where(Course.semester == "2024-2025-2")
    if course_name:
        stmt = stmt.where(Course.name.contains(course_name.replace("A(上)", "A(下)")))
    rows = (await ctx["db"].execute(stmt)).scalars().all()
    if not rows:
        return {"ok": True, "data": [], "message": "没有查到这门课的任课老师，可能不是本学期的课程哦。"}
    lines = [c.name + " 由 " + c.teacher_name + " 老师任教（" + str(c.credit) + " 学分）" for c in rows]
    return {"ok": True, "data": [{"course": c.name, "teacher": c.teacher_name} for c in rows],
            "message": "你们班本学期的任课老师是：\n" + "\n".join(lines)}


async def _query_calendar(ctx: dict) -> dict:
    """13.14c 日程：本周课程 + 近期考试，用一句话说清。"""
    entries = (await ctx["db"].execute(
        select(TimetableEntry).where(TimetableEntry.class_id == ctx["class_id"])
        .order_by(TimetableEntry.weekday, TimetableEntry.start_section))).scalars().all()
    week: dict[int, list[str]] = {}
    for e in entries:
        week.setdefault(e.weekday, []).append(e.course_name + "(" + str(e.start_section) + "-" + str(e.end_section) + "节)")
    from app.services.exam_plan import all_exams

    exams = all_exams()[:3]
    lines = [WEEKDAY_CN.get(d, "周" + str(d)) + "：" + "、".join(v) for d, v in sorted(week.items())]
    exam_line = "最近的考试：" + "；".join(e["course_name"] + " " + e["exam_date"] for e in exams)
    return {"ok": True, "data": {"week": lines, "exams": exams},
            "message": "这周你的课程安排是：\n" + "\n".join(lines) + "\n" + exam_line,
            "ui": [{"type": "navigate", "page": "timetable", "label": "课表页面"}]}


async def _query_makeup(ctx: dict) -> dict:
    """13.14d 补考查询与确认。"""
    stu = await _student(ctx)
    if not stu:
        return {"ok": False, "data": [], "message": "学籍信息异常，暂时查不到补考信息。"}
    failed = (await ctx["db"].execute(select(Grade).where(
        Grade.student_id == stu.id, Grade.score < 60))).scalars().all()
    if not failed:
        return {"ok": True, "data": [], "message": "你上学期没有不及格的课程呀，不用补考，继续保持～"}
    done = {a.title for a in (await ctx["db"].execute(select(Application).where(
        Application.student_id == stu.id, Application.app_type == "补考确认"))).scalars().all()}
    lines = [g.course_name + "：" + str(g.score) + " 分" + ("（已确认补考）" if g.course_name in done else "（待确认）")
             for g in failed]
    return {"ok": True, "data": [{"course": g.course_name, "score": g.score} for g in failed],
            "message": "你有 " + str(len(failed)) + " 门课需要补考：\n" + "\n".join(lines)
                       + "\n需要的话可以在「补考确认」页面一键提交，或者告诉我帮你确认。",
            "ui": [{"type": "navigate", "page": "makeup_confirm", "label": "补考确认"}]}


async def _query_textbooks(ctx: dict) -> dict:
    """13.14e 教材明细与费用。"""
    books = (await ctx["db"].execute(select(Textbook))).scalars().all()
    if not books:
        return {"ok": True, "data": [], "message": "本学期还没有教材征订记录。"}
    total = round(sum(b.price for b in books), 1)
    lines = [b.course_name + "：《" + b.name + "》¥" + str(b.price) for b in books]
    return {"ok": True, "data": [{"course": b.course_name, "name": b.name, "price": b.price} for b in books],
            "message": "本学期教材明细：\n" + "\n".join(lines) + "\n合计 ¥" + str(total) + "。",
            "ui": [{"type": "navigate", "page": "textbook_order", "label": "教材预订"}]}


async def _query_electives(ctx: dict) -> dict:
    """13.14f 可选选修课。"""
    from app.services.curriculum import ELECTIVES

    lines = [e["name"] + "（" + str(e["credit"]) + " 学分，" + e["time"] + "，" + e["teacher"] + "）"
             for e in ELECTIVES]
    return {"ok": True, "data": ELECTIVES,
            "message": "本学期可以选的选修课有：\n" + "\n".join(lines)
                       + "\n在「自主选课」页面点一下就能选上。",
            "ui": [{"type": "navigate", "page": "self_course", "label": "自主选课"}]}


async def _query_training_plan(ctx: dict) -> dict:
    """13.14g 培养方案（按学期给学分）。"""
    from app.services.curriculum import TRAINING_PLAN, total_credits

    lines = [s["semester"] + "：" + str(round(sum(c for _, c in s["courses"]), 1)) + " 学分（"
             + "、".join(n for n, _ in s["courses"][:4]) + "…）" for s in TRAINING_PLAN]
    return {"ok": True, "data": TRAINING_PLAN,
            "message": "本专业培养方案共 " + str(total_credits()) + " 学分：\n" + "\n".join(lines),
            "ui": [{"type": "navigate", "page": "training_plan", "label": "个人培养方案"}]}


async def _submit_application(ctx: dict, app_type: str = "学分认定", title: str = "", detail: str = "") -> dict:
    """13.14h 提交报名申请（学分认定、创新创业、转专业等）。"""
    stu = await _student(ctx)
    if not stu:
        return {"ok": False, "data": [], "message": "学籍信息异常，无法提交申请。"}
    ctx["db"].add(Application(student_id=stu.id, app_type=app_type,
                              title=title or app_type, detail=detail, status="已提交"))
    await ctx["db"].flush()
    return {"ok": True, "data": [], "message": "已经帮你提交「" + app_type + "」申请啦，辅导员审核后就能看到进度。"}


async def _web_search(ctx: dict, query: str = "") -> dict:
    """13.14i 联网搜索学习资料（游戏类会被内容边界拦截）。"""
    from app.ai.websearch import search

    results = await search(query or "学习方法")
    if not results:
        return {"ok": True, "data": [],
                "message": "我试着上网查了，但暂时没搜到合适的结果（也可能是网络受限）。"
                           "你可以换个说法，或者问我和课程、考试相关的内容～"}
    lines = [r["title"] + "：" + (r["snippet"] or "")[:60] for r in results[:3]]
    return {"ok": True, "data": results,
            "message": "我上网帮你找了几条资料：\n" + "\n".join(lines)
                       + "\n详细内容在右侧「联网搜索」结果里，需要完整链接可以再问我。"}


# 13.15 工具注册表：name -> 描述 + 参数说明 + 实现函数
STUDENT_TOOLS: dict[str, dict] = {
    "query_grades": {"desc": "查询当前学生的成绩（可指定课程，如 程序设计基础 / 高等数学A(上)）",
                     "params": {"course_name": "课程名，可省略表示查全部"}, "fn": _query_grades},
    "query_timetable": {"desc": "查询本班课表，可指定星期几",
                        "params": {"weekday": "1-5 的整数，0 表示整周"}, "fn": _query_timetable},
    "query_exams": {"desc": "查询本人考试安排（时间、地点）", "params": {}, "fn": _query_exams},
    "list_notifications": {"desc": "查看通知公告", "params": {}, "fn": _list_notifications},
    "list_messages": {"desc": "查看老师发来的消息与未读数", "params": {}, "fn": _list_messages},
    "reserve_exam": {"desc": "帮学生预约某门课的考试时段",
                     "params": {"course_name": "课程名", "session": "上午/下午/晚上"}, "fn": _reserve_exam},
    "query_free_classrooms": {"desc": "查询某天某节的空闲教室",
                              "params": {"weekday": "1-5", "section": "节次"}, "fn": _query_free_classrooms},
    "my_enrollments": {"desc": "查询本人选课情况", "params": {}, "fn": _my_enrollments},
    "my_profile": {"desc": "查询本人学号、班级、联系方式、辅导员", "params": {}, "fn": _my_profile},
    "rag_search": {"desc": "检索教务规章（转专业、学分认定、补考、休学等）", "params": {"question": "问题"}, "fn": _rag_search},
    "study_advice": {"desc": "结合成绩短板给学习建议", "params": {"question": "学生的问题"}, "fn": _study_advice},
    "check_feature": {"desc": "查询某个功能是否已上线", "params": {"feature_name": "功能名"}, "fn": _check_feature},
    "query_course_teacher": {"desc": "查询某门课（或全部课）的任课老师",
                             "params": {"course_name": "课程名，可省略"}, "fn": _query_course_teacher},
    "query_calendar": {"desc": "查询本周课程安排与近期考试", "params": {}, "fn": _query_calendar},
    "query_makeup": {"desc": "查询不及格课程与补考确认状态", "params": {}, "fn": _query_makeup},
    "query_textbooks": {"desc": "查询本学期教材明细与费用", "params": {}, "fn": _query_textbooks},
    "query_electives": {"desc": "查询可选修的课程", "params": {}, "fn": _query_electives},
    "query_training_plan": {"desc": "查询本专业培养方案与学分要求", "params": {}, "fn": _query_training_plan},
    "submit_application": {"desc": "提交报名申请（学分认定/创新创业/转专业等）",
                           "params": {"app_type": "申请类型", "title": "标题", "detail": "说明"},
                           "fn": _submit_application},
    "web_search": {"desc": "联网搜索学习类资料（概念解释、学习方法、课程延伸）",
                   "params": {"query": "搜索词"}, "fn": _web_search},
}
