"""
模块 6 · 功能菜单注册表
--------------------------------------------------------------------
作用：把需求里那一长串菜单（学生端 40 项左右、教师端若干项）实现成一份可配置清单。
      前端按清单渲染菜单；未实现的项统一返回「系统正在开发中」，
      AI 也能读懂 status 字段，从而回答「这个功能现在能不能用」。
"""

from __future__ import annotations

READY = "ready"            # 已实现
DEV = "developing"         # 系统正在开发中


def _item(key: str, name: str, status: str = READY, desc: str = "", endpoint: str = "",
          category: str = "信息查询") -> dict:
    return {"key": key, "name": name, "status": status, "desc": desc,
            "endpoint": endpoint, "category": category}


# ---------------------------------------------------------------
# 6.1 学生端菜单：信息查询 / 报名申请 / 信息维护 / 选课 / 考试
# ---------------------------------------------------------------
STUDENT_MENU: list[dict] = [
    # ---- 信息查询（前 9 项已实现，其余按需求标注开发中）----
    _item("notifications", "通知公告", READY, "查看教务处与教师发布的通知", "/api/student/notifications"),
    _item("my_timetable", "个人课表查询", READY, "按星期查看本人课表", "/api/student/timetable"),
    _item("class_timetable", "班级课表查询", READY, "查看本班整体课表", "/api/student/timetable"),
    _item("grades", "学生成绩查询", READY, "上学期成绩、平均分与绩点", "/api/student/grades"),
    _item("exams", "考试信息查询", READY, "考试科目、时间、地点", "/api/student/exams"),
    _item("messages", "消息列表", READY, "教师发来的点对点消息", "/api/student/messages"),
    _item("profile", "个人信息查询", READY, "学号、班级、联系方式", "/api/student/profile"),
    _item("free_classrooms", "查询空闲教室", READY, "按时间点查空闲教室", "/api/student/free-classrooms"),
    _item("selection_confirm", "学生选课情况确认", READY, "确认本学期选课结果", "/api/student/enrollments"),
    _item("selection_list", "选课名单查询", READY, "查看本班选课名单", "/api/student/selection-list"),
    _item("textbook_detail", "教材明细查询", READY, "每门课的教材、出版社、ISBN", "/api/student/textbooks"),
    _item("textbook_fee", "教材费用查询", READY, "本学期教材总费用", "/api/student/textbooks"),
    _item("academic_warning", "学业预警处理查询", READY, "按不及格学分判断是否预警", "/api/student/academic-status"),
    _item("certificate_print", "学生证书打印", DEV),
    _item("academic_status", "学生学业情况查询", READY, "已修学分、绩点、预警状态", "/api/student/academic-status"),
    _item("teaching_plan", "教学执行计划查看", READY, "本专业八学期培养方案", "/api/student/training-plan"),
    # ---- 报名申请（全部开发中，保留入口）----
    _item("status_change", "学籍异动申请", READY, "在线提交学籍异动申请",
          "/api/student/applications?app_type=学籍异动申请", category="报名申请"),
    _item("retake", "重修报名", READY, "提交重修报名并写明课程",
          "/api/student/applications?app_type=重修报名", category="报名申请"),
    _item("major_transfer", "学生转专业申请", READY, "在线提交转专业申请",
          "/api/student/applications?app_type=转专业申请", category="报名申请"),
    _item("project_signup", "教学项目报名", READY, "在线提交教学项目报名",
          "/api/student/applications?app_type=教学项目报名", category="报名申请"),
    _item("credit_recognize", "学生成绩学分认定申请", READY, "上传/填写学分认定信息",
          "/api/student/applications?app_type=学分认定", category="报名申请"),
    _item("english_credit", "大学英语学分认定申请", READY, "按四六级成绩申请认定",
          "/api/student/applications?app_type=大学英语学分认定", category="报名申请"),
    _item("makeup_confirm", "补考确认", READY, "一键确认不及格课程的补考",
          "/api/student/makeup", category="报名申请"),
    _item("graduation_makeup", "毕业补考报名", DEV, category="报名申请"),
    _item("innovation_signup", "创新创业报名", READY, "在线提交创新创业项目报名",
          "/api/student/applications?app_type=创新创业报名", category="报名申请"),
    _item("completion_cert", "结业换证报名", DEV, category="报名申请"),
    _item("qualification", "学生资格证书申请", DEV, category="报名申请"),
    _item("book_return", "学生退书申请", DEV, category="报名申请"),
    _item("course_replace", "校内课程替代申请", DEV, category="报名申请"),
    _item("credit_node_replace", "校内课程学分节点替代申请", DEV, category="报名申请"),
    _item("credit_node_replace2", "校内学分节点替代申请", DEV, category="报名申请"),
    _item("outside_replace", "校外课程学分节点替代申请", DEV, category="报名申请"),
    _item("bachelor_degree", "学士学位申请", DEV, category="报名申请"),
    _item("my_applications", "我的申请记录", READY, "查看所有申请及审批进度",
          "/api/student/applications", category="报名申请"),
    # ---- 信息维护 ----
    _item("profile_maintain", "学生个人信息维护", READY, "修改手机号与邮箱", "/api/student/profile",
          category="信息维护"),
    _item("training_plan", "个人培养方案", READY, "本专业八学期课程与学分要求",
          "/api/student/training-plan", category="信息维护"),
    _item("innovation_credit", "创新创业学分确认", READY, "确认已获得的创新学分",
          "/api/student/applications?app_type=创新创业学分", category="信息维护"),
    _item("self_register", "学生自主报到注册", READY, "在线完成学期报到注册",
          "/api/student/applications?app_type=自主报到注册", category="信息维护"),
    # ---- 选课 ----
    _item("self_course", "自主选课", READY, "从选修课池中选课", "/api/student/electives", category="选课"),
    _item("textbook_order", "教材预订", READY, "预订本学期教材", "/api/student/textbooks", category="选课"),
    # ---- 考试 ----
    _item("exam_appointment", "考试预约", READY, "预约课程考试时段（可让 AI 代办）",
          "/api/student/exams/reserve", category="考试"),
]

# ---------------------------------------------------------------
# 6.2 教师端菜单
# ---------------------------------------------------------------
TEACHER_MENU: list[dict] = [
    _item("send_notification", "发送通知", READY, "向全体或指定班级发通知", "/api/teacher/notifications",
          category="学生管理"),
    _item("send_message", "给学生发消息", READY, "点对点消息", "/api/teacher/messages", category="学生管理"),
    _item("class_list", "班级列表", READY, "所带班级与学生人数", "/api/teacher/classes", category="学生管理"),
    _item("student_list", "学生名单", READY, "按班级查学生", "/api/teacher/students", category="学生管理"),
    _item("query_grades", "查询学生成绩", READY, "按班级/学号查成绩", "/api/teacher/grades", category="成绩管理"),
    _item("upload_grades", "上传成绩 Excel", READY, "从桌面 Excel 直接导入数据库", "/api/teacher/grades/upload",
          category="成绩管理"),
    _item("export_grades", "导出成绩文件", READY, "生成 Excel 并返回下载地址", "/api/teacher/grades/export",
          category="成绩管理"),
    _item("my_timetable", "我的课程表", READY, "教师本人课表与上课时间", "/api/teacher/timetable", category="教学安排"),
    _item("schedule_change", "调课申请", READY, "单独调课 / 与同事互换课程", "/api/teacher/schedule/change",
          category="教学安排"),
    _item("meetings", "会议安排", READY, "查看本人会议时间地点", "/api/teacher/meetings", category="教学安排"),
    _item("class_analysis", "班级成绩分析", READY, "平均分/及格率/最高分", "/api/teacher/grades/analysis",
          category="成绩管理"),
    _item("grade_edit", "成绩录入与修改", DEV, category="成绩管理"),
    _item("proctor", "监考安排", READY, "查看与新增本人的监考任务", "/api/teacher/proctor", category="教学安排"),
    _item("textbook_manage", "教材管理", READY, "教材征订与状态维护", "/api/teacher/textbooks", category="教学安排"),
    _item("approve_change", "调课审批", READY, "审批待处理的调课申请", "/api/teacher/schedule/pending",
          category="教学安排"),
]


# ---------------------------------------------------------------
# 6.2b 管理员菜单（不接入 AI，纯后台管理）
# ---------------------------------------------------------------
ADMIN_MENU: list[dict] = [
    _item("admin_students", "学生账号管理", READY, "查看/新增/删除学生账号，重置密码",
          "/api/admin/students", category="账号管理"),
    _item("admin_teachers", "教师账号管理", READY, "查看/新增/删除教师账号，重置密码",
          "/api/admin/teachers", category="账号管理"),
    _item("admin_recovery", "找回申请处理", READY, "学生提交的找回/重置密码申请，一键重置",
          "/api/admin/recovery", category="账号管理"),
    _item("admin_applications", "学生申请审批", READY, "补考确认、学分认定、教材预订等申请审批",
          "/api/admin/applications", category="账号管理"),
    _item("admin_classes", "班级概览", READY, "各班人数、平均分、及格率、学分",
          "/api/admin/classes-overview", category="数据"),
    _item("admin_stats", "数据总览", READY, "学生数、教师数、班级数、成绩条数",
          "/api/admin/stats", category="系统"),
    _item("admin_import", "批量导入学生账号", READY, "上传 Excel 批量建号，默认密码 123456",
          "/api/admin/students/import", category="账号管理"),
    _item("admin_role", "管理员权限配置", DEV, category="系统"),
]


def menu_for(role: str) -> list[dict]:
    """6.3 按角色返回菜单，并按大类分组，前端直接渲染。"""
    items = TEACHER_MENU if role == "teacher" else (ADMIN_MENU if role == "admin" else STUDENT_MENU)
    grouped: dict[str, list[dict]] = {}
    for it in items:
        grouped.setdefault(it["category"], []).append(it)
    return [{"category": k, "items": v} for k, v in grouped.items()]


def find_feature(key_or_name: str) -> dict | None:
    """6.4 模糊匹配一个功能：AI 说「帮我打开补考确认」时用来判断是否开发中。"""
    text = (key_or_name or "").strip()
    if not text:
        return None
    for it in STUDENT_MENU + TEACHER_MENU + ADMIN_MENU:
        if text == it["key"] or text == it["name"] or text in it["name"]:
            return it
    return None
