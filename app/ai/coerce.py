# -*- coding: utf-8 -*-
"""参数归一化工具。

为什么需要这一层：模型（尤其是中英文混说的场景）在抽参数时经常把
「星期几」抽成"周三""星期三""礼拜三"这样的字符串，甚至带"这周""下"这样的修饰词。
如果他直接传给 SQL 查询，SQL 永远查不到数据，用户会看到"你本班没有排课"这种假空结果。
所以所有对外暴露的数值型参数，进工具的第一件事就是过一遍这里。
"""

WEEK_TEXT = {
    "一": 1, "1": 1, "二": 2, "2": 2, "三": 3, "3": 3,
    "四": 4, "4": 4, "五": 5, "5": 5, "六": 6, "6": 6,
    "日": 7, "天": 7, "7": 7,
}


def weekday_num(value, default: int = 0) -> int:
    """把任意"星期几"表达折算成 1-7 的整数；无法识别时返回 default。

    支持：3 / "3" / 3.0 / "周三" / "星期三" / "礼拜3" / "这周三" / "整周" / 空值。
    返回 0 表示"整周"，调用方按不加过滤处理。
    """
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value if 1 <= value <= 7 else default
    if isinstance(value, float):
        n = int(value)
        return n if 1 <= n <= 7 else default

    text = str(value).strip()
    if not text:
        return default
    if text in ("整周", "本周", "全部", "all", "0", "今天"):
        return 0
    if text.isdigit():
        n = int(text)
        return n if 1 <= n <= 7 else default

    # 逐个汉字找"一二三四五六日天"，取第一个能命中的
    for ch in text:
        if ch in WEEK_TEXT:
            return WEEK_TEXT[ch]
    return default


def section_num(value, default: int = 1) -> int:
    """把"第3节""3-4节""三"这类表达折算成起始节次整数。"""
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        n = int(value)
        return n if 1 <= n <= 12 else default
    text = str(value)
    for token in text.replace("第", " ").replace("节", " ").replace("-", " ").split():
        if token.isdigit():
            n = int(token)
            if 1 <= n <= 12:
                return n
    for ch in text:
        if ch in WEEK_TEXT and WEEK_TEXT[ch] <= 7:
            return WEEK_TEXT[ch]
    return default
