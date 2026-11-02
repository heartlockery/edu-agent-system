"""
模块 16 · 联网搜索（只查学习相关资料）
--------------------------------------------------------------------
作用：给学生/老师提供「上网查资料」的能力，用于概念解释、学习方法、课程延伸阅读。
实现：先试 Bing（国内可访问），失败再试 DuckDuckGo；两边都失败就返回空，
      由上层给一句温柔提示，不会让对话卡住。
安全：搜索前先过内容边界检查，游戏、代刷类关键词直接拒绝。
"""

from __future__ import annotations

import html as html_lib
import re

import httpx

from app.ai.guard import check

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

_TAG = re.compile(r"<[^>]+>")


def _strip(text: str) -> str:
    return html_lib.unescape(_TAG.sub("", text or "")).strip()


def _parse_bing(html: str) -> list[dict]:
    """Bing 结果页：<li class="b_algo"> 里包含标题与摘要。"""
    out: list[dict] = []
    for block in re.findall(r'<li class="b_algo".*?</li>', html, flags=re.S)[:5]:
        m = re.search(r'<h2[^>]*>.*?<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, flags=re.S)
        if not m:
            continue
        snippet = ""
        p = re.search(r"<p[^>]*>(.*?)</p>", block, flags=re.S)
        if p:
            snippet = _strip(p.group(1))[:160]
        out.append({"title": _strip(m.group(2))[:80], "url": m.group(1), "snippet": snippet})
    return out


def _parse_ddg(html: str) -> list[dict]:
    out: list[dict] = []
    pattern = r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</a>'
    for url, title, snippet in re.findall(pattern, html, flags=re.S)[:5]:
        out.append({"title": _strip(title)[:80], "url": url, "snippet": _strip(snippet)[:160]})
    return out


FILLER = re.compile(r"推荐|帮我|查一下|搜一下|我想|想要|几个|一些|的网站|网站|资料|怎么样|如何学好")


def _variants(query: str) -> list[str]:
    """12c.1 搜索词优化：去掉口语填充词，必要时补上「教程」，提高命中率。"""
    cleaned = FILLER.sub(" ", query).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    out = [query]
    if cleaned and cleaned != query and len(cleaned) >= 2:
        out.append(cleaned)
        out.append(cleaned + " 教程")
    return out


async def search(query: str, limit: int = 5) -> list[dict]:
    """联网搜索入口：返回 [{title, url, snippet}]，失败返回空列表。"""
    if check(query):                       # 游戏/作弊类直接不查
        return []
    headers = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"}

    for q in _variants(query):
        url_q = httpx.QueryParams({"q": q})
        for url, parser in (
            (("https://cn.bing.com/search?" + str(url_q)), _parse_bing),
            (("https://html.duckduckgo.com/html/?" + str(url_q)), _parse_ddg),
        ):
            try:
                async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
                    resp = await client.get(url, headers=headers)
                if resp.status_code != 200:
                    continue
                results = [r for r in parser(resp.text) if r["title"] and r["url"].startswith("http")]
                if len(results) >= 2:
                    return results[:limit]
            except Exception:
                continue
    return []
