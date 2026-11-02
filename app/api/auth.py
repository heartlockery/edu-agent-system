"""
模块 20 · 登录 / 身份 / 菜单 / 账号找回入口
--------------------------------------------------------------------
作用：三种身份共用一个登录接口（student / teacher / admin）；
      同时提供「免登录的账号找回申请」，学生忘记学号或密码时提交班级+姓名即可。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Admin, ClassInfo, RecoveryRequest, Student, Teacher
from app.db.session import get_db
from app.schemas import ChangePasswordIn, LoginIn, LoginOut
from app.security import create_token, get_principal, hash_password, verify_password
from app.services.registry import menu_for

router = APIRouter(prefix="/api/auth", tags=["认证"])

DEFAULT_PASSWORD = "123456"
_MAX_FAILS = 8


async def _load_identity(role: str, username: str, db: AsyncSession):
    """16.1 按角色查账号：三种身份三张表，登录逻辑统一。"""
    if role == "admin":
        row = (await db.execute(select(Admin).where(Admin.ano == username))).scalars().first()
        return row, (row.name if row else "")
    if role == "teacher":
        row = (await db.execute(select(Teacher).where(Teacher.tno == username))).scalars().first()
        return row, (row.name if row else "")
    row = (await db.execute(select(Student).where(Student.sno == username))).scalars().first()
    return row, (row.name if row else "")


@router.post("/login", response_model=LoginOut)
async def login(data: LoginIn, request: Request, db: AsyncSession = Depends(get_db)):
    """16.2 登录：密码错误统一提示；同一 IP+账号 5 分钟内失败 8 次会被锁定。"""
    from app.services.limits import clear_fails, mark_fail, too_many_fails

    role = data.role if data.role in ("student", "teacher", "admin") else "student"
    key = (request.client.host if request.client else "unknown") + ":" + data.username.strip()
    if await too_many_fails(key):
        raise HTTPException(status_code=429, detail="尝试次数过多，请 5 分钟后再试，或提交密码重置申请")

    row, name = await _load_identity(role, data.username.strip(), db)
    if not row:
        await mark_fail(key)
        raise HTTPException(status_code=404, detail="账号不存在，可在登录页提交「找回账号」申请")
    if not verify_password(data.password, row.password_hash or hash_password(DEFAULT_PASSWORD)):
        left = _MAX_FAILS - await mark_fail(key)
        raise HTTPException(status_code=401, detail="密码错误，可提交密码重置申请（今日剩余尝试次数 " + str(max(left, 0)) + "）")
    await clear_fails(key)

    if role == "student":
        klass = (await db.execute(select(ClassInfo).where(ClassInfo.id == row.class_id))).scalar_one_or_none()
        profile = {"sno": row.sno, "name": row.name, "class_name": klass.name if klass else "",
                   "major": row.major, "gender": row.gender}
    elif role == "teacher":
        profile = {"tno": row.tno, "name": row.name, "title": row.title, "dept": row.dept}
    else:
        profile = {"ano": row.ano, "name": row.name, "role_desc": row.role_desc}

    token = create_token(role, row.id, data.username.strip())
    return {"token": token, "role": role, "profile": profile}


@router.get("/me")
async def me(principal: dict = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    """16.3 校验令牌并回显身份。"""
    role = principal["role"]
    row, name = await _load_identity(role, principal["username"], db)
    return {"role": role, "username": principal["username"], "name": name}


@router.post("/change-password")
async def change_password(data: ChangePasswordIn,
                          principal: dict = Depends(get_principal),
                          db: AsyncSession = Depends(get_db)):
    """16.5 修改密码：校验旧密码 -> 写新哈希，三种身份通用。"""
    role = principal["role"]
    row, _name = await _load_identity(role, principal["username"], db)
    if not row:
        raise HTTPException(status_code=404, detail="账号不存在")
    if not verify_password(data.old_password, row.password_hash or hash_password(DEFAULT_PASSWORD)):
        raise HTTPException(status_code=400, detail="旧密码不正确")
    if data.old_password == data.new_password:
        raise HTTPException(status_code=400, detail="新密码不能和旧密码相同")
    row.password_hash = hash_password(data.new_password)
    await db.flush()
    return {"ok": True, "message": "密码已修改，下次请用新密码登录"}


@router.get("/menu")
async def menu(principal: dict = Depends(get_principal)):
    """16.4 按角色下发功能菜单（含开发中状态）。"""
    return {"role": principal["role"], "menus": menu_for(principal["role"])}
