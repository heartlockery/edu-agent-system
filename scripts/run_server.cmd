@echo off
rem 后端常驻启动器：供计划任务调用，日志追加到 logs\uvicorn.log
cd /d D:\desktop\edu-agent-system
if not exist logs mkdir logs
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 >> logs\uvicorn.log 2>&1
