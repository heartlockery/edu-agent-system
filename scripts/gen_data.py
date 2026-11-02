"""
模块 29 · 模拟数据生成器（一次性生成 JSON + 两个 Excel）
--------------------------------------------------------------------
生成内容：
    1. data/classes.json      3 个班（数据科学2401/2402/2403）
    2. data/teachers.json     5 位教师（4 位计算机 + 1 位思政）
    3. data/courses.json      本学期 7 门课（2 位老师各带 2 门）
    4. data/last_courses.json 上学期 7 门课（成绩表用）
    5. data/students.json     3 × 60 = 180 名学生
    6. data/timetable.json    3 份课表（差异较小）
    7. data/成绩_2024-2025-1_上学期.xlsx
    8. data/课表_数据科学2401-2403.xlsx （3 个 sheet）
运行：python scripts/gen_data.py
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

# 23.1 班级：3 个班，每班 60 人
CLASSES = [
    {"name": "数据科学2401", "grade": "2024", "major": "数据科学与大数据技术", "advisor": "孙老师"},
    {"name": "数据科学2402", "grade": "2024", "major": "数据科学与大数据技术", "advisor": "周老师"},
    {"name": "数据科学2403", "grade": "2024", "major": "数据科学与大数据技术", "advisor": "吴老师"},
]

# 23.2 教师：前 4 位计算机相关，最后 1 位思政；张伟、李强各带 2 门课
TEACHERS = [
    {"tno": "T1001", "name": "张伟", "title": "副教授", "dept": "计算机学院",
     "research": "数据结构与算法、程序设计教学", "phone": "13900001001", "email": "zhangwei@univ.edu.cn"},
    {"tno": "T1002", "name": "李强", "title": "讲师", "dept": "计算机学院",
     "research": "计算机体系结构、数据库系统", "phone": "13900001002", "email": "liqiang@univ.edu.cn"},
    {"tno": "T1003", "name": "王芳", "title": "副教授", "dept": "计算机学院",
     "research": "高等数学、数值计算", "phone": "13900001003", "email": "wangfang@univ.edu.cn"},
    {"tno": "T1004", "name": "陈晨", "title": "讲师", "dept": "计算机学院",
     "research": "计算机网络、网络安全", "phone": "13900001004", "email": "chenchen@univ.edu.cn"},
    {"tno": "T1005", "name": "赵敏", "title": "讲师", "dept": "马克思主义学院",
     "research": "思想政治教育", "phone": "13900001005", "email": "zhaomin@univ.edu.cn"},
]

# 23.3 本学期 7 门课：张伟(2) 李强(2) 王芳(1) 陈晨(1) 赵敏(1)
COURSES = [
    {"code": "CS201", "name": "数据结构与算法", "credit": 4.0, "hours": 64, "category": "专业必修",
     "teacher_tno": "T1001", "teacher_name": "张伟", "semester": "2024-2025-2"},
    {"code": "CS202", "name": "面向对象程序设计", "credit": 3.0, "hours": 48, "category": "专业必修",
     "teacher_tno": "T1001", "teacher_name": "张伟", "semester": "2024-2025-2"},
    {"code": "CS203", "name": "计算机组成原理", "credit": 3.0, "hours": 48, "category": "专业必修",
     "teacher_tno": "T1002", "teacher_name": "李强", "semester": "2024-2025-2"},
    {"code": "CS204", "name": "数据库原理", "credit": 3.0, "hours": 48, "category": "专业必修",
     "teacher_tno": "T1002", "teacher_name": "李强", "semester": "2024-2025-2"},
    {"code": "MA201", "name": "高等数学A(下)", "credit": 5.0, "hours": 80, "category": "通识必修",
     "teacher_tno": "T1003", "teacher_name": "王芳", "semester": "2024-2025-2"},
    {"code": "CS205", "name": "计算机网络", "credit": 3.0, "hours": 48, "category": "专业必修",
     "teacher_tno": "T1004", "teacher_name": "陈晨", "semester": "2024-2025-2"},
    {"code": "SZ201", "name": "中国近现代史纲要", "credit": 3.0, "hours": 48, "category": "通识必修",
     "teacher_tno": "T1005", "teacher_name": "赵敏", "semester": "2024-2025-2"},
]

# 23.4 上学期 7 门课（成绩表用，含课程号与学分）
LAST_COURSES = [
    {"code": "CS101", "name": "程序设计基础", "credit": 3.0},
    {"code": "MA101", "name": "高等数学A(上)", "credit": 5.0},
    {"code": "EN101", "name": "大学英语(一)", "credit": 3.0},
    {"code": "CS102", "name": "计算机导论", "credit": 2.0},
    {"code": "MA102", "name": "离散数学", "credit": 3.0},
    {"code": "PE101", "name": "大学体育(一)", "credit": 1.0},
    {"code": "SZ101", "name": "思想道德与法治", "credit": 3.0},
]

# 23.5 三份课表：每班 6 个时段，班级之间只有少量差异（场地/时间错开）
TIMETABLE = [
    # ---- 数据科学2401 ----
    {"class_name": "数据科学2401", "course_code": "MA201", "course_name": "高等数学A(下)",
     "teacher_tno": "T1003", "teacher_name": "王芳", "weekday": 1, "start_section": 1,
     "end_section": 2, "location": "主楼A101", "weeks": "1-16周"},
    {"class_name": "数据科学2401", "course_code": "CS201", "course_name": "数据结构与算法",
     "teacher_tno": "T1001", "teacher_name": "张伟", "weekday": 1, "start_section": 3,
     "end_section": 4, "location": "主楼A203", "weeks": "1-16周"},
    {"class_name": "数据科学2401", "course_code": "CS202", "course_name": "面向对象程序设计",
     "teacher_tno": "T1001", "teacher_name": "张伟", "weekday": 2, "start_section": 1,
     "end_section": 2, "location": "实验楼C302", "weeks": "1-16周"},
    {"class_name": "数据科学2401", "course_code": "CS203", "course_name": "计算机组成原理",
     "teacher_tno": "T1002", "teacher_name": "李强", "weekday": 3, "start_section": 3,
     "end_section": 4, "location": "主楼A102", "weeks": "1-16周"},
    {"class_name": "数据科学2401", "course_code": "CS205", "course_name": "计算机网络",
     "teacher_tno": "T1004", "teacher_name": "陈晨", "weekday": 4, "start_section": 5,
     "end_section": 6, "location": "主楼B201", "weeks": "1-16周"},
    {"class_name": "数据科学2401", "course_code": "SZ201", "course_name": "中国近现代史纲要",
     "teacher_tno": "T1005", "teacher_name": "赵敏", "weekday": 5, "start_section": 1,
     "end_section": 2, "location": "主楼A301", "weeks": "1-16周"},
    # ---- 数据科学2402（课程相同，时段错开）----
    {"class_name": "数据科学2402", "course_code": "MA201", "course_name": "高等数学A(下)",
     "teacher_tno": "T1003", "teacher_name": "王芳", "weekday": 1, "start_section": 1,
     "end_section": 2, "location": "主楼A101", "weeks": "1-16周"},
    {"class_name": "数据科学2402", "course_code": "CS202", "course_name": "面向对象程序设计",
     "teacher_tno": "T1001", "teacher_name": "张伟", "weekday": 1, "start_section": 3,
     "end_section": 4, "location": "实验楼C302", "weeks": "1-16周"},
    {"class_name": "数据科学2402", "course_code": "CS201", "course_name": "数据结构与算法",
     "teacher_tno": "T1001", "teacher_name": "张伟", "weekday": 2, "start_section": 3,
     "end_section": 4, "location": "主楼A203", "weeks": "1-16周"},
    {"class_name": "数据科学2402", "course_code": "CS203", "course_name": "计算机组成原理",
     "teacher_tno": "T1002", "teacher_name": "李强", "weekday": 3, "start_section": 5,
     "end_section": 6, "location": "主楼A102", "weeks": "1-16周"},
    {"class_name": "数据科学2402", "course_code": "CS205", "course_name": "计算机网络",
     "teacher_tno": "T1004", "teacher_name": "陈晨", "weekday": 4, "start_section": 1,
     "end_section": 2, "location": "主楼B201", "weeks": "1-16周"},
    {"class_name": "数据科学2402", "course_code": "SZ201", "course_name": "中国近现代史纲要",
     "teacher_tno": "T1005", "teacher_name": "赵敏", "weekday": 5, "start_section": 3,
     "end_section": 4, "location": "主楼A301", "weeks": "1-16周"},
    # ---- 数据科学2403（高数移到周一 5-6 节，其余小幅错开）----
    {"class_name": "数据科学2403", "course_code": "MA201", "course_name": "高等数学A(下)",
     "teacher_tno": "T1003", "teacher_name": "王芳", "weekday": 1, "start_section": 5,
     "end_section": 6, "location": "主楼A101", "weeks": "1-16周"},
    {"class_name": "数据科学2403", "course_code": "CS201", "course_name": "数据结构与算法",
     "teacher_tno": "T1001", "teacher_name": "张伟", "weekday": 2, "start_section": 1,
     "end_section": 2, "location": "主楼A203", "weeks": "1-16周"},
    {"class_name": "数据科学2403", "course_code": "CS202", "course_name": "面向对象程序设计",
     "teacher_tno": "T1001", "teacher_name": "张伟", "weekday": 2, "start_section": 5,
     "end_section": 6, "location": "实验楼C302", "weeks": "1-16周"},
    {"class_name": "数据科学2403", "course_code": "CS203", "course_name": "计算机组成原理",
     "teacher_tno": "T1002", "teacher_name": "李强", "weekday": 3, "start_section": 7,
     "end_section": 8, "location": "主楼A102", "weeks": "1-16周"},
    {"class_name": "数据科学2403", "course_code": "CS205", "course_name": "计算机网络",
     "teacher_tno": "T1004", "teacher_name": "陈晨", "weekday": 4, "start_section": 3,
     "end_section": 4, "location": "主楼B201", "weeks": "1-16周"},
    {"class_name": "数据科学2403", "course_code": "SZ201", "course_name": "中国近现代史纲要",
     "teacher_tno": "T1005", "teacher_name": "赵敏", "weekday": 5, "start_section": 5,
     "end_section": 6, "location": "主楼A301", "weeks": "1-16周"},
]

SURNAMES = "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳"
GIVEN = ["子涵", "浩然", "雨桐", "思远", "嘉怡", "俊杰", "欣怡", "宇轩", "梓萱", "泽宇",
         "诗涵", "皓轩", "雅静", "天佑", "若曦", "承宇", "梦琪", "文博", "一诺", "晨阳",
         "婉清", "明轩", "可欣", "志强", "佳琪", "书豪", "静怡", "锦程", "慧敏", "子墨"]


def _students(rng: random.Random) -> list[dict]:
    """23.6 生成 3 × 60 名学生：学号 2024010XY 规则，姓名不重复。"""
    out: list[dict] = []
    used: set[str] = set()
    for ci, klass in enumerate(CLASSES, start=1):
        for idx in range(1, 61):
            while True:
                name = rng.choice(SURNAMES) + rng.choice(GIVEN)
                if name not in used:
                    used.add(name)
                    break
            sno = "2024010" + str(ci) + str(idx).zfill(2)
            out.append({
                "sno": sno,
                "name": name,
                "gender": rng.choice(["男", "女"]),
                "class_name": klass["name"],
                "major": klass["major"],
                "enroll_year": "2024",
                "phone": "138" + str(rng.randint(10000000, 99999999)),
                "email": sno + "@stu.univ.edu.cn",
            })
    return out


def _grades(students: list[dict], rng: random.Random) -> list[dict]:
    """23.7 生成上学期成绩：每人一个「能力值」，保证同一个人各科成绩相关。"""
    base_mean = {"程序设计基础": 78, "高等数学A(上)": 71, "大学英语(一)": 80,
                 "计算机导论": 83, "离散数学": 74, "大学体育(一)": 86, "思想道德与法治": 85}
    out = []
    for stu in students:
        ability = rng.gauss(0, 7)
        grades = {}
        for course in LAST_COURSES:
            score = base_mean[course["name"]] + ability + rng.gauss(0, 8)
            grades[course["name"]] = round(min(100, max(38, score)), 1)
        out.append({**stu, "grades": grades})
    return out


def _grade_point(score: float) -> float:
    """23.7b 百分制 -> 绩点（与后端 app/services/grades.py 保持一致）。"""
    for line, point in ((90, 4.0), (85, 3.7), (82, 3.3), (78, 3.0), (75, 2.7),
                        (72, 2.3), (68, 2.0), (64, 1.5), (60, 1.0)):
        if score >= line:
            return point
    return 0.0


def _write_grade_excel(rows: list[dict]) -> Path:
    """23.8 写成绩表：表头与后端解析逻辑严格一致（学号/姓名/班级/课程.../总分/平均分）。"""
    wb = Workbook()
    ws = wb.active
    ws.title = "上学期成绩"
    headers = ["学号", "姓名", "班级"] + [c["name"] for c in LAST_COURSES] + ["总分", "平均分", "总学分", "平均绩点"]
    ws.append(headers)

    for row in rows:
        scores = [row["grades"][c["name"]] for c in LAST_COURSES]
        total = round(sum(scores), 1)
        avg = round(total / len(scores), 1)
        credits = round(sum(c["credit"] for c in LAST_COURSES), 1)
        gpa = round(sum(_grade_point(s) * c["credit"] for s, c in zip(scores, LAST_COURSES)) / credits, 2)
        ws.append([row["sno"], row["name"], row["class_name"]] + scores + [total, avg, credits, gpa])

    head_fill = PatternFill("solid", fgColor="1F4E78")
    thin = Side(style="thin", color="BFBFBF")
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = head_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.border = Border(left=thin, right=thin, top=thin, bottom=thin)
            cell.alignment = Alignment(horizontal="center")
    ws.freeze_panes = "A2"
    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width = max(len(str(c.value or "")) for c in col) + 4

    path = DATA_DIR / "成绩_2024-2025-1_上学期.xlsx"
    wb.save(path)
    return path


def _write_timetable_excel() -> Path:
    """23.9 写课表：一个工作簿三个 sheet，每个班一张「星期 × 节次」网格。"""
    wb = Workbook()
    wb.remove(wb.active)
    sections = [(1, 2, "1-2节 08:00-09:35"), (3, 4, "3-4节 10:05-11:40"),
                (5, 6, "5-6节 14:00-15:35"), (7, 8, "7-8节 16:05-17:40"),
                (9, 10, "9-10节 19:00-20:35")]
    weekdays = ["周一", "周二", "周三", "周四", "周五"]

    for klass in CLASSES:
        ws = wb.create_sheet(klass["name"])
        ws.append(["节次", *weekdays])
        rows = [e for e in TIMETABLE if e["class_name"] == klass["name"]]
        for start, end, label in sections:
            line = [label]
            for day in range(1, 6):
                hit = [e for e in rows if e["weekday"] == day and e["start_section"] == start]
                if hit:
                    e = hit[0]
                    line.append(e["course_name"] + "\n" + e["teacher_name"] + "\n" + e["location"])
                else:
                    line.append("")
            ws.append(line)
        ws.column_dimensions["A"].width = 22
        for col in "BCDEF":
            ws.column_dimensions[col].width = 20
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="2E7D32")
            cell.alignment = Alignment(horizontal="center")
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.freeze_panes = "B2"

    path = DATA_DIR / "课表_数据科学2401-2403.xlsx"
    wb.save(path)
    return path


def generate_all(force: bool = False) -> dict:
    """23.10 一键生成全部模拟数据（幂等，重复执行结果一致）。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(20240901)
    students = _students(rng)
    grade_rows = _grades(students, rng)

    files = {
        "classes.json": CLASSES,
        "teachers.json": TEACHERS,
        "courses.json": COURSES,
        "last_courses.json": LAST_COURSES,
        "students.json": students,
        "timetable.json": TIMETABLE,
    }
    for name, payload in files.items():
        (DATA_DIR / name).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    grade_path = _write_grade_excel(grade_rows)
    timetable_path = _write_timetable_excel()
    return {"students": len(students), "grades_file": str(grade_path), "timetable_file": str(timetable_path)}


if __name__ == "__main__":
    info = generate_all()
    print("数据生成完成：", info)
