#!/usr/bin/env bash
# 服务加固：并发上限、keep-alive、代理头；可重复执行（幂等）
set -euo pipefail
UNIT=/etc/systemd/system/edu.service
[ -f "$UNIT.bak" ] || cp "$UNIT" "$UNIT.bak"

NEW="ExecStart=/opt/edu-agent-system/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --timeout-keep-alive 30 --limit-concurrency 120"
sed -i "s|^ExecStart=.*|$NEW|" "$UNIT"

systemctl daemon-reload
systemctl restart edu
sleep 6
systemctl is-active edu
systemctl show edu -p ExecStart --no-pager | head -2
curl -s -m 8 http://127.0.0.1:8000/api/health
echo
journalctl -u edu -n 6 --no-pager | tail -4
