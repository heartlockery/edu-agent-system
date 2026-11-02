"""
模块 33 · 增量部署小工具（本地执行，凭据走环境变量）
--------------------------------------------------------------------
用法（PowerShell）：
    $env:EDU_HOST="1.2.3.4"; $env:EDU_USER="root"; $env:EDU_PASS="***"
    python scripts/deploy_remote.py app/main.py static/index.html ...
作用：把指定文件通过 SFTP 覆盖到 /opt/edu-agent-system/，重启服务并打印健康检查。
说明：凭据只从环境变量读取，不落盘，适合日常改一行就发一次的小步部署。
"""

from __future__ import annotations

import os
import sys
import time

import paramiko

HOST = os.environ.get("EDU_HOST", "")
USER = os.environ.get("EDU_USER", "root")
PASS = os.environ.get("EDU_PASS", "")
REMOTE = os.environ.get("EDU_DIR", "/opt/edu-agent-system/")
LOCAL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    if not (HOST and PASS):
        print("缺少 EDU_HOST / EDU_PASS 环境变量")
        return 2
    args = sys.argv[1:]
    extra_cmd = ""
    if "--cmd" in args:
        idx = args.index("--cmd")
        extra_cmd = args[idx + 1]
        args = args[:idx] + args[idx + 2:]
    files = args
    if not files and not extra_cmd:
        print("请至少指定一个要上传的相对路径")
        return 2

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, 22, USER, PASS, timeout=15)
    sftp = client.open_sftp()
    for rel in files:
        sftp.put(os.path.join(LOCAL, rel.replace("/", os.sep)), REMOTE + rel)
        print("上传:", rel)
    sftp.close()

    cmd = ("systemctl restart edu; sleep 6; systemctl is-active edu; "
           "curl -s -m 10 http://127.0.0.1:8000/api/health; echo")
    _in, out, err = client.exec_command(cmd, timeout=120)
    print(out.read().decode("utf-8", "replace").strip())
    if extra_cmd:
        _i2, o2, e2 = client.exec_command(extra_cmd, timeout=120)
        print(o2.read().decode("utf-8", "replace").strip()[-3000:])
        _e2 = e2.read().decode("utf-8", "replace").strip()
        if _e2:
            print("[stderr]", _e2[-500:])
    _e = err.read().decode("utf-8", "replace").strip()
    if _e and "Warning" not in _e:
        print("[stderr]", _e[-400:])
    client.close()
    print("完成时间:", time.strftime("%H:%M:%S"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
