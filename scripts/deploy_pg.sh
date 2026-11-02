#!/usr/bin/env bash
# =====================================================================
# 智能教务系统 · 云服务器一键部署脚本（Ubuntu / Debian + PostgreSQL）
# 用法（在服务器项目根目录执行）：
#     chmod +x scripts/deploy_pg.sh
#     sudo bash scripts/deploy_pg.sh '你的数据库密码'
# 作用：装 PostgreSQL -> 建库建用户 -> 装 Python 依赖 -> 生成 .env
#       -> 建表灌数据 -> 注册 systemd 常驻服务 -> 启动并打印访问地址
# =====================================================================
set -euo pipefail

DB_NAME="${DB_NAME:-edu_system}"
DB_USER="${DB_USER:-edu_user}"
DB_PASS="${1:-}"
PORT="${PORT:-8000}"
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [ -z "$DB_PASS" ]; then
  echo "请把数据库密码作为第一个参数传进来：sudo bash scripts/deploy_pg.sh '你的密码'"
  exit 1
fi

echo "==> 1/6 安装系统依赖"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y postgresql postgresql-contrib python3-venv python3-pip curl

echo "==> 2/6 建库建用户（已存在则跳过）"
systemctl enable --now postgresql
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1 || \
  sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';"
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1 || \
  sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER ENCODING 'UTF8';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"

echo "==> 3/6 创建虚拟环境并安装依赖"
cd "$APP_DIR"
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
pip install asyncpg -i https://pypi.tuna.tsinghua.edu.cn/simple

echo "==> 4/6 生成 .env（已存在则备份）"
if [ -f .env ]; then
  cp .env ".env.bak.$(date +%s)"
  echo "    检测到已有 .env，已备份"
fi
SECRET="$(head -c 32 /dev/urandom | base64 | tr -d '=+/' | cut -c1-40)"
cat > .env <<ENVEOF
DEBUG=false
SECRET_KEY=$SECRET
TOKEN_EXPIRE_MINUTES=720
DATABASE_URL=postgresql+asyncpg://$DB_USER:$DB_PASS@127.0.0.1:5432/$DB_NAME
STUDENT_LLM_MODEL=deepseek-chat
STUDENT_LLM_API_KEY=
STUDENT_LLM_BASE_URL=https://api.deepseek.com/v1
STUDENT_LLM_TEMPERATURE=0.3
TEACHER_LLM_MODEL=deepseek-chat
TEACHER_LLM_API_KEY=
TEACHER_LLM_BASE_URL=https://api.deepseek.com/v1
TEACHER_LLM_TEMPERATURE=0.2
LANGCHAIN_TRACING_V2=false
LANGCHAIN_API_KEY=
LANGCHAIN_PROJECT=edu-agent-system
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
EMBEDDING_MODEL=text-embedding-3-small
RAG_TOP_K=4
RAG_CHUNK_SIZE=420
ENVEOF
chmod 600 .env

echo "==> 5/6 建表 + 灌种子数据（180 学生 / 5 教师 / 7 课程）"
python scripts/init_db.py

echo "==> 6/6 注册 systemd 常驻服务"
cat > /etc/systemd/system/edu.service <<SVCEOF
[Unit]
Description=Smart Edu System (LangGraph Agent)
After=network.target postgresql.service

[Service]
User=root
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port $PORT
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
SVCEOF
systemctl daemon-reload
systemctl enable --now edu
sleep 2
systemctl is-active --quiet edu && echo "    服务已启动" || (journalctl -u edu -n 30 --no-pager; exit 1)

IP="$(curl -s --max-time 3 https://api.ipify.org || echo 你的公网IP)"
echo ""
echo "================ 部署完成 ================"
echo "  访问地址 : http://$IP:$PORT"
echo "  管理员   : 10214823205 / 123456"
echo "  学生     : 2024010101 / 123456"
echo "  教师     : T1001 / 123456"
echo "  日志     : journalctl -u edu -f"
echo "  重启     : systemctl restart edu"
echo "  注意     : 安全组需放行 TCP $PORT"
echo "=========================================="
