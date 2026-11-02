# 智能教务系统（LangChain + LangGraph + LangSmith + RAG + 双大模型 Agent）

一个可以在 VS Code 里直接跑起来的教务系统 Demo：
学生、教师、管理员三种身份，**一句话直达功能**（查成绩、查课表、预约考试、发通知、导出 Excel、调课申请），
底层用 LangGraph 编排 Agent、用两套大模型分别服务学生和老师、用 RAG 回答教务规章问题、用 LangSmith 记录链路。

> 没有配置任何大模型 Key 也能完整运行：系统会自动进入「离线规则模式」，功能一模一样，只是由规则引擎代替大模型做意图识别。

---

## 一、5 分钟跑起来（VS Code）

1. 用 VS Code 打开本文件夹。
2. 新建终端，创建虚拟环境并安装依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

3. 复制环境变量模板（不填 Key 也能跑）：

```powershell
copy .env.example .env
```

4. 生成模拟数据（已生成过可跳过，脚本幂等）：

```powershell
python scripts/gen_data.py
```

5. 启动服务：

```powershell
uvicorn app.main:app --reload --port 8000
```

6. 浏览器打开 <http://127.0.0.1:8000> ，接口文档在 <http://127.0.0.1:8000/docs> 。
   首次启动会自动建表并灌入 180 名学生、5 位教师、7 门课程、课表、成绩、通知、会议等种子数据。

### 默认账号（初始密码都是 123456）

| 身份 | 账号 | 密码 | 说明 |
| --- | --- | --- | --- |
| 学生 | 2024010101~2024010160（2401 班）<br>2024010201~2024010260（2402 班）<br>2024010301~2024010360（2403 班） | 123456 | 共 3 个班 180 人 |
| 教师 | T1001 张伟 / T1002 李强 / T1003 王芳 / T1004 陈晨 / T1005 赵敏 | 123456 | 前 4 位计算机学院，赵敏为思政教师 |
| 管理员 | 10214823205 | 123456 | 只做账号管理，**不接入 AI** |

---

## 二、功能清单（已实现 / 开发中）

### 学生端

| 分类 | 已实现 | 开发中（点击提示「系统正在开发中」） |
| --- | --- | --- |
| 信息查询 | 通知公告、个人课表、班级课表、成绩查询、考试信息、消息列表、个人信息、空闲教室、选课情况确认 | 选课名单、教材明细/费用、学业预警、证书打印、学业情况、教学执行计划 |
| 报名申请 | **补考确认**、**成绩学分认定**、**大学英语学分认定**、**创新创业报名**、**学籍异动**、**重修报名**、**转专业申请**、**教学项目报名**（在线提交 + 进度查询） | 毕业补考、结业换证、资格证书、退书、课程/学分节点替代、学士学位 |
| 信息维护 | 个人信息维护、**个人培养方案**、**创新创业学分确认**、**自主报到注册** | — |
| 选课 | 个人课表、选课情况确认、**自主选课**、**教材预订/明细/费用** | — |
| 考试 | **考试预约**（网页和 AI 都能约） | — |

### 教师端

| 分类 | 已实现 | 开发中 |
| --- | --- | --- |
| 学生管理 | 发通知（全体/指定班级，同时写站内消息）、给单个学生发消息 | — |
| 成绩管理 | 查询学生成绩、**上传桌面 Excel 成绩表**、**导出成绩文件**、班级成绩分析 | 成绩录入修改 |
| 教学安排 | 我的课表、会议安排、**调课申请**、**监考安排（查/新增）**、**教材管理（征订/改状态）**、**调课审批（通过即同步课表并通知申请人）** | — |

### 管理员端（无 AI）

学生账号管理（查询/新增/重置密码/删除）、教师账号管理、**找回申请处理**（按姓名+班级定位账号，一键重置为 123456）、数据总览。

学生忘记账号或密码时，在登录页点「忘记学号 / 密码」填写 **班级 + 姓名** 提交申请，管理员在后台「通过并重置」即可。

### AI 一句话直达（核心亮点）

| 你说 | Agent 做的事 |
| --- | --- |
| 我上学期高数考了多少分 | 调用 query_grades(course_name=高等数学A(上))，返回单科分、平均分、绩点 |
| 这周三我有什么课 | 调用 query_timetable(weekday=3)，并自动跳到课表页 |
| 帮我预约大学英语的考试 | 调用 reserve_exam，写库并返回考场时间 |
| 转专业需要什么条件 | RAG 检索知识库后作答（不编造政策） |
| 推荐几个学 Python 的网站 | 调用 web_search 联网检索（只查学习资料；游戏类请求会被温柔拦下） |
| 我的高数老师是谁 | 调 query_course_teacher 查任课老师 |
| 我这个月有什么安排 | 调 query_calendar，首页日历也会同步高亮 |
| 我哪几门要补考 | 调 query_makeup，可直接在页面一键确认补考 |
| 我最近有点跟不上，给点建议 | 结合本人最低分课程 + RAG 规章给学习建议 |
| （教师）把 2401 班成绩导成 Excel 发我 | 生成文件并返回**绝对路径 + 下载链接**，前端自动下载 |
| （教师）给 2401 班发通知：明天停课 | 写通知表 + 给 60 名学生各写一条站内消息 |
| （教师）我下周三什么时候开会 | 查会议表，返回时间地点 |

---

## 三、技术架构

```
浏览器（static/index.html 单页）
    │  JWT 风格令牌（HMAC-SHA256）
    ▼
FastAPI（app/api/*）───────────────┐
    │  登录态上下文                 │  账号管理（管理员）
    ▼                              ▼
LangGraph Agent（app/ai/graph.py）  SQLAlchemy 2.0 异步 ORM
  intake → planner → executor → responder
    │            │                │
    │            │                └── 双大模型（学生/教师各一套配置）
    │            └── 工具集（查询/操作/导出）
    └── RAG 知识库（knowledge/*.md → 向量/TF-IDF 检索）
    │
    └── LangSmith 链路追踪（可选）
```

- **双大模型**：`STUDENT_LLM_*` 与 `TEACHER_LLM_*` 两组配置，可分别指向不同模型/Key，人格与权限边界也不同。
- **LangGraph**：状态图编排 + MemorySaver 多轮记忆，`thread_id = 角色:账号:会话ID`。
- **工具调用协议**：让模型输出 JSON（`{"tool_calls":[...]}`）而非依赖各家不同的 Function Calling，兼容性更好。
- **RAG**：有 Key 走向量检索，无 Key 走「字符 n-gram + TF-IDF 余弦」，两种模式接口一致。
- **降级策略**：大模型超时/报错/未配置 → 自动切规则引擎，保证演示不中断。

---

## 四、模拟数据说明

| 文件 | 内容 |
| --- | --- |
| data/students.json | 3 个班 × 60 人 = 180 名学生 |
| data/teachers.json | 5 位教师（张伟、李强各带 2 门课；赵敏为思政教师） |
| data/courses.json | 本学期 7 门课 |
| data/timetable.json | 3 份课表（班与班之间时段/教室小幅错开） |
| **data/成绩_2024-2025-1_上学期.xlsx** | 上学期 7 门课成绩 + 总分 / 平均分 / 总学分 / 平均绩点（180 行） |
| **data/课表_数据科学2401-2403.xlsx** | 3 个 sheet，每班一张「星期 × 节次」课表 |

课表可直接用 Excel 打开核对；成绩表格式即「教师上传模板」格式，可在教师端直接上传回系统。

---

## 五、目录结构与每个文件的作用

```
edu-agent-system/
├─ app/
│  ├─ config.py              配置总控（数据库/双模型/LangSmith/RAG/目录）
│  ├─ security.py            密码哈希 + 令牌 + 角色鉴权依赖
│  ├─ schemas.py             Pydantic 请求响应模型
│  ├─ main.py                应用入口：路由注册、静态资源、启动建表与灌数据
│  ├─ db/
│  │  ├─ models.py           13 张表的 ORM 定义
│  │  ├─ session.py          异步引擎与会话工厂（SQLite/MySQL 自动切换）
│  │  └─ seed.py             首次启动灌入种子数据
│  ├─ api/
│  │  ├─ auth.py             登录、身份校验、菜单、账号找回申请
│  │  ├─ student.py          学生端 12 个接口
│  │  ├─ teacher.py          教师端 13 个接口（含 Excel 上传/导出）
│  │  ├─ admin.py            管理员端账号与找回申请管理（无 AI）
│  │  └─ chat.py             AI 对话入口 + 自检接口
│  ├─ services/
│  │  ├─ registry.py         40+ 功能菜单注册表（ready / developing）
│  │  ├─ grades.py           成绩 Excel 解析、导出、绩点换算、统计
│  │  └─ exam_plan.py        考试计划静态数据
│  └─ ai/
│     ├─ llm.py              双大模型接入 + 规划/作答封装
│     ├─ mock_llm.py         离线规则引擎（无 Key 时的意图识别与作答）
│     ├─ prompts.py          学生/教师人格、规划器、润色、学习建议提示词
│     ├─ rag.py              RAG 知识库（在线向量 / 离线 TF-IDF）
│     ├─ tools_student.py    学生端 12 个工具
│     ├─ tools_teacher.py    教师端 10 个工具
│     └─ graph.py            LangGraph 状态图与 LangSmith 追踪
├─ knowledge/                教务规章 Markdown（RAG 语料，4 篇）
├─ scripts/gen_data.py       模拟数据生成器
├─ static/index.html         内置单页前端（登录 + 三端界面 + AI 对话）
├─ data/                     生成的 JSON / Excel / SQLite 库
├─ scripts/smoke_test.py     端到端验收脚本（60 项检查）
├─ scripts/load_test.py      轻量并发压测
├─ DEPLOY.md                 云服务器部署手册（MobaXterm + PostgreSQL/MySQL）
├─ requirements.txt          依赖清单
├─ LIBRARIES.md              **用到的插件与库说明（单独文件）**
└─ .env.example              环境变量模板
```

---

## 四之二、语气与内容边界

- 学生端助手是「温柔学姐」口吻：先给结论再讲细节，考差了先安慰再给建议；教师端是「贴心教学秘书」口吻，写操作前先说明影响范围。
- 登录后 AI 会**主动打招呼**：带时间段问候、今天的课、未读消息数；教师端带最近会议与待审批数量。
- **内容边界**：命中「游戏 / 代打 / 代刷 / 作弊」等关键词会被温柔拒绝，并把话题引回学习，不进入大模型；联网搜索同样会过滤。
- 双模型分别配置：§STUDENT_LLM_API_KEY§ 服务学生，§TEACHER_LLM_API_KEY§ 服务老师，互不影响。

## 五之二、自检与验收

§§§powershell
python scripts/smoke_test.py
§§§

一条命令跑完 39 项端到端检查（用 httpx 直接打 ASGI 应用，不占用端口、不影响正式库）：
三种身份登录、学生成绩/课表、AI 查成绩/查课表/问规章/预约考试、教师查成绩/导出 Excel/发通知、
管理员统计与找回审批、管理员禁用 AI、首页可访问。**当前结果：24 项全部通过。**

---

## 六、部署到云服务器（需要你提供这些信息）

代码本身已经支持「本地 SQLite ↔ 线上 MySQL」一键切换，只需要在 `.env` 里改 `DATABASE_URL`。
如果要我帮你把数据库真正接到云服务器上，请把这些信息发给我（敏感内容请私聊/环境变量，别写进代码）：

1. **服务器地址**：公网 IP 或域名
2. **端口**：MySQL 一般是 3306
3. **数据库名**：例如 edu_system
4. **用户名 / 密码**：建议单独建一个只对本库有权限的账号
5. **是否开启 SSL**：云数据库（如阿里云 RDS、腾讯云 CDB）通常需要
6. **服务器系统**：Windows Server 还是 Linux（决定部署方式）
7. 是否需要我把应用也一起部署（uvicorn + Nginx + systemd/PM2）

拿到信息后我会：建表脚本 → 导入 180 名学生与成绩 → 切换 `DATABASE_URL` → 跑一次冒烟测试。
其他可选项：`.env` 里的 `STUDENT_LLM_API_KEY`、`TEACHER_LLM_API_KEY`（DeepSeek/通义/OpenAI 均可）、`LANGCHAIN_API_KEY`（LangSmith）。

建议的安全设置：`.env` 加入 `.gitignore`（已配置）、管理员密码首次登录后修改、生产环境把 `DEBUG=false`、给 `/docs` 加访问限制。

---

## 六之二、运维与本次优化记录

### 已落到线上的基础服务能力

| 能力 | 说明 | 位置 |
| --- | --- | --- |
| GZip 压缩 | 首页从 45KB 压到 13.7KB，1Mbps 带宽下明显更快 | §app/main.py§ |
| 静态缓存策略 | §/static§ 缓存 1 小时，首页 §no-cache§，发版刷新即生效 | §app/main.py§ |
| 慢请求观测 | 超过 2s 的接口记录到 §/api/health§ 的 §slow_requests§ | §app/main.py§ + §app/services/limits.py§ |
| 登录防爆破 | 同一 IP+账号 5 分钟内失败 8 次锁定 | §app/services/limits.py§ |
| 统一异常兜底 | 未捕获异常返回 JSON，不再吐 HTML 栈 | §app/main.py§ |
| 健康检查 | 应用 + 数据库 + 运行时长 + 慢请求 | §/api/health§ |
| 修改密码 | 学生/教师/管理员通用，校验旧密码 | §/api/auth/change-password§ |
| 每日数据库备份 | 每天 03:15 §pg_dump§，保留 7 份 | §scripts/backup_db.sh§ + §edu-backup.timer§ |
| 服务加固 | uvicorn 限并发 120、keep-alive 30s、代理头 | §scripts/harden.sh§ |
| 增量部署 | 改一个文件也能一键上传+重启+自检 | §scripts/deploy_remote.py§ |
| 全接口巡检 | 31 个接口状态码一览 | §scripts/sweep_health.sh§ |

### 本次修复的真实 bug

1. **教师收件箱 500**：§await db.execute(...).order_by()§ 括号位置错，导致对 coroutine 调 §order_by§。
2. **启动被卡 2 分钟**：RAG 用 DeepSeek 的 Key 去调不存在的 §/embeddings§，超时后才 fallback → 改为默认离线向量 + 后台预热。
3. **上传/发通知/发消息 405**：POST 接口被前端当 GET 调用 → 改为表单页。
4. **导出成绩报 §avg_score undefined§**：把下载当 JSON 解析 → 改为带鉴权的 blob 下载。
5. 模型提示词里 §deepseek-chatfalse§ 的运算符优先级错误。
6. 300+ 处被模板字符串破坏的 §\n§ 转义。

## 六之三、本次迭代记录（19:09–19:24）

| 时间 | 内容 |
| --- | --- |
| 第 1 轮 | 修教师收件箱 500（`order_by` 括号错位）；GZip（首页 45KB→13.7KB）、静态缓存、慢请求观测、登录防爆破、全局异常兜底、健康检查、修改密码、每日备份、uvicorn 加固 |
| 第 2 轮 | 管理员批量导入学生账号（Excel，含跳过/错误提示）；教材预订加选课校验；修 404 兜底掩盖业务错误 |
| 第 3 轮 | AI 多轮追问（规划器带上一轮工具结果，「那英语呢」可接上）；选课容量 + 时间冲突校验；健康检查补模型状态与数据库延迟 |
| 第 4 轮 | 管理员班级概览（人数/平均分/及格率/学分）；发通知空内容追问 + 覆盖人数预览 |
| 第 5 轮 | 学生首页待办聚合（申请进度/未读/补考/近期考试）；「我的申请记录」菜单；调课审批显示理由；同一套 60 项用例在 PostgreSQL 上跑通 |

### 功能清单补充

- 学生：我的申请记录、首页待办卡片、日历点选、消息已读。
- 教师：班级列表/学生名单、成绩筛选、发通知范围预览、监考/教材/调课审批。
- 管理员：学生申请审批、批量导入、班级概览、数据总览。

### 测试

- `python scripts/smoke_test.py` → 60 项，SQLite 与 PostgreSQL 双跑全过。
- `BASE=http://<ip>:8000 python scripts/load_test.py` → 服务器本机 150 次并发全成功，平均 67ms、P95 118ms；公网 90 次全成功，平均 261ms、P95 705ms（受 1Mbps 带宽限制）。
- `bash scripts/sweep_health.sh` → 31 个线上接口状态码一览。
- AI 意图覆盖：13 条问法（含多轮追问、游戏拦截）线上实测全中。

## 七、常见问题

- **启动报 ModuleNotFoundError**：确认虚拟环境已激活并执行 `pip install -r requirements.txt`。
- **想换成 MySQL**：`pip install aiomysql pymysql`，把 `.env` 里 `DATABASE_URL` 改成 `mysql+aiomysql://user:pass@host:3306/db?charset=utf8mb4`，删掉旧 SQLite 后重启即可建表。
- **AI 一直回答「我暂时没听懂」**：说明走了离线规则，换个说法（带上课程名/星期/「成绩」「课表」「预约」等关键词），或配置 API Key。
- **LangSmith 没有数据**：确认 `LANGCHAIN_TRACING_V2=true` 且 `LANGCHAIN_API_KEY` 正确，重启服务。

---

## 八、可以继续扩展的方向

1. 微信小程序 / Vue3 前端替换内置单页；
2. 把 RAG 换成 FAISS + bge-m3 本地向量模型，支持 PDF 规章入库；
3. 教师端增加监考安排、审批流（教研室主任 → 教学院长）；
4. 用 LangGraph 的 interrupt 做「调课审批」人工介入节点；
5. 引入 Alembic 做数据库版本迁移，Docker Compose 一键部署。
