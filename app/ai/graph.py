"""
模块 19 · LangGraph 智能体编排
--------------------------------------------------------------------
作用：把「提交问题 -> 规划选工具 -> 执行工具 -> 润色作答」串成一张状态图，
      用 LangGraph 负责状态流转与多轮记忆（checkpointer），再用 LangSmith 记录链路。
图结构：
    intake ──> planner ──(有工具调用)──> executor ──> responder ──> END
                  └──────(无需工具)─────────────────> responder ──> END
记忆：thread_id = 角色:账号:会话ID，同一个会话内的多轮对话自动带上历史。
"""

from __future__ import annotations

from typing import Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.ai.llm import get_llm
from app.ai.prompts import STUDENT_SYSTEM, TEACHER_SYSTEM
from app.ai.tools_teacher import tools_for
from app.config import settings

# 15.0 LangSmith 追踪装饰器：没装或没配置时自动退化为空装饰器
try:
    from langsmith import traceable
except Exception:                     # pragma: no cover

    def traceable(*_args, **_kwargs):
        def _deco(fn):
            return fn

        return _deco


SYSTEM_PROMPTS = {"student": STUDENT_SYSTEM, "teacher": TEACHER_SYSTEM}


class AgentState(TypedDict, total=False):
    """15.1 图状态：一次对话里在各节点之间流转的数据。"""

    role: str
    question: str
    messages: list[dict[str, Any]]       # 多轮历史（裁剪到最近 12 条）
    plan: list[dict[str, Any]]           # 规划器给出的工具调用
    tool_results: list[dict[str, Any]]   # 工具执行结果
    ui_actions: list[dict[str, Any]]     # 让前端自动跳转/下载的动作
    answer: str
    model: str
    trace: list[str]


def _cfg(config: RunnableConfig) -> dict:
    return (config or {}).get("configurable", {})


# ---------------------------------------------------------------
# 15.2 节点一：入库。把用户这句话追加进历史，供规划和作答使用
# ---------------------------------------------------------------
async def intake_node(state: AgentState, config: RunnableConfig) -> dict:
    messages = list(state.get("messages") or [])
    messages.append({"role": "user", "content": state.get("question", "")})
    return {"messages": messages[-12:]}


# ---------------------------------------------------------------
# 15.3 节点二：规划。交给该角色的大模型决定「调哪个工具、传什么参数」
# ---------------------------------------------------------------
async def planner_node(state: AgentState, config: RunnableConfig) -> dict:
    role = state.get("role", "student")
    tools = tools_for(role)
    history = "\n".join(
        m["role"] + ": " + str(m["content"])[:120] for m in (state.get("messages") or [])[-6:-1]
    )
    # 15.3b 把上一轮工具结果摘要也交给规划器，这样「那英语呢」「它的考试呢」能接上
    prev = state.get("tool_results") or []
    if prev:
        hint = "；".join(r["tool"] + " -> " + str(r.get("message", ""))[:60] for r in prev[-2:])
        history = history + "\n[上一轮工具结果] " + hint

    llm = get_llm(role)
    calls = await llm.plan(state.get("question", ""), tools, history)

    trace = list(state.get("trace") or [])
    trace.append("规划：" + ("、".join(c["tool"] for c in calls) if calls else "无需工具，直接回答"))
    return {"plan": calls, "trace": trace, "model": llm.model_name}


# ---------------------------------------------------------------
# 15.4 节点三：执行。真正去数据库里取数/写数（工具失败不影响整体回答）
# ---------------------------------------------------------------
async def executor_node(state: AgentState, config: RunnableConfig) -> dict:
    ctx = _cfg(config)["ctx"]
    tools = tools_for(state.get("role", "student"))
    results: list[dict[str, Any]] = []

    for call in state.get("plan") or []:
        name = call.get("tool", "")
        args = call.get("args") or {}
        spec = tools.get(name)
        if not spec:
            continue
        try:
            res = await spec["fn"](ctx, **args)
        except TypeError as exc:                     # 参数不匹配（模型编了参数）
            res = {"ok": False, "data": [], "message": "工具参数不正确：" + str(exc)[:80]}
        except Exception as exc:                     # 其它异常：兜底，不中断对话
            res = {"ok": False, "data": [], "message": "执行 " + name + " 时出错：" + str(exc)[:120]}
        results.append({
            "tool": name,
            "args": args,
            "ok": bool(res.get("ok", True)),
            "message": res.get("message", ""),
            "data": res.get("data", []),
            "ui": res.get("ui", []),
        })
        await ctx["db"].flush()

    trace = list(state.get("trace") or [])
    trace.append("执行：" + "、".join(r["tool"] for r in results))
    return {"tool_results": results, "trace": trace}


# ---------------------------------------------------------------
# 15.5 节点四：作答。把工具结果交给该角色的大模型润色成人话
# ---------------------------------------------------------------
async def responder_node(state: AgentState, config: RunnableConfig) -> dict:
    role = state.get("role", "student")
    question = state.get("question", "")
    results = state.get("tool_results") or []
    llm = get_llm(role)
    answer = await llm.answer(question, results, SYSTEM_PROMPTS.get(role, STUDENT_SYSTEM))

    messages = list(state.get("messages") or []) + [{"role": "assistant", "content": answer}]
    ui_actions = [act for r in results for act in (r.get("ui") or [])]
    trace = list(state.get("trace") or [])
    trace.append("作答完成（" + ("在线模型" if llm.online else "离线规则模式") + "）")
    return {"answer": answer, "messages": messages[-12:], "ui_actions": ui_actions,
            "trace": trace, "model": llm.model_name}


def _route_after_planner(state: AgentState) -> str:
    """15.6 条件边：有工具调用就去执行，否则直接作答。"""
    return "executor" if state.get("plan") else "responder"


def build_graph():
    """15.7 组装并编译状态图；MemorySaver 提供多轮记忆。"""
    graph = StateGraph(AgentState)
    graph.add_node("intake", intake_node)
    graph.add_node("planner", planner_node)
    graph.add_node("executor", executor_node)
    graph.add_node("responder", responder_node)

    graph.set_entry_point("intake")
    graph.add_edge("intake", "planner")
    graph.add_conditional_edges("planner", _route_after_planner,
                                {"executor": "executor", "responder": "responder"})
    graph.add_edge("executor", "responder")
    graph.add_edge("responder", END)
    return graph.compile(checkpointer=MemorySaver())


agent_graph = build_graph()


@traceable(name="edu-agent-chat", run_type="chain")
async def run_agent(role: str, question: str, session_id: str, db, ctx: dict) -> dict:
    """15.8 对外唯一入口：API 层只调这个函数。

    - thread_id 保证同一会话的多轮记忆
    - config 里带 db 与 ctx（登录态），它们不参与 checkpoint 持久化
    """
    settings.apply_langsmith_env()
    config = {
        "configurable": {
            "thread_id": role + ":" + str(ctx.get("username", "")) + ":" + session_id,
            "db": db,
            "ctx": ctx,
        }
    }
    out = await agent_graph.ainvoke({"role": role, "question": question}, config=config)
    return {
        "answer": out.get("answer", ""),
        "tool_calls": out.get("plan") or [],
        "tool_results": out.get("tool_results") or [],
        "ui_actions": out.get("ui_actions") or [],
        "model": out.get("model", ""),
        "trace": out.get("trace") or [],
    }
