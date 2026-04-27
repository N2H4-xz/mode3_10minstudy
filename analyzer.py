"""
analyzer.py
聊天记录风格分析模块。
单次 LLM 调用，分析整段对话，返回 StyleProfile。
"""

from __future__ import annotations

import json
import re

import openai

from config import CHARACTERISTICS_SPEC, LABEL_MAP, get_model_name
from models import Characteristic, RawStats, StyleProfile


# ── Prompt ──────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
你是一位专业的中文语言风格分析师。你的任务是按照六类风格指标，分析一段聊天记录，提取说话人的语言风格特征。

【必须使用的六类指标】
1. 词汇复杂度：平均词长、type-token ratio、高级词汇使用情况。
2. 句法复杂度：平均句子长度、从句出现频率、词性分布。
3. 形式化指数：代词比例、功能词比例、正式表达与口语表达占比。
4. 情感表达度：感叹号、表情符号、强化词（如“绝对”“非常”）或情感词汇的使用频率。
5. 可读性指标：长句比例、分句密度、抽象词密度、结构清晰度、阅读难度。
6. 人际交往标记：礼貌策略（如“请”“谢谢”）、免责声明（如“可能”“我认为”）、模糊语（如“某种程度上”“大概”）以及表达立场或礼貌程度的委婉语。

分析要求：
1. 必须分析整段聊天记录，不能只看前几条消息。
2. 只能输出上述六类一级特征，禁止新增“标点风格”“话题转换”“回答详略”等独立一级 key。
3. 每个一级特征的 value 必须覆盖该类别下列出的具体指标，只输出指标值和判断，不解释指标来源。
4. 对数值型指标给出估算值和简短解释；比例类使用 0.0~1.0。
5. 每个一级特征必须从原文摘取 3~5 个真实例句作为证据（直接引用，不改写）。
6. confidence 是你对该类别整体判断的把握（0.0~1.0），不确定时如实给低分。

【重要：只关注说话格式，不关注内容】
7. 本分析只提取“怎么说”的格式规律，严禁在 value 和 evidence 字段中出现具体话题名称、专业领域词汇或对用户观点的总结。
8. examples 选取原则：优先选能展示该类别指标的短例，而非信息量丰富、内容重要的句子；若一句话既能体现格式又带有大量具体内容，尽量选更短、格式特征更纯粹的那句。
9. 高级词汇、词性分布、情感词汇等指标只描述语言结构层面的使用情况，不总结具体主题、立场或知识领域。

输出格式：严格输出 JSON，不要有任何其他文字，结构如下：
{
  "stats": {
    "total_messages": <int>,
    "avg_chars_per_message": <float>,
    "total_chars": <int>
  },
  "characteristics": {
    "lexical_complexity": {
      "value": "平均词长：<估算>；type-token ratio：<0.0~1.0估算>；高级词汇使用情况：<描述>",
      "examples": ["<原文例句1>", "..."],
      "evidence": "<一句话说明词汇复杂度判断依据>",
      "confidence": <0.0~1.0>
    },
    "syntactic_complexity": {
      "value": "平均句子长度：<估算>；从句出现频率：<估算>；词性分布：<描述>",
      "examples": ["<原文例句1>", "..."],
      "evidence": "<一句话说明句法复杂度判断依据>",
      "confidence": <0.0~1.0>
    },
    "formality_indices": {
      "value": "代词比例：<0.0~1.0估算>；功能词比例：<0.0~1.0估算>；正式表达占比：<0.0~1.0估算>；口语表达占比：<0.0~1.0估算>",
      "examples": ["<原文例句1>", "..."],
      "evidence": "<一句话说明形式化指数判断依据>",
      "confidence": <0.0~1.0>
    },
    "emotiveness": {
      "value": "感叹号频率：<估算>；表情符号频率：<估算>；强化词频率：<估算>；情感词汇频率：<估算>",
      "examples": ["<原文例句1>", "..."],
      "evidence": "<一句话说明情感表达度判断依据>",
      "confidence": <0.0~1.0>
    },
    "readability_metrics": {
      "value": "长句比例：<0.0~1.0估算>；分句密度：<估算>；抽象词密度：<0.0~1.0估算>；结构清晰度：<描述>；阅读难度：<描述>",
      "examples": ["<原文例句1>", "..."],
      "evidence": "<一句话说明可读性判断依据>",
      "confidence": <0.0~1.0>
    },
    "interpersonal_markers": {
      "value": "礼貌策略：<描述>；免责声明/立场标记：<描述>；模糊语/委婉语：<描述>",
      "examples": ["<原文例句1>", "..."],
      "evidence": "<一句话说明人际交往标记判断依据>",
      "confidence": <0.0~1.0>
    }
  }
}
"""


def _build_user_message(chat_text: str) -> str:
    char_count = len(chat_text)
    return (
        f"以下是需要分析的聊天记录（共约 {char_count} 字）：\n\n"
        f"<chat_log>\n{chat_text}\n</chat_log>\n\n"
        "请分析上述聊天记录中说话人的语言风格特征，输出严格 JSON。"
    )


# ── 解析 ────────────────────────────────────────────────────────────────────

def _extract_json(raw: str) -> dict:
    """从 LLM 返回文本中提取 JSON，兼容 markdown 代码块。"""
    # 去掉可能的 ```json ... ``` 包裹
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def _parse_response(data: dict) -> StyleProfile:
    stats_raw = data.get("stats", {})
    raw_stats = RawStats(
        total_messages=int(stats_raw.get("total_messages", 0)),
        avg_chars_per_message=float(stats_raw.get("avg_chars_per_message", 0.0)),
        total_chars=int(stats_raw.get("total_chars", 0)),
    )

    characteristics: dict[str, Characteristic] = {}
    chars_raw = data.get("characteristics", {})

    for spec in CHARACTERISTICS_SPEC:
        key = spec["key"]
        label = LABEL_MAP[key]
        item = chars_raw.get(key, {})
        if not item:
            # 兜底：LLM 漏输某个 key
            characteristics[key] = Characteristic(
                key=key,
                label=label,
                value="（未分析）",
                examples=[],
                evidence="LLM 未返回此特征",
                confidence=0.0,
            )
            continue

        examples = item.get("examples", [])
        # 最多保留 5 条
        if len(examples) > 5:
            examples = examples[:5]

        characteristics[key] = Characteristic(
            key=key,
            label=label,
            value=str(item.get("value", "")),
            examples=examples,
            evidence=str(item.get("evidence", "")),
            confidence=float(item.get("confidence", 0.5)),
        )

    return StyleProfile(
        characteristics=characteristics,
        raw_stats=raw_stats,
        source_length_chars=raw_stats.total_chars or len(""),
    )


# ── 公开 API ─────────────────────────────────────────────────────────────────

def analyze_chat_log(chat_text: str, client: openai.OpenAI) -> StyleProfile:
    """分析聊天记录，返回 StyleProfile。"""
    response = client.chat.completions.create(
        model=get_model_name(),
        max_tokens=4096,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_message(chat_text)}
        ],
    )
    raw_text = response.choices[0].message.content
    data = _extract_json(raw_text)
    profile = _parse_response(data)
    # 用原始文本长度补充
    profile.source_length_chars = len(chat_text)
    return profile
