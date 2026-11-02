"""
模块 1 · 配置总控
--------------------------------------------------------------------
作用：把「数据库 / 学生端大模型 / 教师端大模型 / LangSmith / RAG / 目录」六类
      外部依赖收敛到一个 Settings 对象，其他模块只 import settings。
设计：不额外依赖 pydantic-settings，自带一个极简 .env 解析器，
      Windows + VS Code 双击就能跑；没有填 API Key 时自动降级到离线规则模式。
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------
# 1.1 目录定义：所有路径都相对项目根目录，避免换机器后路径失效
# ---------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
EXPORT_DIR = DATA_DIR / "exports"      # 教师端「导出成绩文件」的落地目录
KB_DIR = BASE_DIR / "knowledge"        # RAG 知识库（教务规章 Markdown）
STATIC_DIR = BASE_DIR / "static"       # 内置前端页面


def _load_dotenv(path: Path) -> None:
    """1.2 最小 .env 解析器：KEY=VALUE，# 为注释，不覆盖已存在的系统环境变量。"""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(BASE_DIR / ".env")


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


class Settings:
    """1.3 全局配置对象（模块级单例 settings）。"""

    # ---- 基础信息 ----
    app_name: str = "智能教务系统"
    version: str = "1.0.0"
    debug: bool = _env("DEBUG", "true").lower() == "true"
    secret_key: str = _env("SECRET_KEY", "dev-secret-change-me")
    token_expire_minutes: int = int(_env("TOKEN_EXPIRE_MINUTES", "720"))

    # ---- 数据库：默认本地 SQLite，填 DATABASE_URL 即切到云端 MySQL ----
    database_url: str = _env(
        "DATABASE_URL",
        "sqlite+aiosqlite:///" + (DATA_DIR / "edu.db").as_posix(),
    )

    # ---- 双大模型：一个服务学生，一个服务老师 ----
    student_model: str = _env("STUDENT_LLM_MODEL", "deepseek-chat")
    student_api_key: str = _env("STUDENT_LLM_API_KEY", "")
    student_base_url: str = _env("STUDENT_LLM_BASE_URL", "https://api.deepseek.com/v1")
    student_temperature: float = float(_env("STUDENT_LLM_TEMPERATURE", "0.3"))

    teacher_model: str = _env("TEACHER_LLM_MODEL", "deepseek-chat")
    teacher_api_key: str = _env("TEACHER_LLM_API_KEY", "")
    teacher_base_url: str = _env("TEACHER_LLM_BASE_URL", "https://api.deepseek.com/v1")
    teacher_temperature: float = float(_env("TEACHER_LLM_TEMPERATURE", "0.2"))

    # ---- LangSmith 追踪 ----
    langsmith_enabled: bool = _env("LANGCHAIN_TRACING_V2", "false").lower() == "true"
    langsmith_api_key: str = _env("LANGCHAIN_API_KEY", "")
    langsmith_project: str = _env("LANGCHAIN_PROJECT", "edu-agent-system")
    langsmith_endpoint: str = _env("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")

    # ---- RAG ----
    # EMBEDDING_PROVIDER=offline 时用「字符 n-gram + TF-IDF」，零依赖、启动瞬间完成；
    # 只有显式配成 openai 且给了专用 Key 才会调用 /embeddings（DeepSeek 没有该接口，别混用）。
    embedding_provider: str = _env("EMBEDDING_PROVIDER", "offline")
    embedding_model: str = _env("EMBEDDING_MODEL", "text-embedding-3-small")
    embedding_api_key: str = _env("EMBEDDING_API_KEY", "")
    embedding_base_url: str = _env("EMBEDDING_BASE_URL", "https://api.openai.com/v1")
    rag_top_k: int = int(_env("RAG_TOP_K", "4"))
    rag_chunk_size: int = int(_env("RAG_CHUNK_SIZE", "420"))

    def llm_config(self, role: str) -> dict:
        """1.4 按角色取模型配置：role 只能是 student / teacher。"""
        if role == "teacher":
            return {
                "model": self.teacher_model,
                "api_key": self.teacher_api_key,
                "base_url": self.teacher_base_url,
                "temperature": self.teacher_temperature,
            }
        return {
            "model": self.student_model,
            "api_key": self.student_api_key,
            "base_url": self.student_base_url,
            "temperature": self.student_temperature,
        }

    def embeddings_online(self) -> bool:
        """1.4b 是否启用在线向量模型（默认关闭，避免启动时被网络拖住）。"""
        return self.embedding_provider.lower() == "openai" and bool(self.embedding_api_key)

    def apply_langsmith_env(self) -> None:
        """1.5 启动时把 LangSmith 参数写回环境变量，LangChain 会自动上报链路。"""
        if not (self.langsmith_enabled and self.langsmith_api_key):
            return
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = self.langsmith_api_key
        os.environ["LANGCHAIN_PROJECT"] = self.langsmith_project
        os.environ["LANGCHAIN_ENDPOINT"] = self.langsmith_endpoint

    def ensure_dirs(self) -> None:
        """1.6 启动时确保运行期目录存在。"""
        for d in (DATA_DIR, EXPORT_DIR, KB_DIR):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
