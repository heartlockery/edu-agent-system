# 部署到云服务器（MobaXterm 上传 + PostgreSQL / MySQL）

> 你这台机器：ins-102ccwv4（南京三区，2 核 4G，内网 10.206.0.14）。
> **当前没有公网 IPv4（主IPv4 地址是 -）**，所以 MobaXterm 现在连不上，我也连不上。
> 先去云控制台绑定一个弹性公网 IP（EIP），再放行安全组，才谈得上上传。

## 一、先解决「能不能连上」

1. 控制台 → 弹性公网 IP（EIP）→ 绑定到 ins-102ccwv4。
2. 安全组入方向放行：22（SSH/MobaXterm）、8000（系统网页演示），
   5432/3306 只在需要从本机连数据库时开，并限制来源 IP。
3. 拿到公网 IP 后，MobaXterm 新建 SSH 会话：Remote host = 公网 IP，用户名 root（或你的用户），密码或密钥登录。

## 一之二、懒人路线：一条脚本全搞定

EIP 绑定 + 安全组放行之后，在服务器项目根目录执行：

§§§bash
chmod +x scripts/deploy_pg.sh
sudo bash scripts/deploy_pg.sh '你的数据库密码'
§§§

脚本会自动完成：装 PostgreSQL → 建库建用户 → venv + 依赖 → 生成 .env（含随机 SECRET_KEY）
→ 建表灌数据 → 注册 systemd 常驻 → 启动并打印访问地址。

## 二、MobaXterm 上传代码（可以，最省事）

**方式 A：SFTP 面板拖拽** —— 连接成功后左侧就是 SFTP 浏览器，把本地 `edu-agent-system` 文件夹拖到 `/opt/` 下。

**方式 B：本地打包 + scp**（Windows PowerShell 执行，IP 换成你的）：

```powershell
cd D:\desktop
tar -czf edu-agent-system.tar.gz edu-agent-system
scp edu-agent-system.tar.gz root@公网IP:/opt/
```

服务器上解压：

```bash
cd /opt && tar -xzf edu-agent-system.tar.gz && cd edu-agent-system
```

> 上传时不要带 `.venv/`、`__pycache__/`、`data/edu.db`（`.gitignore` 已排除）。
> 种子数据（`data/*.json` 和两个 Excel）必须一起传，否则服务器上没数据。

## 三、PostgreSQL 可以吗？可以

代码是 SQLAlchemy 2.0 异步 ORM，只用标准字段类型，**MySQL / PostgreSQL / SQLite 都能跑**，只需换驱动和连接串。

### 1. 装 PostgreSQL（Ubuntu / Debian）

```bash
sudo apt update
sudo apt install -y postgresql postgresql-contrib python3-venv python3-pip
sudo systemctl enable --now postgresql
```

### 2. 建库建用户

```bash
sudo -u postgres psql
```

在 psql 里执行（密码换成你自己的强密码）：

```sql
CREATE USER edu_user WITH PASSWORD '换成你的强密码';
CREATE DATABASE edu_system OWNER edu_user ENCODING 'UTF8';
GRANT ALL PRIVILEGES ON DATABASE edu_system TO edu_user;
\q
```

### 3. 装依赖

```bash
cd /opt/edu-agent-system
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
pip install asyncpg
```

### 4. 改 .env

```ini
DATABASE_URL=postgresql+asyncpg://edu_user:你的密码@127.0.0.1:5432/edu_system
SECRET_KEY=换成随机字符串
DEBUG=false
STUDENT_LLM_API_KEY=
TEACHER_LLM_API_KEY=
LANGCHAIN_TRACING_V2=false
```

> 用 MySQL 的话把连接串换成：
> `DATABASE_URL=mysql+aiomysql://edu_user:密码@127.0.0.1:3306/edu_system?charset=utf8mb4`
> 并把依赖换成 `pip install aiomysql pymysql`。

### 5. 建表 + 灌数据

```bash
python scripts/init_db.py
```

看到「种子数据导入完成」即可：13 张表、180 名学生、5 位教师、7 门课程、课表、成绩、通知、会议。

### 6. 启动

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

浏览器访问 `http://公网IP:8000`，管理员账号 `10214823205 / 123456`。

后台常驻（systemd）：

```bash
sudo tee /etc/systemd/system/edu.service > /dev/null <<'EOF'
[Unit]
Description=Smart Edu System
After=network.target postgresql.service

[Service]
User=root
WorkingDirectory=/opt/edu-agent-system
EnvironmentFile=/opt/edu-agent-system/.env
ExecStart=/opt/edu-agent-system/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now edu
sudo systemctl status edu --no-pager
```

## 四、常见的坑

| 现象 | 原因 / 解决 |
| --- | --- |
| MobaXterm 连不上、一直超时 | 没绑 EIP，或安全组没放行 22 |
| pip 很慢/卡住 | 加国内源 `-i https://pypi.tuna.tsinghua.edu.cn/simple` |
| `ModuleNotFoundError: asyncpg` | 忘了装 PostgreSQL 驱动 |
| `password authentication failed` | 密码含特殊字符需 URL 编码（`@` 写成 `%40`） |
| 网页打不开 | 安全组没放 8000，或没监听 `0.0.0.0` |
| 中文乱码 | 数据库编码必须 `UTF8`（PG）/ `utf8mb4`（MySQL） |
| `asyncpg` 编译失败 | `apt install -y python3-dev build-essential` |
| 想重来一遍 | `python scripts/init_db.py --reset`（会删表重建） |

## 五、需要你告诉我的信息

1. 绑定后的**公网 IP**
2. SSH 端口（默认 22）与用户名
3. 数据库选 **PostgreSQL 还是 MySQL**
4. 数据库名 / 用户名（密码你自己写进 `.env`，不必贴在聊天里）
5. 是否要部署成 systemd 常驻服务

拿到 1、2、3 之后，我可以给你逐条命令，或直接写好一键部署脚本让你粘贴执行。
