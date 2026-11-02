"""
模块 32 · 增量补数据脚本（已部署环境用）
--------------------------------------------------------------------
作用：新版新增了 applications / proctors / textbooks 三张表。
      Web 服务重启时 create_all 会自动建表，本脚本负责把「教材、监考、演示调课申请」补进去，
      不碰已有的学生、成绩、课表数据。
用法：python scripts/seed_extra.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from sqlalchemy import func, select                    # noqa: E402

from app.db.models import Proctor, ScheduleChangeRequest, Textbook, TimetableEntry  # noqa: E402
from app.db.session import SessionLocal, init_db       # noqa: E402
from app.services.curriculum import TEXTBOOKS          # noqa: E402

PROCTORS = [
    ("T1001", "张伟", "数据结构与算法", "2025-06-23", "上午 09:00-11:00", "主楼A203", "主监考"),
    ("T1001", "张伟", "面向对象程序设计", "2025-06-25", "下午 14:00-16:00", "实验楼C302", "副监考"),
    ("T1002", "李强", "数据库原理", "2025-06-24", "上午 09:00-11:00", "主楼A102", "主监考"),
    ("T1004", "陈晨", "计算机网络", "2025-06-26", "下午 14:00-16:00", "主楼B201", "主监考"),
]


async def main() -> int:
    await init_db()                     # 新表自动创建（幂等）
    async with SessionLocal() as db:
        books = (await db.execute(select(func.count()).select_from(Textbook))).scalar_one()
        if not books:
            for b in TEXTBOOKS:
                db.add(Textbook(course_code=b["course_code"], course_name=b["course_name"],
                                name=b["name"], isbn=b["isbn"], publisher=b["publisher"],
                                price=b["price"], status=b["status"]))
            print("教材已补入：" + str(len(TEXTBOOKS)) + " 本")
        else:
            print("教材已存在，跳过：" + str(books) + " 本")

        proctors = (await db.execute(select(func.count()).select_from(Proctor))).scalar_one()
        if not proctors:
            for tno, name, course, day, session, room, duty in PROCTORS:
                db.add(Proctor(teacher_tno=tno, teacher_name=name, course_name=course,
                               exam_date=day, session=session, room=room, duty=duty))
            print("监考任务已补入：" + str(len(PROCTORS)) + " 条")
        else:
            print("监考任务已存在，跳过：" + str(proctors) + " 条")

        pending = (await db.execute(select(func.count()).select_from(ScheduleChangeRequest))).scalar_one()
        if not pending:
            first = (await db.execute(select(TimetableEntry))).scalars().first()
            db.add(ScheduleChangeRequest(teacher_tno="T1002", teacher_name="李强",
                                         change_type="教师互换调课", course_name="数据库原理",
                                         from_slot="周三第5-6节 主楼A102",
                                         to_slot="周四第3-4节 主楼A102", target_tno="T1004",
                                         reason="学院教研活动冲突，申请与陈晨老师互换时段",
                                         status="待审批"))
            print("演示用调课申请已补入 1 条（" + (first.course_name if first else "") + "）")
        else:
            print("调课申请已存在，跳过：" + str(pending) + " 条")

        await db.commit()
    print("增量数据完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
