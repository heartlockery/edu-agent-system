@echo off
rem 内网穿透常驻启动器：供计划任务调用，日志追加到 logs\cloudflared.log
cd /d D:\desktop\edu-agent-system
if not exist logs mkdir logs
tools\cloudflared.exe tunnel --url http://127.0.0.1:8000 --no-autoupdate >> logs\cloudflared.log 2>&1
