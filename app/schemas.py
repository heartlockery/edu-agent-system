"""
模块 5 · 请求/响应数据模型
--------------------------------------------------------------------
作用：约束前端与后端之间的数据格式，FastAPI 自动做校验并生成 /docs 文档。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# 5.1 登录
class LoginIn(BaseModel):
    role: str = Field(default="student", description="student 或 teacher")
    username: str = Field(description="学号或工号")
    password: str = Field(default="123456", description="默认密码 123456")


class LoginOut(BaseModel):
    token: str
    role: str
    profile: dict[str, Any]


# 5.2 AI 对话
class ChatIn(BaseModel):
    message: str = Field(description="学生/老师对 AI 说的一句话")
    session_id: str = Field(default="default", description="会话 ID，用于多轮上下文记忆")


class ChatOut(BaseModel):
    answer: str
    tool_calls: list[dict[str, Any]] = []
    ui_actions: list[dict[str, Any]] = []
    model: str = ""
    trace: list[str] = []


# 5.3 教师：发通知 / 发消息 / 调课
class NotificationIn(BaseModel):
    title: str
    content: str = ""
    category: str = "教务通知"
    class_name: str | None = Field(default=None, description="不填表示全体学生")


class MessageIn(BaseModel):
    sno: str
    title: str = ""
    content: str


class ScheduleChangeIn(BaseModel):
    change_type: str = Field(default="单独调课", description="单独调课 / 教师互换调课")
    course_name: str
    from_slot: str
    to_slot: str = ""
    target_tno: str = ""
    reason: str = ""


# 5.4 学生：考试预约 / 个人信息维护
class ExamReserveIn(BaseModel):
    course_code: str
    exam_date: str = ""
    session: str = "上午"


class ProfileUpdateIn(BaseModel):
    phone: str | None = None
    email: str | None = None


class ChangePasswordIn(BaseModel):
    """登录后修改密码（三种身份通用）。"""

    old_password: str
    new_password: str = Field(min_length=6, description="新密码至少 6 位")
