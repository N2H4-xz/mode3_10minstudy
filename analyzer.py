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
你是一位专业的中文语言风格分析师。你的任务是分析一段聊天记录，提取说话人的语言风格特征。

分析要求：
1. 必须分析整段聊天记录，不能只看前几条消息。
2. 对每个特征，要从整体角度描述规律——例如若用户长短句都有使用，应描述为"长短句混合"而不是"偏短句"。
3. 每个特征必须从原文摘取 3~5 个真实例句作为证据（直接引用，不改写）。
4. confidence 是你对该判断的把握（0.0~1.0），不确定时如实给低分。

输出格式：严格输出 JSON，不要有任何其他文字，结构如下：
{
  "stats": {
    "total_messages": <int>,
    "avg_chars_per_message": <float>,
    "total_chars": <int>
  },
  "characteristics": {
    "sentence_length": {
      "value": "<整体描述>",
      "examples": ["<原文例句1>", "..."],
      "evidence": "<一句话判断依据>",
      "confidence": <0.0~1.0>
    },
    "punctuation_style":       { "value": "...", "examples": [...], "evidence": "...", "confidence": ... },
    "formality_level":         { "value": "...", "examples": [...], "evidence": "...", "confidence": ... },
    "logical_connectors":      { "value": "...", "examples": [...], "evidence": "...", "confidence": ... },
    "response_completeness":   { "value": "...", "examples": [...], "evidence": "...", "confidence": ... },
    "topic_transition":        { "value": "...", "examples": [...], "evidence": "...", "confidence": ... },
    "message_structure":       { "value": "...", "examples": [...], "evidence": "...", "confidence": ... },
    "opener_closer_phrases":   { "value": "...", "examples": [...], "evidence": "...", "confidence": ... },
    "question_usage":          { "value": "...", "examples": [...], "evidence": "...", "confidence": ... },
    "vocabulary_characteristics": { "value": "...", "examples": [...], "evidence": "...", "confidence": ... }
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
