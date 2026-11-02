"""
模块 12 · 双大模型接入层
--------------------------------------------------------------------
作用：同一套接口，按角色（student / teacher）取不同模型配置：
      - 有 API Key：走 langchain-openai 的 ChatOpenAI（兼容 DeepSeek / 通义 / OpenAI 等）
      - 没有 Key：自动降级为离线规则引擎（见 mock_llm.py），保证项目零配置可跑
      并把「规划（选工具）」与「作答（润色）」封装成统一方法，供 LangGraph 调用。
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.ai import mock_llm
from app.ai.prompts import PLANNER_TEMPLATE, RESPONDER_TEMPLATE
from app.config import settings

# 10.0 代码块标记（三个反引号），在这里用字符拼出来，避免源码里的转义困扰
FENCE = chr(96) * 3


def _extract_json(text: str) -> dict:
    """10.1 从模型输出里抠出第一个 JSON 对象，兼容代码块包裹与前后废话。"""
    text = text.strip()
    if text.startswith(FENCE) or text.endswith(FENCE):
        text = text.replace(FENCE + "json", "").replace(FENCE, "").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return {}
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return {}


def _tool_catalog(tools: dict[str, dict]) -> str:
    """10.1.1 把工具注册表渲染成提示词里的工具清单。"""
    lines = []
    for name, spec in tools.items():
        params = ", ".join(spec.get("params", {}).keys()) or "无参数"
        lines.append("- " + name + ": " + spec["desc"] + " | 参数: " + params)
    return "\n".join(lines)


class DualLLM:
    """10.2 一个角色一个实例：student 与 teacher 用不同模型 / 温度 / Key。"""

    def __init__(self, role: str):
        self.role = "teacher" if role == "teacher" else "student"
        self.cfg = settings.llm_config(self.role)
        self.model_name = self.cfg["model"]
        self.online = bool(self.cfg.get("api_key"))
        self._client = None

    # ---- 10.2.1 懒加载 ChatOpenAI：没有 Key 时不实例化，避免启动报错 ----
    def _chat(self):
        if self._client is None:
            from langchain_openai import ChatOpenAI

            self._client = ChatOpenAI(
                model=self.cfg["model"],
                api_key=self.cfg["api_key"],
                base_url=self.cfg["base_url"],
                temperature=self.cfg["temperature"],
                timeout=30,
                max_retries=1,
            )
        return self._client

    async def complete(self, system: str, user: str) -> str:
        """10.2.2 单轮文本补全（规划、润色、学习建议都走这里）。"""
        if not self.online:
            raise RuntimeError("offline")
        from langchain_core.messages import HumanMessage, SystemMessage

        msg = await self._chat().ainvoke([SystemMessage(content=system), HumanMessage(content=user)])
        return (msg.content or "").strip()

    # ---- 10.2.3 规划：先问模型「该调哪些工具」，解析成结构化调用列表 ----
    async def plan(self, question: str, tools: dict[str, dict], history: str = "") -> list[dict]:
        if not self.online:
            return await mock_llm.rule_plan(question, self.role)
        prompt = PLANNER_TEMPLATE.format(
            tools=_tool_catalog(tools),
            history=history or "（无）",
            question=question,
        )
        try:
            raw = await self.complete(
                "你是严格的 JSON 生成器，只输出 JSON，不要 markdown 代码块。", prompt
            )
            data = _extract_json(raw)
            calls = data.get("tool_calls") or []
            cleaned: list[dict] = []
            for c in calls[:2]:
                if not isinstance(c, dict):
                    continue
                name = str(c.get("tool", "")).strip()
                if name in tools:
                    args = c.get("args") or {}
                    cleaned.append({"tool": name, "args": args if isinstance(args, dict) else {}})
            return cleaned
        except Exception:
            # 模型不稳定时兜底：走规则引擎，保证功能不中断
            return await mock_llm.rule_plan(question, self.role)

    # ---- 10.2.4 作答：把工具结果润色成人话 ----
    async def answer(self, question: str, results: list[dict], system: str) -> str:
        if not self.online:
            return mock_llm.compose_answer(question, results)
        payload: Any = json.dumps(results, ensure_ascii=False, default=str)[:6000]
        try:
            return await self.complete(
                system + "\n\n" + RESPONDER_TEMPLATE.format(question=question, results=payload),
                "请直接给出最终答复。",
            )
        except Exception:
            return mock_llm.compose_answer(question, results)


def get_llm(role: str) -> DualLLM:
    """10.3 工厂函数：调用方只关心角色，不关心底层是哪个模型。"""
    return DualLLM(role)
