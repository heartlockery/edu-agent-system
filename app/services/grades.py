"""
模块 7 · 成绩 Excel 读写
--------------------------------------------------------------------
作用：教师端把桌面上的 Excel 成绩表上传 -> 解析成字典 -> 写库；
      也可以从数据库导出 Excel，供教师下载。
说明：用 openpyxl 直接读写（不依赖 pandas 的 DataFrame 结构），
      并用 asyncio.to_thread 包一层，避免阻塞事件循环。
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook

from app.config import EXPORT_DIR

# 7.1 表头约定：前 3 列固定为身份列，第 4 列起每列一门课
IDENTITY_HEADERS = ["学号", "姓名", "班级"]
FIXED_TAIL = ["总分", "平均分", "总学分", "平均绩点"]


def grade_point(score: float) -> float:
    """7.2 百分制 -> 绩点（常见 4.0 制换算，可按学校规则调整）。"""
    if score >= 90:
        return 4.0
    if score >= 85:
        return 3.7
    if score >= 82:
        return 3.3
    if score >= 78:
        return 3.0
    if score >= 75:
        return 2.7
    if score >= 72:
        return 2.3
    if score >= 68:
        return 2.0
    if score >= 64:
        return 1.5
    if score >= 60:
        return 1.0
    return 0.0


def parse_grade_workbook(path: str | Path) -> tuple[list[dict], list[str]]:
    """7.3 解析教师上传的成绩表：返回 (每行成绩, 课程列名)。

    期望格式（与教师端下载的模板一致）：
        学号 | 姓名 | 班级 | 高等数学A | 大学英语 | ... | 总分 | 平均分
    """
    wb = load_workbook(filename=str(path), data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return [], []

    header = [str(c).strip() if c is not None else "" for c in rows[0]]
    course_cols = [h for h in header[3:] if h and h not in FIXED_TAIL]

    records: list[dict] = []
    for row in rows[1:]:
        if not row or row[0] is None:
            continue
        base = {
            "sno": str(row[0]).strip(),
            "name": str(row[1]).strip() if len(row) > 1 and row[1] else "",
            "class_name": str(row[2]).strip() if len(row) > 2 and row[2] else "",
            "grades": {},
        }
        for idx, course in enumerate(course_cols):
            col = 3 + idx
            value = row[col] if col < len(row) else None
            if value is None or value == "":
                continue
            try:
                base["grades"][course] = float(value)
            except (TypeError, ValueError):
                continue
        if base["grades"]:
            records.append(base)
    return records, course_cols


def summarize(rows: list[dict]) -> dict:
    """7.4 汇总统计：平均分、及格率、最高分、最低分（教师端成绩分析用）。"""
    if not rows:
        return {"count": 0, "avg_score": 0, "pass_rate": 0, "max_score": 0, "min_score": 0}

    scores = [float(s) for r in rows for s in r.get("grades", {}).values()]
    if not scores:
        return {"count": len(rows), "avg_score": 0, "pass_rate": 0, "max_score": 0, "min_score": 0}

    passed = len([s for s in scores if s >= 60])
    return {
        "count": len(rows),
        "avg_score": round(sum(scores) / len(scores), 2),
        "pass_rate": round(passed / len(scores) * 100, 2),
        "max_score": max(scores),
        "min_score": min(scores),
    }


def write_grade_workbook(rows: list[dict], course_names: list[str], out_path: str | Path,
                         title: str = "学生成绩表") -> Path:
    """7.5 导出 Excel：表头冻结 + 列宽自适应，教师可直接二次编辑。"""
    wb = Workbook()
    ws = wb.active
    ws.title = title[:28]
    ws.append(IDENTITY_HEADERS + course_names + FIXED_TAIL)

    for r in rows:
        grades = r.get("grades", {})
        values = [float(grades.get(c, 0) or 0) for c in course_names]
        total = round(sum(values), 2)
        avg = round(total / max(len(values), 1), 2)
        credits = round(sum(r.get("credits", {}).get(c, 3.0) for c in course_names), 1)
        gpa = round(sum(grade_point(v) for v in values) / max(len(values), 1), 2)
        ws.append([r.get("sno", ""), r.get("name", ""), r.get("class_name", "")]
                  + values + [total, avg, credits, gpa])

    ws.freeze_panes = "A2"
    for col in ws.columns:
        width = max(len(str(c.value or "")) for c in col) + 4
        ws.column_dimensions[col[0].column_letter].width = min(max(width, 10), 22)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return out_path


async def export_grades_async(rows: list[dict], course_names: list[str],
                              filename: str | None = None) -> Path:
    """7.6 异步包装：供 /api/teacher/grades/export 与 AI 工具共同调用。"""
    filename = filename or "成绩导出_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".xlsx"
    out = EXPORT_DIR / filename
    return await asyncio.to_thread(write_grade_workbook, rows, course_names, out)
