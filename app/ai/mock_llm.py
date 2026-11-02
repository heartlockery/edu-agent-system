"""\n模块 14 · 离线规则引擎（没有 API Key 时的「假大模型」）
--------------------------------------------------------------------
作用：把中文问题用关键词/正则映射成工具调用，并把工具结果拼成温柔的人话。
      ① 没有 Key 也能完整体验 Agent 调度；② 在线模型异常时自动兜底；
      ③ 规则清晰，答辩时可以直接讲「意图识别 -> 工具调用 -> 结果聚合」链路。
"""

from __future__ import annotations

import re

from app.ai.guard import check

WEEKDAY_WORDS = {
    "周一": 1, "星期一": 1, "礼拜一": 1,
    "周二": 2, "星期二": 2, "礼拜二": 2,
    "周三": 3, "星期三": 3, "礼拜三": 3,
    "周四": 4, "星期四": 4, "礼拜四": 4,
    "周五": 5, "星期五": 5, "礼拜五": 5,
}

# 12.1 课程别名表：学生口语 -> 正式课程名
COURSE_ALIAS = {
    "高数": "高等数学A(上)",
    "高等数学": "高等数学A(上)",
    "数学": "高等数学A(上)",
    "英语": "大学英语(一)",
    "程序设计": "程序设计基础",
    "编程": "程序设计基础",
    "python": "程序设计基础",
    "c语言": "程序设计基础",
    "导论": "计算机导论",
    "离散": "离散数学",
    "体育": "大学体育(一)",
    "思政": "思想道德与法治",
    "思想道德": "思想道德与法治",
}

SECTION_WORDS = {"上午": 1, "早上": 1, "下午": 5, "中午": 3, "晚上": 9, "晚自习": 9}


def _find_course(question: str) -> str:
    q = question.lower()
    for alias, name in COURSE_ALIAS.items():
        if alias in q:
            return name
    return ""


def _find_class(question: str) -> str:
    m = re.search(r"240([123])", question)
    if m:
        return "数据科学240" + m.group(1)
    if "一班" in question or "1班" in question:
        return "数据科学2401"
    if "二班" in question or "2班" in question:
        return "数据科学2402"
    if "三班" in question or "3班" in question:
        return "数据科学2403"
    return ""


def _find_weekday(question: str) -> int:
    for word, day in WEEKDAY_WORDS.items():
        if word in question:
            return day
    return 0


def _find_section(question: str) -> int:
    m = re.search(r"第\s*(\d+)\s*[-到~]?\s*(\d+)?\s*节", question)
    if m:
        return int(m.group(1))
    for word, sec in SECTION_WORDS.items():
        if word in question:
            return sec
    return 1


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


async def rule_plan(question: str, role: str) -> list[dict]:
    """12.2 规则匹配：返回 [{"tool": ..., "args": {...}}]。"""
    q = _clean(question)
    if check(q):                                    # 游戏/作弊类不调度工具
        return []
    course = _find_course(q)
    cls = _find_class(q)
    day = _find_weekday(q)
    sec = _find_section(q)

    if role == "teacher":
        if any(w in q for w in ("监考", "巡考")):
            return [{"tool": "my_proctors", "args": {}}]
        if any(w in q for w in ("教材", "课本", "征订")):
            return [{"tool": "list_textbooks", "args": {}}]
        if any(w in q for w in ("审批", "待处理", "待办", "待批")):
            return [{"tool": "pending_approvals", "args": {}}]
        if any(w in q for w in ("导出", "下载", "导成", "生成excel", "生成表格", "excel", "表格",
                                "成绩文件", "发我文件", "详细地址")):
            return [{"tool": "export_grades_file", "args": {"class_name": cls} if cls else {}}]
        if any(w in q for w in ("调课", "换课", "改时间", "换个时间")):
            slot = re.search(r"(周[一二三四五].{0,12}?节)", q)
            return [{"tool": "apply_schedule_change", "args": {
                "change_type": "教师互换调课" if "互换" in q or "换课" in q else "单独调课",
                "course_name": course or "程序设计基础",
                "from_slot": slot.group(1) if slot else "",
                "reason": q,
            }}]
        if any(w in q for w in ("会议", "开会", "教研活动")):
            return [{"tool": "my_meetings", "args": {}}]
        if any(w in q for w in ("发通知", "通知学生", "发个通知", "发布通知", "停课通知")):
            return [{"tool": "send_notification", "args": {
                "title": q[:40] or "课程通知", "content": q, "class_name": cls}}]
        if any(w in q for w in ("发消息", "私聊", "单独告诉")):
            return [{"tool": "send_message", "args": {"sno": "", "title": "教师消息", "content": q}}]
        if any(w in q for w in ("平均分", "及格率", "分析", "统计", "最高分", "班级情况")):
            return [{"tool": "class_analysis", "args": {"class_name": cls, "course_name": course}}]
        if any(w in q for w in ("成绩", "分数", "考了多少", "挂科")):
            return [{"tool": "query_student_grades", "args": {"class_name": cls, "course_name": course}}]
        if any(w in q for w in ("课表", "上课", "几节课", "有课", "什么课")):
            return [{"tool": "my_timetable", "args": {"weekday": day}}]
        if any(w in q for w in ("上网", "搜索", "查资料", "搜一下", "网上查")):
            return [{"tool": "web_search", "args": {"query": q}}]
        if any(w in q for w in ("规章", "规定", "办法", "政策", "调课流程", "学分")):
            return [{"tool": "rag_search", "args": {"question": q}}]
        if any(w in q for w in ("功能", "开发", "能不能用", "上线")):
            return [{"tool": "check_feature", "args": {"feature_name": q}}]
        return []

    # ---------------- 学生端规则 ----------------
    if any(w in q for w in ("老师", "谁教", "任课", "谁上")):
        return [{"tool": "query_course_teacher", "args": {"course_name": course} if course else {}}]
    if any(w in q for w in ("日历", "日程", "这周", "下周", "这个月", "本月", "安排")):
        return [{"tool": "query_calendar", "args": {}}]
    if any(w in q for w in ("上网", "搜索", "查资料", "搜一下", "网上查", "推荐书", "资料")):
        return [{"tool": "web_search", "args": {"query": q}}]
    apply_map = {"创新创业": "创新创业报名", "转专业": "转专业申请", "重修": "重修报名",
                 "学分认定": "学分认定", "英语认定": "大学英语学分认定", "学籍异动": "学籍异动申请",
                 "报到注册": "自主报到注册"}
    if any(w in q for w in ("报名", "提交申请", "我要申请")):
        for word, app_type in apply_map.items():
            if word in q:
                return [{"tool": "submit_application",
                         "args": {"app_type": app_type, "title": app_type, "detail": q}}]
    if "补考" in q:
        return [{"tool": "query_makeup", "args": {}}]
    if any(w in q for w in ("教材", "课本", "书费", "书多少钱")):
        return [{"tool": "query_textbooks", "args": {}}]
    if any(w in q for w in ("培养方案", "学分要求", "要修多少")):
        return [{"tool": "query_training_plan", "args": {}}]
    if any(w in q for w in ("选修", "自主选课", "选一门", "有什么课可以选")):
        return [{"tool": "query_electives", "args": {}}]
    if ("预约" in q or "预定" in q) and "考试" in q:
        return [{"tool": "reserve_exam", "args": {"course_name": course or "", "session": "上午"}}]
    if any(w in q for w in ("空闲教室", "空教室", "没课的教室", "自习教室")):
        return [{"tool": "query_free_classrooms", "args": {"weekday": day or 1, "section": sec}}]
    if any(w in q for w in ("成绩", "分数", "多少分", "绩点", "挂科", "总分")):
        return [{"tool": "query_grades", "args": {"course_name": course} if course else {}}]
    if any(w in q for w in ("考试", "考场", "什么时候考")):
        return [{"tool": "query_exams", "args": {}}]
    if any(w in q for w in ("通知", "公告", "教务处发的")):
        return [{"tool": "list_notifications", "args": {}}]
    if any(w in q for w in ("消息", "私信", "老师找我")):
        return [{"tool": "list_messages", "args": {}}]
    if any(w in q for w in ("选课", "选了什么", "已选课程", "我的课")):
        return [{"tool": "my_enrollments", "args": {}}]
    if any(w in q for w in ("课表", "上课", "有课", "几节课", "教室", "什么课", "啥课", "上什么")):
        return [{"tool": "query_timetable", "args": {"weekday": day}}]
    if any(w in q for w in ("个人信息", "我是谁", "学号", "手机号", "我的班级", "辅导员")):
        return [{"tool": "my_profile", "args": {}}]
    if any(w in q for w in ("建议", "怎么学", "学习方法", "如何提高", "复习", "规划", "跟不上")):
        return [{"tool": "rag_search", "args": {"question": q}}, {"tool": "study_advice", "args": {"question": q}}]
    if any(w in q for w in ("转专业", "休学", "复学", "学分认定", "学位", "规定", "流程", "怎么办")):
        return [{"tool": "rag_search", "args": {"question": q}}]
    if any(w in q for w in ("功能", "开发", "能不能用", "上线", "入口")):
        return [{"tool": "check_feature", "args": {"feature_name": q}}]
    return []


def compose_answer(question: str, results: list[dict]) -> str:
    """12.3 离线作答：把每个工具返回的 message 拼成温柔的一段话。"""
    blocked = check(question)
    if blocked:
        return blocked
    if not results:
        return ("嗯…这句话我还没完全听懂呢。你可以这样问我：\n"
                "· 我上学期高数考了多少分\n"
                "· 这周三我有什么课\n"
                "· 帮我预约大学英语的考试\n"
                "· 转专业需要什么条件\n"
                "也可以直接点左边的菜单，我都在的～")

    parts = [str(r.get("message") or "").strip() for r in results]
    text = "\n".join(p for p in parts if p)
    ui_hint = "".join("已为你打开「" + str(a.get("label", "对应页面")) + "」。"
                      for r in results for a in (r.get("ui") or []))
    if ui_hint:
        text += "\n" + ui_hint
    return text + "\n\n还有其他想查的，随时和我说～"
