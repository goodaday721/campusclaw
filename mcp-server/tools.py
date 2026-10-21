"""Tool implementations for the campus MCP server (lesson 6).

Both tools give guidance/data only — never a final numeric or full answer to
a homework problem, matching the lesson-5 "解题引导" tone. Text responses are
Chinese and self-contained.
"""
import math

# ---------------------------------------------------------------------------
# formula_hint: keyword-matched guidance library. Gives the formula / next
# step hints for common middle-school math topics; never computes the answer.
# ---------------------------------------------------------------------------
_HINTS = [
    (
        ("去括号", "括号"),
        "去括号提示：括号前是乘数时，先把系数乘到括号内每一项；括号前是负号时，"
        "去掉括号后括号内每一项都要变号。检查方法：展开后用代入一个具体数值验证等式两边是否相等。",
    ),
    (
        ("移项",),
        "移项提示：把含未知数的项移到等号一边、常数项移到另一边，移项要变号。"
        "移完先合并同类项，再用系数化为 1。",
    ),
    (
        ("通分", "分母"),
        "通分提示：先找各分母的最简公分母（系数取最小公倍数，字母取最高次幂），"
        "再把每个分式变成同分母。分子运算时记得给分子整体加括号。",
    ),
    (
        ("配方", "一元二次"),
        "配方法提示：先把二次项系数化为 1，再把常数项移到等号右边，"
        "两边同时加上一次项系数一半的平方，左侧即可写成完全平方式。",
    ),
    (
        ("因式分解", "十字相乘", "提公因式"),
        "因式分解提示：先看有没有公因式可提，再看项数——二项考虑平方差，"
        "三项考虑完全平方或十字相乘，注意分解到不能再分解为止。",
    ),
    (
        ("方程组", "二元一次"),
        "方程组提示：观察两式系数，同一个未知数成倍数关系用加减消元，"
        "否则用代入消元；解出一个未知数后回代求另一个，最后把两个解代回原方程组检验。",
    ),
    (
        ("不等式",),
        "不等式提示：两边同乘或同除以负数时，不等号方向必须改变；"
        "其余步骤与解方程类似，最后在数轴上表示解集检验端点。",
    ),
]

_FORMULA_HINT_SPEC = {
    "name": "formula_hint",
    "description": (
        "按学生的问题给出公式或解题步骤提示，帮助学生自己完成推导；"
        "只给思路与公式提示，不给出最终数值答案。适用于数学解题引导场景，"
        "当学生卡在某一步（去括号、移项、通分、配方等）时使用。"
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "学生卡住的问题或步骤描述，如“去括号这一步我不会”",
            }
        },
        "required": ["query"],
    },
}

_UNIT_HINT_SPEC = {
    "name": "unit_convert",
    "description": (
        "单位换算工具：把一个数值在常见长度或重量单位之间换算（如千米↔米、"
        "千克↔克）。返回换算结果与进率说明；注意它只负责单位换算这一步，"
        "不负责解题。当提问涉及单位换算时使用。"
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "value": {"type": "number", "description": "待换算的数值"},
            "from_unit": {"type": "string", "description": "原单位，如 千米/km"},
            "to_unit": {"type": "string", "description": "目标单位，如 米/m"},
        },
        "required": ["value", "from_unit", "to_unit"],
    },
}

TOOLS = [_FORMULA_HINT_SPEC, _UNIT_HINT_SPEC]

_LENGTH = {
    "km": 1000.0, "千米": 1000.0, "kilometer": 1000.0, "kilometre": 1000.0,
    "hm": 100.0, "百米": 100.0,
    "dam": 10.0, "十米": 10.0,
    "m": 1.0, "米": 1.0, "meter": 1.0, "metre": 1.0,
    "dm": 0.1, "分米": 0.1,
    "cm": 0.01, "厘米": 0.01, "centimeter": 0.01, "centimetre": 0.01,
    "mm": 0.001, "毫米": 0.001,
}

_WEIGHT = {
    "t": 1000.0, "吨": 1000.0, "ton": 1000.0, "tonne": 1000.0,
    "kg": 1.0, "千克": 1.0, "公斤": 1.0, "kilogram": 1.0,
    "g": 0.001, "克": 0.001, "gram": 0.001,
    "mg": 1e-6, "毫克": 1e-6,
}


def formula_hint(query):
    """Return guidance text for the topic matched in `query` (no answers)."""
    text = str(query or "").strip()
    if not text:
        return "请描述你卡住的具体步骤，例如“去括号这一步我不会”。"
    for keys, hint in _HINTS:
        if any(k in text for k in keys):
            return hint
    return (
        "通用解题提示：先把已知条件和要求的问题分别列出来，"
        "再想需要哪个公式或法则；把大步骤拆成小步骤逐步推进，"
        "每一步都写清依据。完成后用代入或估算检验一遍。"
    )


def unit_convert(value, from_unit, to_unit):
    """Convert between common length/weight units; returns explanatory text."""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "换算失败：value 必须是数字。"
    src = str(from_unit or "").strip().lower()
    dst = str(to_unit or "").strip().lower()
    if src in _LENGTH and dst in _LENGTH:
        table, kind = _LENGTH, "长度"
    elif src in _WEIGHT and dst in _WEIGHT:
        table, kind = _WEIGHT, "重量"
    else:
        return (
            f"换算失败：暂不支持“{from_unit}”到“{to_unit}”。"
            "目前支持的单位——长度：km/千米、m/米、dm/分米、cm/厘米、mm/毫米；"
            "重量：t/吨、kg/千克、g/克、mg/毫克。"
        )
    factor = table[src] / table[dst]
    result = num * factor
    if math.isfinite(result) and float(result).is_integer():
        shown = str(int(result))
    else:
        shown = f"{result:.6g}"
    return f"{num} {from_unit} = {shown} {to_unit}（1 {from_unit} = {factor:g} {to_unit}，{kind}单位换算）。"


def call_tool(name, arguments):
    """Dispatch a tools/call. Returns (text, is_error)."""
    args = arguments if isinstance(arguments, dict) else {}
    if name == "formula_hint":
        return formula_hint(args.get("query")), False
    if name == "unit_convert":
        if "value" not in args or "from_unit" not in args or "to_unit" not in args:
            return "参数不完整：value、from_unit、to_unit 均为必填。", True
        return unit_convert(args["value"], args["from_unit"], args["to_unit"]), False
    return f"未知工具：{name}", True
