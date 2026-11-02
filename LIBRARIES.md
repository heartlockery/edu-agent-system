# 用到的插件与库说明（单独文件）

本文档对应 requirements.txt 与前端页面，说明每个依赖**用在哪、解决什么问题、为什么选它**。

## 一、后端 Python 库

### 1. Web 框架与运行时

| 库 | 版本 | 用途 | 在项目里的位置 |
| --- | --- | --- | --- |
| fastapi | >=0.115 | 异步 Web 框架，自动生成 OpenAPI 文档 | app/main.py、app/api/*.py |
| uvicorn[standard] | >=0.30 | ASGI 服务器，带 --reload 热重载 | 启动命令 `uvicorn app.main:app --reload` |
| python-multipart | >=0.0.9 | 解析 multipart 表单，**教师上传 Excel 必需** | app/api/teacher.py 的 UploadFile |
| httpx | >=0.27 | 异步 HTTP 客户端（LangChain 内部也用它） | 依赖传递 + 调试脚本 |

### 2. 数据库

| 库 | 版本 | 用途 |
| --- | --- | --- |
| SQLAlchemy | >=2.0.30 | 异步 ORM，定义 13 张表、查询、事务 |
| aiosqlite | >=0.20 | 本地默认的异步 SQLite 驱动（零配置） |
| aiomysql | >=0.2 | 线上云 MySQL 的异步驱动 |
| pymysql | >=1.1 | aiomysql 的同步底层，部分工具依赖 |

切换数据库只改 `.env` 的 `DATABASE_URL`，代码零改动。

### 3. AI / Agent 层

| 库 | 版本 | 用途 | 说明 |
| --- | --- | --- | --- |
| langchain-core | >=0.3 | Prompt / Message / Runnable 抽象 | 大模型调用的基础类型 |
| langchain-openai | >=0.2 | ChatOpenAI、OpenAIEmbeddings | 兼容 DeepSeek、通义、OpenAI 等 OpenAI 协议服务 |
| langgraph | >=0.2.40 | 状态图编排 + MemorySaver 多轮记忆 | app/ai/graph.py：intake→planner→executor→responder |
| langsmith | >=0.1.100 | 链路追踪（trace），可视化每一步工具调用 | `@traceable` 装饰 run_agent，环境变量控制开关 |

### 4. 数据处理

| 库 | 版本 | 用途 |
| --- | --- | --- |
| openpyxl | >=3.1.2 | 读写 .xlsx：成绩导入/导出、三份课表生成 |
| pandas | >=2.2 | 批量清洗成绩表（备用；核心链路用 openpyxl 直读，避免大依赖阻塞） |
| numpy | >=1.26 | 离线版 RAG 的向量矩阵与余弦相似度计算 |

### 5. 未使用但可选的增强项

| 库 | 何时启用 |
| --- | --- |
| faiss-cpu | 规章片段超过 10 万条，需要 ANN 检索时 |
| jieba | 想让离线 RAG 的中文分词更准确时（当前用字符 n-gram 免依赖实现） |

### 6. 刻意不引入的依赖

| 常见选择 | 本项目做法 | 原因 |
| --- | --- | --- |
| pydantic-settings | 自己写 30 行 .env 解析 | 少一个依赖，Windows 上更省事 |
| python-jose / pyjwt | 标准库 hmac 实现令牌 | 教学演示足够，且避免版本冲突 |
| passlib | 标准库 pbkdf2_hmac | 同上 |
| alembic | 启动时 create_all | Demo 阶段建表足够，生产再引入迁移 |
| 前端 Vite/React | 原生 HTML + JS 单文件 | 无需 Node 环境，双击就能改 |

## 二、前端

前端为单文件 `static/index.html`：原生 HTML + CSS + JavaScript（fetch + 事件委托），**不需要 npm、不需要打包**。
内置登录页、三端菜单、数据表格、课表网格、AI 对话窗。

## 三、VS Code 插件推荐

| 插件 | 作用 |
| --- | --- |
| Python（Microsoft） | 解释器选择、虚拟环境识别、调试 |
| Pylance | 类型提示，本项目用了较多类型标注，收益明显 |
| SQLite Viewer | 直接点开 `data/edu.db` 看表结构和数据 |
| REST Client / Thunder Client | 调 `/api/*` 接口（也可直接用 /docs） |
| Excel Viewer | 在编辑器里预览成绩与课表 xlsx |
| Docker（可选） | 后续容器化部署 |

> 本项目属于 Python + 原生前端项目，**不需要**在 VS Code 里安装任何专门的「插件包」即可运行；上面只是提升开发体验的推荐项。

## 四、外部服务（可选）

| 服务 | 作用 | 配置项 |
| --- | --- | --- |
| DeepSeek / 通义 / OpenAI 兼容 API | 学生端、教师端大模型 | STUDENT_LLM_* / TEACHER_LLM_* |
| LangSmith | trace 追踪与调试 | LANGCHAIN_TRACING_V2、LANGCHAIN_API_KEY、LANGCHAIN_PROJECT |
| MySQL（云服务器） | 线上数据库 | DATABASE_URL |

## 五、版本兼容说明

- Python 3.10+（实测 3.12），SQLAlchemy 2.0 异步写法与 `X | None` 类型语法需要 3.10 以上。
- LangGraph 0.2.x 与 langchain-core 0.3.x 配套；升级 LangGraph 到 0.3/1.x 时 StateGraph 用法不变，MemorySaver 导入路径可能变化。
- 云数据库建议 MySQL 8.0+，字符集 `utf8mb4`（中文姓名、通知内容必须）。
