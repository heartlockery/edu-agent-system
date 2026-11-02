"""
模块 8 · 考试计划（静态教务数据）
--------------------------------------------------------------------
作用：考试信息查询、考试预约都以这份计划为准；
      真实项目里它应该来自教务处的排考接口，这里用可维护的常量模拟。
"""

from __future__ import annotations

# 8.1 上学期期末考试安排（与成绩表课程对应）
EXAM_PLAN: list[dict] = [
    {"course_code": "CS101", "course_name": "程序设计基础", "exam_date": "2025-01-06",
     "session": "上午 09:00-11:00", "room": "主楼A101"},
    {"course_code": "MA101", "course_name": "高等数学A(上)", "exam_date": "2025-01-08",
     "session": "上午 09:00-11:00", "room": "主楼A102"},
    {"course_code": "EN101", "course_name": "大学英语(一)", "exam_date": "2025-01-10",
     "session": "下午 14:00-16:00", "room": "外语楼B201"},
    {"course_code": "CS102", "course_name": "计算机导论", "exam_date": "2025-01-12",
     "session": "下午 14:00-16:00", "room": "主楼A203"},
    {"course_code": "MA102", "course_name": "离散数学", "exam_date": "2025-01-14",
     "session": "上午 09:00-11:00", "room": "主楼A105"},
    {"course_code": "PE101", "course_name": "大学体育(一)", "exam_date": "2025-01-15",
     "session": "上午 10:00-11:30", "room": "体育馆"},
    {"course_code": "SZ101", "course_name": "思想道德与法治", "exam_date": "2025-01-16",
     "session": "下午 14:00-16:00", "room": "主楼A301"},
]

# 8.2 允许预约的时段，学生端「考试预约」下拉框直接用它
RESERVE_SESSIONS = ["上午", "下午", "晚上"]


def find_exam(course_key: str) -> dict | None:
    """按课程名或课程号找考试安排（AI 用自然语言说课程名也能匹配）。"""
    key = (course_key or "").strip()
    for item in EXAM_PLAN:
        if key and (key == item["course_code"] or key in item["course_name"]
                    or item["course_name"] in key):
            return item
    return None


def all_exams() -> list[dict]:
    return [dict(x) for x in EXAM_PLAN]
