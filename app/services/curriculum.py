"""
模块 9 · 培养方案与选修课池（静态教学数据）
--------------------------------------------------------------------
作用：个人培养方案、自主选课、教材明细这些页面需要一份「教学计划」数据。
      真实系统从教务处接口取，这里用可维护的常量模拟，结构与正式数据一致。
"""

from __future__ import annotations

# 8b.1 数据科学与大数据技术专业 · 八学期培养方案
TRAINING_PLAN: list[dict] = [
    {"semester": "第1学期", "courses": [
        ("高等数学A(上)", 5.0), ("大学英语(一)", 3.0), ("程序设计基础", 3.0),
        ("计算机导论", 2.0), ("离散数学", 3.0), ("大学体育(一)", 1.0), ("思想道德与法治", 3.0)]},
    {"semester": "第2学期", "courses": [
        ("高等数学A(下)", 5.0), ("大学英语(二)", 3.0), ("数据结构与算法", 4.0),
        ("面向对象程序设计", 3.0), ("计算机组成原理", 3.0), ("计算机网络", 3.0),
        ("中国近现代史纲要", 3.0)]},
    {"semester": "第3学期", "courses": [
        ("概率论与数理统计", 3.0), ("数据库原理", 3.0), ("操作系统", 4.0),
        ("Python数据分析", 3.0), ("大学物理", 3.0), ("大学体育(二)", 1.0)]},
    {"semester": "第4学期", "courses": [
        ("机器学习导论", 3.0), ("软件工程", 3.0), ("大数据技术基础", 3.0),
        ("Web前端开发", 2.0), ("马克思主义基本原理", 3.0)]},
    {"semester": "第5学期", "courses": [
        ("数据可视化", 2.0), ("分布式系统", 3.0), ("数据仓库与ETL", 3.0),
        ("专业英语", 2.0), ("习近平新时代中国特色社会主义思想概论", 3.0)]},
    {"semester": "第6学期", "courses": [
        ("深度学习", 3.0), ("云计算与容器", 3.0), ("数据安全与隐私", 2.0),
        ("创新创业实践", 2.0)]},
    {"semester": "第7学期", "courses": [
        ("大数据项目实训", 4.0), ("专业实习", 6.0)]},
    {"semester": "第8学期", "courses": [("毕业设计（论文）", 12.0)]},
]

# 8b.2 选修课池：自主选课从这里选
ELECTIVES: list[dict] = [
    {"code": "EL001", "name": "人工智能导论", "credit": 2.0, "teacher": "张伟", "capacity": 60,
     "time": "周三第7-8节", "location": "主楼A203", "desc": "大模型与智能体的基本原理"},
    {"code": "EL002", "name": "Web前端开发实践", "credit": 2.0, "teacher": "陈晨", "capacity": 50,
     "time": "周四第9-10节", "location": "实验楼C302", "desc": "HTML/CSS/JS 到前后端联调"},
    {"code": "EL003", "name": "数据可视化", "credit": 2.0, "teacher": "王芳", "capacity": 45,
     "time": "周二第7-8节", "location": "主楼A102", "desc": "ECharts 与数据叙事"},
    {"code": "EL004", "name": "网络安全基础", "credit": 2.0, "teacher": "陈晨", "capacity": 40,
     "time": "周五第7-8节", "location": "主楼B201", "desc": "常见攻防与安全加固"},
    {"code": "EL005", "name": "创新创业实践", "credit": 1.0, "teacher": "赵敏", "capacity": 80,
     "time": "周五第9-10节", "location": "文科楼108", "desc": "项目路演与商业计划书"},
    {"code": "EL006", "name": "Java程序设计", "credit": 2.0, "teacher": "张伟", "capacity": 50,
     "time": "周三第3-4节", "location": "实验楼C302",
     "desc": "面向对象进阶（与 2401 班计算机组成原理时间冲突，可用于演示）"},
]

# 8b.3 教材（与 7 门课对应，供教材明细/费用/预订使用）
TEXTBOOKS: list[dict] = [
    {"course_code": "CS201", "course_name": "数据结构与算法", "name": "数据结构（C语言版）",
     "isbn": "978-7-302-42496-3", "publisher": "清华大学出版社", "price": 49.0, "status": "已征订"},
    {"course_code": "CS202", "course_name": "面向对象程序设计", "name": "Java核心技术 卷I",
     "isbn": "978-7-111-63154-8", "publisher": "机械工业出版社", "price": 149.0, "status": "已征订"},
    {"course_code": "CS203", "course_name": "计算机组成原理", "name": "计算机组成原理（第2版）",
     "isbn": "978-7-04-048170-5", "publisher": "高等教育出版社", "price": 45.5, "status": "已征订"},
    {"course_code": "CS204", "course_name": "数据库原理", "name": "数据库系统概论（第6版）",
     "isbn": "978-7-04-055520-8", "publisher": "高等教育出版社", "price": 43.0, "status": "已征订"},
    {"course_code": "MA201", "course_name": "高等数学A(下)", "name": "高等数学（下册）",
     "isbn": "978-7-04-039663-4", "publisher": "高等教育出版社", "price": 38.8, "status": "已征订"},
    {"course_code": "CS205", "course_name": "计算机网络", "name": "计算机网络（第8版）",
     "isbn": "978-7-111-62571-4", "publisher": "机械工业出版社", "price": 59.0, "status": "待确认"},
    {"course_code": "SZ201", "course_name": "中国近现代史纲要", "name": "中国近现代史纲要（2023版）",
     "isbn": "978-7-04-059904-2", "publisher": "高等教育出版社", "price": 26.0, "status": "已征订"},
]


# 8b.4 计算培养方案总学分
def total_credits() -> float:
    return round(sum(c for s in TRAINING_PLAN for _, c in s["courses"]), 1)
