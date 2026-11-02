"""
模块 30 · 端到端冒烟测试（交付前的统一验收）
--------------------------------------------------------------------
不启动端口，用 httpx 的 ASGITransport 直接打 FastAPI 应用，覆盖：
    登录(学生/教师/管理员) -> 学生查成绩/课表 -> AI 一句话查成绩/查课表/问规章
    -> 教师查成绩/导出 Excel -> 管理员统计/找回审批 -> 管理员禁止用 AI
运行：python scripts/smoke_test.py
说明：使用独立的 data/smoke.db，不影响正式库；没有配置大模型 Key 时走离线规则模式。
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

# 必须赶在 import app 之前设置，保证测试库独立；
# 想用 PostgreSQL 验证同一套用例：export SMOKE_DB_URL=postgresql+asyncpg://...
os.environ["DATABASE_URL"] = os.environ.get(
    "SMOKE_DB_URL", "sqlite+aiosqlite:///" + (BASE / "data" / "smoke.db").as_posix())
os.environ.pop("LANGCHAIN_API_KEY", None)

from app.main import app                      # noqa: E402
from app.config import DATA_DIR               # noqa: E402

PASS, FAIL = [], []
try:                                          # Windows 控制台中文输出
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(("  [PASS] " if cond else "  [FAIL] ") + name + (("  -> " + detail) if detail and not cond else ""))


async def main() -> int:
    import httpx

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=60) as c:
            print("== 1. 健康检查与登录 ==")
            r = await c.get("/api/health")
            check("健康检查", r.status_code == 200 and r.json()["ok"])

            r = await c.post("/api/auth/login", json={"role": "student", "username": "2024010101", "password": "123456"})
            check("学生登录", r.status_code == 200 and r.json()["profile"]["class_name"] == "数据科学2401",
                  r.text[:120])
            stu_token = r.json()["token"]
            sh = {"Authorization": "Bearer " + stu_token}

            r = await c.post("/api/auth/login", json={"role": "teacher", "username": "T1001", "password": "123456"})
            check("教师登录", r.status_code == 200 and r.json()["profile"]["name"] == "张伟", r.text[:120])
            th = {"Authorization": "Bearer " + r.json()["token"]}

            r = await c.post("/api/auth/login", json={"role": "admin", "username": "10214823205", "password": "123456"})
            check("管理员登录", r.status_code == 200 and r.json()["role"] == "admin", r.text[:120])
            ah = {"Authorization": "Bearer " + r.json()["token"]}

            print("== 2. 学生端数据接口 ==")
            r = await c.get("/api/student/grades", headers=sh)
            g = r.json()
            check("学生成绩 7 门", r.status_code == 200 and len(g["items"]) == 7,
                  str(len(g.get("items", []))) + " 门")
            check("成绩汇总含绩点", g["summary"]["gpa"] > 0)

            r = await c.get("/api/student/timetable", headers=sh)
            check("课表 6 个时段", len(r.json()["items"]) == 6, str(len(r.json().get("items", []))))

            r = await c.get("/api/auth/menu", headers=sh)
            menus = r.json()["menus"]
            ready = sum(1 for grp in menus for it in grp["items"] if it["status"] == "ready")
            dev = sum(1 for grp in menus for it in grp["items"] if it["status"] != "ready")
            check("学生菜单含已实现与开发中", ready >= 25 and dev >= 5, "ready=" + str(ready) + " dev=" + str(dev))

            print("== 3. AI 一句话直达（离线规则模式） ==")
            r = await c.post("/api/chat", headers=sh, json={"message": "我上学期高数考了多少分", "session_id": "s1"})
            ans = r.json()
            check("AI 查成绩走 query_grades",
                  r.status_code == 200 and any(t["tool"] == "query_grades" for t in ans["tool_calls"]),
                  str(ans.get("tool_calls")))
            check("AI 查成绩答出分数", "分" in ans["answer"] and "高等数学" in ans["answer"], ans["answer"][:120])

            r = await c.post("/api/chat", headers=sh, json={"message": "这周三我有什么课", "session_id": "s1"})
            ans2 = r.json()
            check("AI 查课表走 query_timetable",
                  any(t["tool"] == "query_timetable" for t in ans2["tool_calls"]), str(ans2.get("tool_calls")))

            r = await c.post("/api/chat", headers=sh, json={"message": "转专业需要什么条件", "session_id": "s2"})
            ans3 = r.json()
            check("RAG 命中教务规章",
                  any(t["tool"] == "rag_search" for t in ans3["tool_calls"]) and "转专业" in ans3["answer"],
                  ans3["answer"][:120])

            r = await c.post("/api/chat", headers=sh, json={"message": "帮我预约大学英语的考试", "session_id": "s3"})
            ans4 = r.json()
            check("AI 预约考试",
                  any(t["tool"] == "reserve_exam" for t in ans4["tool_calls"]) and "预约" in ans4["answer"],
                  ans4["answer"][:120])

            print("== 4. 教师端查询与导出 ==")
            r = await c.get("/api/teacher/grades?class_name=2401", headers=th)
            check("教师查 2401 班成绩 60 人", len(r.json()["items"]) == 60,
                  str(len(r.json().get("items", []))))

            r = await c.post("/api/chat", headers=th, json={"message": "把2401班成绩导成excel发我", "session_id": "t1"})
            t_ans = r.json()
            check("AI 导出成绩走 export_grades_file",
                  any(t["tool"] == "export_grades_file" for t in t_ans["tool_calls"]), str(t_ans.get("tool_calls")))
            check("导出文件真实落盘", "xlsx" in t_ans["answer"] and list((DATA_DIR / "exports").glob("*.xlsx")) != [],
                  t_ans["answer"][:160])

            r = await c.post("/api/teacher/notifications",
                             headers=th, json={"title": "冒烟测试通知", "content": "明天停课", "class_name": "2401"})
            check("教师发通知覆盖 60 人", r.status_code == 200 and r.json()["count"] == 60, r.text[:120])

            r = await c.get("/api/teacher/meetings", headers=th)
            check("教师会议安排", len(r.json()["items"]) >= 2)

            print("== 5. 管理员端（无 AI） ==")
            r = await c.get("/api/admin/stats", headers=ah)
            st = r.json()
            check("数据总览 180 名学生", st["students"] == 180 and st["teachers"] == 5, str(st))

            r = await c.post("/api/auth/recovery", json={"role": "student", "name": "谢若曦",
                                                         "class_name": "数据科学2401", "contact": "13800001111"})
            check("免登录提交找回申请", r.status_code == 200, r.text[:120])

            r = await c.get("/api/admin/recovery", headers=ah)
            pending = [x for x in r.json()["items"] if x["status"] == "待处理"]
            check("管理员看到待处理申请", len(pending) >= 1, str(len(pending)))

            rid = pending[0]["id"]
            r = await c.post("/api/admin/recovery/" + str(rid) + "/handle",
                             headers=ah, json={"action": "approve", "new_password": "123456"})
            check("审批通过并重置密码", r.status_code == 200 and r.json().get("ok"), r.text[:160])

            r = await c.post("/api/chat", headers=ah, json={"message": "查一下成绩", "session_id": "a1"})
            check("管理员禁止使用 AI", r.status_code == 403, str(r.status_code))

            print("== 5b. 新开放功能 ==")
            r = await c.get("/api/student/calendar", headers=sh)
            check("首页日历接口", r.status_code == 200 and len(r.json()["days"]) >= 28, str(r.status_code))

            r = await c.get("/api/chat/greeting", headers=sh)
            check("学生打招呼", r.status_code == 200 and "同学" in r.json()["text"], r.text[:120])

            r = await c.get("/api/student/todos", headers=sh)
            td = r.json()
            check("首页待办聚合", r.status_code == 200 and "applications" in td and "upcoming_exams" in td,
                  r.text[:140])

            r = await c.get("/api/student/makeup", headers=sh)
            check("补考名单接口", r.status_code == 200 and "items" in r.json(), r.text[:120])

            r = await c.post("/api/student/makeup/confirm", headers=sh, json={"course_codes": []})
            check("补考确认可提交", r.status_code == 200, r.text[:120])

            r = await c.post("/api/student/applications", headers=sh,
                             json={"app_type": "学分认定", "title": "CET-4 认定", "detail": "已通过 CET-4"})
            check("学分认定申请", r.status_code == 200 and r.json().get("ok"), r.text[:120])

            r = await c.get("/api/student/training-plan", headers=sh)
            check("培养方案 8 学期", len(r.json()["plan"]) == 8, r.text[:120])

            r = await c.get("/api/student/textbooks", headers=sh)
            check("教材明细含费用", r.status_code == 200 and r.json()["total_fee"] > 0, r.text[:120])

            r = await c.get("/api/student/electives", headers=sh)
            check("选修课池", len(r.json()["items"]) >= 4, r.text[:120])

            r = await c.get("/api/student/academic-status", headers=sh)
            check("学业情况", r.status_code == 200 and "warning" in r.json(), r.text[:120])

            r = await c.get("/api/student/selection-list", headers=sh)
            check("选课名单 60 人", len(r.json()["items"]) == 60, str(len(r.json().get("items", []))))

            r = await c.get("/api/teacher/classes", headers=th)
            check("教师班级列表 3 个班", len(r.json()["items"]) == 3, r.text[:120])

            r = await c.get("/api/teacher/proctor", headers=th)
            check("监考安排", len(r.json()["items"]) >= 2, r.text[:120])

            r = await c.get("/api/teacher/textbooks", headers=th)
            check("教材管理", len(r.json()["items"]) >= 7, r.text[:120])

            r = await c.get("/api/teacher/schedule/pending", headers=th)
            check("调课审批列表", r.status_code == 200, r.text[:120])

            print("== 5c. 内容边界与温柔语气 ==")
            r = await c.post("/api/chat", headers=sh, json={"message": "我想打游戏，帮我查攻略", "session_id": "g1"})
            check("游戏请求被温柔拦截",
                  r.status_code == 200 and "游戏" in r.json()["answer"] and r.json()["model"] == "guard",
                  r.json().get("answer", "")[:120])

            r = await c.post("/api/chat", headers=sh, json={"message": "我的高数老师是谁", "session_id": "s4"})
            check("AI 查任课老师",
                  any(t["tool"] == "query_course_teacher" for t in r.json()["tool_calls"]),
                  str(r.json().get("tool_calls")))

            print("== 5d. 基础服务 ==")
            r = await c.get("/api/health")
            h = r.json()
            check("健康检查含数据库状态", h["ok"] and h["database"] == "up" and h["uptime_seconds"] >= 0, str(h))
            check("健康检查含模型状态", "ai" in h and "db_latency_ms" in h, str(h)[:120])

            r = await c.get("/", headers={"Accept-Encoding": "gzip"})
            check("gzip 压缩生效", r.status_code == 200 and r.headers.get("content-encoding") == "gzip",
                  str(r.headers.get("content-encoding")))

            r = await c.post("/api/auth/change-password", headers=sh,
                             json={"old_password": "123456", "new_password": "abc12345"})
            check("修改密码成功", r.status_code == 200, r.text[:120])
            r = await c.post("/api/auth/login", json={"role": "student", "username": "2024010101",
                                                      "password": "abc12345"})
            check("新密码可登录", r.status_code == 200, r.text[:120])
            r = await c.post("/api/auth/change-password", headers=sh,
                             json={"old_password": "abc12345", "new_password": "123456"})
            check("密码改回默认", r.status_code == 200, r.text[:120])

            r = await c.get("/api/not-exist")
            check("404 返回 JSON", r.status_code == 404 and "detail" in r.json(), r.text[:120])

            r = await c.get("/api/student/messages", headers=sh)
            msgs = r.json().get("items", [])
            if msgs:
                r = await c.post("/api/student/messages/" + str(msgs[0]["id"]) + "/read", headers=sh)
                check("消息标记已读", r.status_code == 200, r.text[:120])
            else:
                check("消息标记已读（无消息跳过）", True)

            r = await c.get("/api/teacher/messages", headers=th)
            check("教师收件箱可用", r.status_code == 200 and "items" in r.json(), r.text[:120])

            r = await c.post("/api/teacher/messages", headers=th,
                             json={"sno": "2024010101", "title": "冒烟消息", "content": "测试一下"})
            check("教师发消息成功", r.status_code == 200 and r.json().get("ok"), r.text[:120])

            r = await c.get("/api/admin/classes-overview", headers=ah)
            ov = r.json()["items"]
            check("班级概览 3 个班", r.status_code == 200 and len(ov) == 3 and ov[0]["students"] == 60, r.text[:160])

            r = await c.get("/api/admin/applications", headers=ah)
            apps = r.json()["items"]
            check("管理员看到学生申请", r.status_code == 200 and len(apps) >= 1, str(len(apps)))
            if apps:
                aid = apps[0]["id"]
                r = await c.post("/api/admin/applications/" + str(aid) + "/handle", headers=ah,
                                 json={"action": "approve", "note": "材料齐全"})
                check("管理员审批申请", r.status_code == 200 and r.json().get("ok"), r.text[:120])

            print("== 5g. 选课校验与追问 ==")
            r = await c.get("/api/student/electives", headers=sh)
            check("选修课 6 门", len(r.json()["items"]) >= 6, str(len(r.json().get("items", []))))

            r = await c.post("/api/student/electives/select", headers=sh,
                             json={"course_name": "Java程序设计"})
            check("时间冲突被拦下", r.status_code == 200 and r.json().get("ok") is False
                  and "冲突" in r.json().get("message", ""), r.text[:160])

            r = await c.post("/api/student/electives/select", headers=sh,
                             json={"course_name": "人工智能导论"})
            check("无冲突可选课", r.status_code == 200 and r.json().get("ok"), r.text[:140])

            print("== 5f. 管理员批量导入 ==")
            from io import BytesIO

            from openpyxl import Workbook

            wb = Workbook()
            ws = wb.active
            ws.append(["学号", "姓名", "班级", "性别", "手机", "邮箱"])
            ws.append(["2024010998", "测试导入甲", "数据科学2401", "男", "13800000001", "a@stu.edu.cn"])
            ws.append(["2024010999", "测试导入乙", "数据科学2401", "女", "13800000002", "b@stu.edu.cn"])
            buf = BytesIO()
            wb.save(buf)
            buf.seek(0)
            r = await c.post("/api/admin/students/import", headers=ah,
                             files={"file": ("import.xlsx", buf.getvalue(),
                                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
            body = r.json()
            check("批量导入 2 名学生", r.status_code == 200 and body.get("created") == 2, r.text[:160])
            for s in ("2024010998", "2024010999"):
                await c.delete("/api/admin/students/" + s, headers=ah)

            print("== 5e. 防护与观测 ==")
            r = await c.get("/api/student/grades", headers=sh)
            check("响应带耗时头", "X-Process-Time-Ms" in r.headers, str(dict(r.headers))[:120])

            blocked = None
            for _ in range(9):
                rr = await c.post("/api/auth/login", json={"role": "student", "username": "ratetest", "password": "x"})
                if rr.status_code == 429:
                    blocked = rr
                    break
            check("登录失败 8 次后被限流", blocked is not None and blocked.status_code == 429,
                  "last=" + str(rr.status_code))

            print("== 6. 静态页面 ==")
            r = await c.get("/")
            check("首页返回单页前端", r.status_code == 200 and "智能教务系统" in r.text)

    print()
    print("汇总：" + str(len(PASS)) + " 项通过，" + str(len(FAIL)) + " 项失败")
    if FAIL:
        print("失败项：" + "；".join(FAIL))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
