"""
模块 2 · 数据库模型（ORM）
--------------------------------------------------------------------
作用：用一张张表描述教务系统的「人、课、成绩、消息、预约」。
      学生端查询、教师端上传成绩、AI 工具取数，最终都落到这些表上。
说明：表结构同时兼容 SQLite（本地）与 MySQL 8（云服务器），
      没有使用任何方言专属字段，迁移成本为零。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """2.1 声明式基类（SQLAlchemy 2.0 风格）。"""


# ---------------------------------------------------------------
# 2.2 班级 / 学生 / 教师：系统的「人」
# ---------------------------------------------------------------
class ClassInfo(Base):
    __tablename__ = "classes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60), unique=True, index=True)   # 数据科学2401
    grade: Mapped[str] = mapped_column(String(10), default="2024")           # 年级
    major: Mapped[str] = mapped_column(String(60), default="数据科学与大数据技术")
    advisor: Mapped[str] = mapped_column(String(40), default="")             # 辅导员姓名

    students: Mapped[list["Student"]] = relationship(back_populates="klass")


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    sno: Mapped[str] = mapped_column(String(20), unique=True, index=True)    # 学号
    name: Mapped[str] = mapped_column(String(40))
    gender: Mapped[str] = mapped_column(String(4), default="男")
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"), index=True)
    major: Mapped[str] = mapped_column(String(60), default="")
    enroll_year: Mapped[str] = mapped_column(String(10), default="2024")
    phone: Mapped[str] = mapped_column(String(20), default="")
    email: Mapped[str] = mapped_column(String(60), default="")
    password_hash: Mapped[str] = mapped_column(String(160), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    klass: Mapped[ClassInfo] = relationship(back_populates="students")


class Teacher(Base):
    __tablename__ = "teachers"

    id: Mapped[int] = mapped_column(primary_key=True)
    tno: Mapped[str] = mapped_column(String(20), unique=True, index=True)    # 工号
    name: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(30), default="讲师")           # 职称
    dept: Mapped[str] = mapped_column(String(60), default="计算机学院")
    research: Mapped[str] = mapped_column(String(120), default="")           # 研究方向/授课方向
    phone: Mapped[str] = mapped_column(String(20), default="")
    email: Mapped[str] = mapped_column(String(60), default="")
    password_hash: Mapped[str] = mapped_column(String(160), default="")


# ---------------------------------------------------------------
# 2.3 课程 / 课表：一门课可以被多个班在不同时间上
# ---------------------------------------------------------------
class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)   # CS101
    name: Mapped[str] = mapped_column(String(60))
    credit: Mapped[float] = mapped_column(Float, default=3.0)
    hours: Mapped[int] = mapped_column(Integer, default=48)
    category: Mapped[str] = mapped_column(String(20), default="专业必修")     # 通识/专业必修
    teacher_tno: Mapped[str] = mapped_column(String(20), index=True)
    teacher_name: Mapped[str] = mapped_column(String(40), default="")
    semester: Mapped[str] = mapped_column(String(20), default="2024-2025-2")


class TimetableEntry(Base):
    """课表条目：一个班 + 一门课 + 一周某一时段（1-5 天，1-10 节）。"""

    __tablename__ = "timetable"

    id: Mapped[int] = mapped_column(primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"), index=True)
    course_code: Mapped[str] = mapped_column(String(20), index=True)
    course_name: Mapped[str] = mapped_column(String(60), default="")
    teacher_tno: Mapped[str] = mapped_column(String(20), default="")
    teacher_name: Mapped[str] = mapped_column(String(40), default="")
    weekday: Mapped[int] = mapped_column(Integer, default=1)                 # 1=周一
    start_section: Mapped[int] = mapped_column(Integer, default=1)           # 第 1 节
    end_section: Mapped[int] = mapped_column(Integer, default=2)
    location: Mapped[str] = mapped_column(String(40), default="")            # 主楼A101
    weeks: Mapped[str] = mapped_column(String(40), default="1-16周")
    semester: Mapped[str] = mapped_column(String(20), default="2024-2025-2")


# ---------------------------------------------------------------
# 2.4 成绩：教师 Excel 上传后写入这里，学生端/教师端/AI 共用
# ---------------------------------------------------------------
class Grade(Base):
    __tablename__ = "grades"
    __table_args__ = (UniqueConstraint("student_id", "course_code", "semester", name="uq_grade"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    course_code: Mapped[str] = mapped_column(String(20))
    course_name: Mapped[str] = mapped_column(String(60))
    credit: Mapped[float] = mapped_column(Float, default=3.0)
    score: Mapped[float] = mapped_column(Float, default=0.0)                 # 百分制
    semester: Mapped[str] = mapped_column(String(20), default="2024-2025-1")
    exam_type: Mapped[str] = mapped_column(String(20), default="期末考试")
    source: Mapped[str] = mapped_column(String(20), default="系统导入")       # 教师上传/系统导入


# ---------------------------------------------------------------
# 2.5 通知 / 消息：教师发送，学生接收
# ---------------------------------------------------------------
class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    content: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(20), default="教务通知")     # 教务/考试/课程
    sender_tno: Mapped[str] = mapped_column(String(20), default="")
    sender_name: Mapped[str] = mapped_column(String(40), default="教务处")
    target_class_id: Mapped[int | None] = mapped_column(ForeignKey("classes.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Message(Base):
    """点对点消息（教师 -> 学生），学生端「消息列表」读的就是这张表。"""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    sender_role: Mapped[str] = mapped_column(String(10), default="teacher")
    sender_id: Mapped[str] = mapped_column(String(20), default="")
    sender_name: Mapped[str] = mapped_column(String(40), default="")
    receiver_role: Mapped[str] = mapped_column(String(10), default="student")
    receiver_id: Mapped[str] = mapped_column(String(20), index=True)          # 学号
    title: Mapped[str] = mapped_column(String(120), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)


# ---------------------------------------------------------------
# 2.6 考试预约 / 选课 / 调课申请 / 会议
# ---------------------------------------------------------------
class ExamAppointment(Base):
    __tablename__ = "exam_appointments"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    course_code: Mapped[str] = mapped_column(String(20))
    course_name: Mapped[str] = mapped_column(String(60), default="")
    exam_date: Mapped[str] = mapped_column(String(20), default="")            # 2025-01-08
    session: Mapped[str] = mapped_column(String(20), default="上午")
    room: Mapped[str] = mapped_column(String(40), default="")
    status: Mapped[str] = mapped_column(String(20), default="已预约")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Enrollment(Base):
    __tablename__ = "enrollments"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    course_code: Mapped[str] = mapped_column(String(20))
    course_name: Mapped[str] = mapped_column(String(60), default="")
    credit: Mapped[float] = mapped_column(Float, default=3.0)
    semester: Mapped[str] = mapped_column(String(20), default="2024-2025-2")
    status: Mapped[str] = mapped_column(String(20), default="已选课")
    selected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class ScheduleChangeRequest(Base):
    """调课申请：单独调课 或 教师互换调课（教师端核心业务之一）。"""

    __tablename__ = "schedule_changes"

    id: Mapped[int] = mapped_column(primary_key=True)
    teacher_tno: Mapped[str] = mapped_column(String(20), index=True)
    teacher_name: Mapped[str] = mapped_column(String(40), default="")
    change_type: Mapped[str] = mapped_column(String(20), default="单独调课")
    course_name: Mapped[str] = mapped_column(String(60), default="")
    from_slot: Mapped[str] = mapped_column(String(60), default="")            # 周一第1-2节 主楼A101
    to_slot: Mapped[str] = mapped_column(String(60), default="")              # 周三第3-4节
    target_tno: Mapped[str] = mapped_column(String(20), default="")           # 互换对象工号
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="待审批")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Meeting(Base):
    """教师会议安排，AI 可以回答「我下周三什么时候开会」。"""

    __tablename__ = "meetings"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    teacher_tno: Mapped[str] = mapped_column(String(20), index=True)
    start_time: Mapped[str] = mapped_column(String(30), default="")           # 2025-03-12 14:30
    location: Mapped[str] = mapped_column(String(40), default="")
    content: Mapped[str] = mapped_column(Text, default="")


# ---------------------------------------------------------------
# 2.7 管理员：负责学生/教师账号的增删改查、密码重置、找回审批
#     管理员系统不接入大模型，只有后台管理能力
# ---------------------------------------------------------------
class Admin(Base):
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(primary_key=True)
    ano: Mapped[str] = mapped_column(String(30), unique=True, index=True)     # 管理员账号
    name: Mapped[str] = mapped_column(String(40), default="系统管理员")
    role_desc: Mapped[str] = mapped_column(String(40), default="教务管理员")
    password_hash: Mapped[str] = mapped_column(String(160), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Application(Base):
    """通用报名申请：补考确认、学分认定、创新创业、转专业、教材预订等共用一张表。"""

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    app_type: Mapped[str] = mapped_column(String(30))            # 补考确认 / 学分认定 / 教材预订
    title: Mapped[str] = mapped_column(String(120), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="已提交")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Proctor(Base):
    """监考安排：教师端可查、可新增。"""

    __tablename__ = "proctors"

    id: Mapped[int] = mapped_column(primary_key=True)
    teacher_tno: Mapped[str] = mapped_column(String(20), index=True)
    teacher_name: Mapped[str] = mapped_column(String(40), default="")
    course_name: Mapped[str] = mapped_column(String(60), default="")
    exam_date: Mapped[str] = mapped_column(String(20), default="")
    session: Mapped[str] = mapped_column(String(30), default="上午")
    room: Mapped[str] = mapped_column(String(40), default="")
    duty: Mapped[str] = mapped_column(String(40), default="主监考")


class Textbook(Base):
    """教材：教师端可查、可征订；学生端可查明细、费用与预订。"""

    __tablename__ = "textbooks"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_code: Mapped[str] = mapped_column(String(20), index=True)
    course_name: Mapped[str] = mapped_column(String(60), default="")
    name: Mapped[str] = mapped_column(String(120), default="")
    isbn: Mapped[str] = mapped_column(String(40), default="")
    publisher: Mapped[str] = mapped_column(String(60), default="")
    price: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="已征订")     # 已征订/待确认
    order_count: Mapped[int] = mapped_column(Integer, default=0)


class RecoveryRequest(Base):
    """账号找回 / 密码重置申请：学生无需登录即可提交「班级 + 姓名」。

    流程：学生提交 -> 管理员在后台看到 -> 管理员审核通过（系统重置为默认密码）
          -> 学生用学号 + 默认密码登录并自行修改。
    """

    __tablename__ = "recovery_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    role: Mapped[str] = mapped_column(String(10), default="student")          # student / teacher
    name: Mapped[str] = mapped_column(String(40))
    class_name: Mapped[str] = mapped_column(String(60), default="")
    sno: Mapped[str] = mapped_column(String(20), default="")                 # 审核通过后自动回填
    request_type: Mapped[str] = mapped_column(String(20), default="找回账号")
    contact: Mapped[str] = mapped_column(String(60), default="")             # 手机/邮箱，便于核实
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="待处理")         # 待处理/已处理/已驳回
    admin_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    handled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
