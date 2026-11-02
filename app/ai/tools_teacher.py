"""\n模块 18 · 教师端工具集
--------------------------------------------------------------------
作用：教师端的「查询 + 操作」能力，全部包装成 Agent 可调用的工具：
      查成绩 / 班级分析 / 我的课表 / 会议 / 发通知 / 发消息 / 导出 Excel / 调课申请。
安全：所有查询都以登录教师的工号为上下文，导出文件名带时间戳，避免互相覆盖。
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select

from app.ai.rag import kb
from app.db.models import (
    ClassInfo,
    Grade,
    Meeting,
    Message,
    Notification,
    Proctor,
    ScheduleChangeRequest,
    Student,
    Teacher,
    Textbook,
    TimetableEntry,
)
from app.config import EXPORT_DIR
from app.services.grades import export_grades_async, summarize
from app.services.registry import find_feature

from app.ai.coerce import weekday_num

WEEKDAY_CN = {1: "周一", 2: "周二", 3: "周三", 4: "周四", 5: "周五", 0: "整周"}


async def _teacher(ctx: dict) -> Teacher | None:
    res = await ctx["db"].execute(select(Teacher).where(Teacher.tno == ctx["tno"]))
    return res.scalar_one_or_none()


async def _resolve_class(ctx: dict, class_name: str = "") -> ClassInfo | None:
    """14.1 解析班级名：支持「2401」「一班」这类口语写法。"""
    if not class_name:
        return None
    key = class_name.strip()
    if key.isdigit() and len(key) == 4:
        key = "数据科学" + key
    res = await ctx["db"].execute(select(ClassInfo).where(ClassInfo.name.contains(key[-4:])))
    return res.scalars().first()


async def _grade_rows(ctx: dict, class_name: str = "", sno: str = "", course_name: str = "") -> list[dict]:
    """14.2 从数据库拼出「学生 + 课程 + 分数」的行集合，导出/统计/查询共用。"""
    stmt = (select(Student.sno, Student.name, ClassInfo.name, Grade.course_name,
                   Grade.course_code, Grade.score, Grade.credit, Grade.semester)
            .join(Grade, Grade.student_id == Student.id)
            .join(ClassInfo, ClassInfo.id == Student.class_id))
    if class_name:
        klass = await _resolve_class(ctx, class_name)
        if klass:
            stmt = stmt.where(ClassInfo.id == klass.id)
    if sno:
        stmt = stmt.where(Student.sno == sno)
    if course_name:
        stmt = stmt.where(Grade.course_name.contains(course_name))
    rows = (await ctx["db"].execute(stmt)).all()

    buckets: dict[str, dict] = {}
    for r in rows:
        key = r[0]
        if key not in buckets:
            buckets[key] = {"sno": r[0], "name": r[1], "class_name": r[2],
                            "grades": {}, "credits": {}, "semester": r[7]}
        buckets[key]["grades"][r[3]] = r[5]
        buckets[key]["credits"][r[3]] = r[6]
    return list(buckets.values())


async def _query_student_grades(ctx: dict, class_name: str = "", sno: str = "", course_name: str = "") -> dict:
    """14.3 学生成绩查询：给出条数、平均分以及前几条明细。"""
    rows = await _grade_rows(ctx, class_name, sno, course_name)
    if not rows:
        return {"ok": True, "data": [], "message": "没有查到符合条件的成绩记录，请确认班级/学号/课程。"}
    stats = summarize(rows)
    samples = rows[:5]
    lines = []
    for r in samples:
        detail = "、".join(k + " " + str(v) for k, v in r["grades"].items())
        lines.append(r["class_name"] + " " + r["name"] + "（" + r["sno"] + "）：" + detail)
    msg = ("共查到 " + str(stats["count"]) + " 名学生的成绩，平均分 " + str(stats["avg_score"])
           + "，及格率 " + str(stats["pass_rate"]) + "%，最高 " + str(stats["max_score"])
           + "，最低 " + str(stats["min_score"]) + "。\n前几条明细：\n" + "\n".join(lines))
    return {"ok": True, "data": samples, "message": msg, "stats": stats,
            "ui": [{"type": "navigate", "page": "grades", "label": "成绩查询"}]}


async def _class_analysis(ctx: dict, class_name: str = "", course_name: str = "") -> dict:
    """14.4 班级成绩分析：按课程给平均分/及格率/最高最低。"""
    rows = await _grade_rows(ctx, class_name, "", course_name)
    if not rows:
        return {"ok": True, "data": [], "message": "没有可用数据来做分析。"}
    by_course: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        for course, score in r["grades"].items():
            by_course[course].append(float(score))
    lines = []
    for course, scores in by_course.items():
        passed = len([s for s in scores if s >= 60])
        lines.append(course + "：平均 " + str(round(sum(scores) / len(scores), 1))
                     + "，及格率 " + str(round(passed / len(scores) * 100, 1)) + "%"
                     + "，最高 " + str(max(scores)) + "，最低 " + str(min(scores)))
    target = class_name or "全部班级"
    return {"ok": True, "data": {k: round(sum(v) / len(v), 1) for k, v in by_course.items()},
            "message": target + " 的成绩分析：\n" + "\n".join(lines)}


async def _send_notification(ctx: dict, title: str, content: str = "", class_name: str = "") -> dict:
    """14.5 发送通知：写通知表 + 给目标班级学生逐条写消息（真实系统可换成站内推送）。"""
    if not (title or "").strip():
        return {"ok": False, "data": [], "message": "要发通知的话，请告诉我想发什么内容呀～"}
    teacher = await _teacher(ctx)
    klass = await _resolve_class(ctx, class_name) if class_name else None
    target_id = klass.id if klass else None
    ctx["db"].add(Notification(
        title=title, content=content or title, category="教务通知",
        sender_tno=ctx["tno"], sender_name=teacher.name if teacher else "教师",
        target_class_id=target_id,
    ))
    students = (await ctx["db"].execute(
        select(Student).where(Student.class_id == target_id) if target_id else select(Student)
    )).scalars().all()
    for s in students:
        ctx["db"].add(Message(
            sender_role="teacher", sender_id=ctx["tno"], sender_name=teacher.name if teacher else "教师",
            receiver_role="student", receiver_id=s.sno, title=title, content=content or title,
        ))
    await ctx["db"].flush()
    scope = klass.name if klass else "全体学生"
    return {"ok": True, "data": {"class": scope, "count": len(students)},
            "message": "已向 " + scope + " 的 " + str(len(students)) + " 名学生发送通知《" + title + "》。",
            "ui": [{"type": "navigate", "page": "send_notification", "label": "发送通知"}]}


async def _send_message(ctx: dict, sno: str = "", title: str = "教师消息", content: str = "") -> dict:
    """14.6 点对点消息：必须给出学号。"""
    if not sno:
        return {"ok": False, "data": [], "message": "请告诉我要发给哪个学生（学号，例如 2024010101）。"}
    student = (await ctx["db"].execute(select(Student).where(Student.sno == sno))).scalars().first()
    if not student:
        return {"ok": False, "data": [], "message": "没有找到学号 " + sno + " 的学生。"}
    teacher = await _teacher(ctx)
    ctx["db"].add(Message(
        sender_role="teacher", sender_id=ctx["tno"], sender_name=teacher.name if teacher else "教师",
        receiver_role="student", receiver_id=sno, title=title, content=content or title,
    ))
    await ctx["db"].flush()
    return {"ok": True, "data": [{"sno": sno}], "message": "已给 " + student.name + "（" + sno + "）发送消息。"}


async def _my_timetable(ctx: dict, weekday: int = 0) -> dict:
    """14.7 教师课表：只查自己的教学任务。

    weekday 先归一化：模型常把"周三""星期三"直接当参数传进来，
    字符串跟整数列比较会静默查不到数据，表现成"这周没课"。
    """
    weekday = weekday_num(weekday, 0)
    stmt = select(TimetableEntry).where(TimetableEntry.teacher_tno == ctx["tno"])
    if weekday:
        stmt = stmt.where(TimetableEntry.weekday == weekday)
    rows = (await ctx["db"].execute(stmt.order_by(TimetableEntry.weekday, TimetableEntry.start_section))).scalars().all()
    if not rows:
        return {"ok": True, "data": [], "message": "这段时间你没有排课。"}
    lines = []
    for e in rows:
        klass = (await ctx["db"].execute(select(ClassInfo).where(ClassInfo.id == e.class_id))).scalar_one_or_none()
        lines.append(WEEKDAY_CN.get(e.weekday, "周" + str(e.weekday)) + " 第" + str(e.start_section)
                     + "-" + str(e.end_section) + "节 " + e.course_name + "（" + (klass.name if klass else "")
                     + "，" + e.location + "）")
    return {"ok": True, "data": lines, "message": "你的课程安排：\n" + "\n".join(lines),
            "ui": [{"type": "navigate", "page": "my_timetable", "label": "我的课表"}]}


async def _my_meetings(ctx: dict) -> dict:
    """14.8 会议安排：回答「我什么时候开会」。"""
    rows = (await ctx["db"].execute(
        select(Meeting).where(Meeting.teacher_tno == ctx["tno"]).order_by(Meeting.start_time)
    )).scalars().all()
    if not rows:
        return {"ok": True, "data": [], "message": "近期没有你的会议安排。"}
    lines = [m.start_time + " " + m.title + "（" + m.location + "）" for m in rows]
    return {"ok": True, "data": lines, "message": "你的会议安排：\n" + "\n".join(lines),
            "ui": [{"type": "navigate", "page": "meetings", "label": "会议安排"}]}


async def _export_grades_file(ctx: dict, class_name: str = "", course_name: str = "") -> dict:
    """14.9 导出成绩 Excel：生成文件后返回绝对路径 + 浏览器下载地址。"""
    rows = await _grade_rows(ctx, class_name, "", course_name)
    if not rows:
        return {"ok": False, "data": [], "message": "没有可导出的成绩数据。"}
    courses = sorted({c for r in rows for c in r["grades"]})
    label = class_name or "全部班级"
    from datetime import datetime

    filename = "成绩_" + label + "_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".xlsx"
    path = await export_grades_async(rows, courses, filename=filename)
    url = "/files/export/" + path.name
    return {"ok": True,
            "data": {"filename": path.name, "path": str(path), "url": url, "rows": len(rows)},
            "message": "导出完成，共 " + str(len(rows)) + " 名学生。\n文件位置：" + str(path)
                       + "\n下载地址：" + url,
            "ui": [{"type": "download", "url": url, "label": "成绩文件"}]}


async def _apply_schedule_change(ctx: dict, change_type: str = "单独调课", course_name: str = "",
                                 from_slot: str = "", to_slot: str = "", target_tno: str = "",
                                 reason: str = "") -> dict:
    """14.10 调课申请：单独调课直接生成待审批单；互换调课额外给对方发一条消息。"""
    teacher = await _teacher(ctx)
    ctx["db"].add(ScheduleChangeRequest(
        teacher_tno=ctx["tno"], teacher_name=teacher.name if teacher else "教师",
        change_type=change_type, course_name=course_name, from_slot=from_slot,
        to_slot=to_slot, target_tno=target_tno, reason=reason or "教师发起调课", status="待审批",
    ))
    if change_type == "教师互换调课" and target_tno:
        target = (await ctx["db"].execute(select(Teacher).where(Teacher.tno == target_tno))).scalars().first()
        ctx["db"].add(Message(
            sender_role="teacher", sender_id=ctx["tno"], sender_name=teacher.name if teacher else "教师",
            receiver_role="teacher", receiver_id=target_tno,
            title="调课申请通知",
            content=(teacher.name if teacher else "同事") + " 申请与你互换《" + course_name + "》课程，原时间 "
                    + from_slot + "，拟调整到 " + to_slot + "，请审批。",
        ))
        await ctx["db"].flush()
        return {"ok": True, "data": {"target": target.name if target else target_tno, "status": "待审批"},
                "message": "已提交互换调课申请：与 " + (target.name if target else target_tno)
                           + " 互换《" + course_name + "》，原时间 " + from_slot + " -> " + to_slot
                           + "。系统已给对方发送申请消息，当前状态「待审批」。"}
    await ctx["db"].flush()
    return {"ok": True, "data": {"status": "待审批"},
            "message": "已提交《" + course_name + "》的" + change_type + "申请（" + from_slot + " -> "
                       + (to_slot or "待定") + "），等待教务审批。"}


async def _rag_search(ctx: dict, question: str = "") -> dict:
    """14.11 教师端规章检索：调课流程、监考规定等。"""
    hits = await kb.search(question or "教师 调课 规定")
    if not hits:
        return {"ok": True, "data": [], "message": "知识库里没有找到相关规定。"}
    return {"ok": True, "data": hits,
            "message": "相关规定：\n" + "\n".join("· " + h["content"][:160].replace("\n", " ") for h in hits[:3])}


async def _check_feature(ctx: dict, feature_name: str = "") -> dict:
    item = find_feature(feature_name)
    if not item:
        return {"ok": True, "data": [], "message": "没有找到「" + feature_name + "」这个功能。"}
    if item["status"] == "ready":
        return {"ok": True, "data": [item], "message": "「" + item["name"] + "」可用：" + item["desc"],
                "ui": [{"type": "navigate", "page": item["key"], "label": item["name"]}]}
    return {"ok": True, "data": [item], "message": "「" + item["name"] + "」系统正在开发中。"}


async def _my_proctors(ctx: dict) -> dict:
    """14.11b 监考安排查询。"""
    rows = (await ctx["db"].execute(select(Proctor).where(
        Proctor.teacher_tno == ctx["tno"]).order_by(Proctor.exam_date))).scalars().all()
    if not rows:
        return {"ok": True, "data": [], "message": "你暂时没有监考任务，可以安心备课～"}
    lines = [p.exam_date + " " + p.session + " " + p.course_name + "（" + p.room + "，" + p.duty + "）"
             for p in rows]
    return {"ok": True, "data": lines, "message": "你的监考安排：\n" + "\n".join(lines),
            "ui": [{"type": "navigate", "page": "proctor", "label": "监考安排"}]}


async def _list_textbooks(ctx: dict) -> dict:
    """14.11c 教材管理查询。"""
    rows = (await ctx["db"].execute(select(Textbook))).scalars().all()
    if not rows:
        return {"ok": True, "data": [], "message": "还没有教材征订记录。"}
    lines = [b.course_name + "：《" + b.name + "》" + b.status + "，¥" + str(b.price)
             + "，已预订 " + str(b.order_count) + " 本" for b in rows]
    return {"ok": True, "data": [{"id": b.id, "name": b.name, "status": b.status} for b in rows],
            "message": "教材征订情况：\n" + "\n".join(lines),
            "ui": [{"type": "navigate", "page": "textbook_manage", "label": "教材管理"}]}


async def _pending_approvals(ctx: dict) -> dict:
    """14.11d 待审批的调课申请。"""
    rows = (await ctx["db"].execute(select(ScheduleChangeRequest).where(
        ScheduleChangeRequest.status == "待审批").order_by(ScheduleChangeRequest.id.desc()))).scalars().all()
    if not rows:
        return {"ok": True, "data": [], "message": "目前没有待审批的调课申请，很清爽～"}
    lines = [r.teacher_name + "：《" + r.course_name + "》" + r.change_type + " "
             + r.from_slot + " -> " + (r.to_slot or "待定") + "（申请编号 " + str(r.id) + "）" for r in rows]
    return {"ok": True, "data": [{"id": r.id, "teacher": r.teacher_name} for r in rows],
            "message": "有 " + str(len(rows)) + " 条待审批的调课申请：\n" + "\n".join(lines)
                       + "\n在「调课审批」页面可通过或驳回。",
            "ui": [{"type": "navigate", "page": "approve_change", "label": "调课审批"}]}


async def _web_search(ctx: dict, query: str = "") -> dict:
    """14.11e 联网搜索教学资料。"""
    from app.ai.websearch import search

    results = await search(query or "教学方法")
    if not results:
        return {"ok": True, "data": [], "message": "这次没搜到合适的结果，可能是网络受限，换个关键词再试试？"}
    lines = [r["title"] + "：" + (r["snippet"] or "")[:60] for r in results[:3]]
    return {"ok": True, "data": results, "message": "我上网找了几条资料：\n" + "\n".join(lines)}


TEACHER_TOOLS: dict[str, dict] = {
    "query_student_grades": {"desc": "查询班级/某个学生的成绩，可按课程过滤",
                             "params": {"class_name": "班级如 2401", "sno": "学号", "course_name": "课程名"},
                             "fn": _query_student_grades},
    "class_analysis": {"desc": "按课程统计班级平均分、及格率、最高最低",
                       "params": {"class_name": "班级", "course_name": "课程"}, "fn": _class_analysis},
    "send_notification": {"desc": "向全班或全体学生发送通知",
                          "params": {"title": "标题", "content": "正文", "class_name": "班级"},
                          "fn": _send_notification},
    "send_message": {"desc": "给某个学生发点对点消息",
                     "params": {"sno": "学号", "title": "标题", "content": "内容"}, "fn": _send_message},
    "my_timetable": {"desc": "查询我自己的课表", "params": {"weekday": "1-5，0 为整周"}, "fn": _my_timetable},
    "my_meetings": {"desc": "查询我的会议安排", "params": {}, "fn": _my_meetings},
    "export_grades_file": {"desc": "把成绩导出成 Excel 并返回文件绝对路径与下载链接",
                           "params": {"class_name": "班级", "course_name": "课程"}, "fn": _export_grades_file},
    "apply_schedule_change": {"desc": "提交调课申请（单独调课或与同事互换）",
                              "params": {"change_type": "单独调课/教师互换调课", "course_name": "课程",
                                         "from_slot": "原时间", "to_slot": "新时间",
                                         "target_tno": "互换对象工号", "reason": "原因"},
                              "fn": _apply_schedule_change},
    "rag_search": {"desc": "检索教务规章", "params": {"question": "问题"}, "fn": _rag_search},
    "check_feature": {"desc": "查询功能是否上线", "params": {"feature_name": "功能名"}, "fn": _check_feature},
    "my_proctors": {"desc": "查询我的监考安排", "params": {}, "fn": _my_proctors},
    "list_textbooks": {"desc": "查询教材征订与预订情况", "params": {}, "fn": _list_textbooks},
    "pending_approvals": {"desc": "查询待审批的调课申请", "params": {}, "fn": _pending_approvals},
    "web_search": {"desc": "联网搜索教学资料", "params": {"query": "搜索词"}, "fn": _web_search},
}


def tools_for(role: str) -> dict[str, dict]:
    """14.12 按角色返回工具表：学生看不到教师工具，反之亦然。"""
    return TEACHER_TOOLS if role == "teacher" else STUDENT_TOOLS


from app.ai.tools_student import STUDENT_TOOLS  # noqa: E402  （放在底部避免循环导入）
