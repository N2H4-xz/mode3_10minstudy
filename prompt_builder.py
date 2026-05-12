"""
prompt_builder.py
生成两版风格模仿提示词：
  - LLM 生成版：调用 LLM，让其整理为流畅的 system prompt
  - 模板拼接版：直接按固定模板组装 StyleProfile 数据，不调用 LLM
"""

from __future__ import annotations

import re

import openai

from config import CHARACTERISTICS_SPEC, get_model_name
from models import Characteristic, MimicryPromptPair, StyleProfile


# ── LLM 生成版 ───────────────────────────────────────────────────────────────

_LLM_SYSTEM = """\
你是一位提示词工程师，专门为大语言模型生成"风格模仿提示词"。
你的输出将直接作为 system prompt 提供给其他 LLM，使它们能模仿特定用户的说话风格。

输出要求：
1. 用中文撰写。
2. 结构必须包含以下四个部分（使用【】作标题）：
   【说话风格总结】
   【回答样式要求】
   【参考例句】
   【不确定特征说明】
3. 直接输出 prompt 文本，不要任何解释或前言。
4. 参考例句须直接引用用户原文，不要改写。
5. 【说话风格总结】和【回答样式要求】必须围绕以下五类指标组织：词汇复杂度、句法复杂度、形式化指数、情感表达度、人际交往标记。
6. 若某个特征描述中提到"混合"或"有时……有时……"，在回答样式要求中必须体现这种双重性。

【重要约束：只输出格式指令，不输出内容倾向】
7. 生成的 prompt 必须只描述说话格式（词汇复杂度、句法复杂度、正式程度、情感表达、人际标记等），绝不提及话题偏好、专业方向或内容特征。
8. 不得新增五类之外的独立风格分类；如果需要提到标点、句长、语气词等，只能放入对应类别中。
9. 【参考例句】部分必须在所有例句之前加上这句话：「以下例句仅用于展示说话格式，模仿时只参考其句式结构与语气节奏，不要参考例句中的具体内容。」
10. 不得在 prompt 中写入任何暗示用户话题偏好的内容，即使风格画像中的例句涉及具体话题。
"""

_LLM_USER_TEMPLATE = """\
以下是从聊天记录中提取的用户风格画像，请据此生成完整的中文风格模仿提示词：

{formatted_profile}
"""


def _format_profile_for_llm(profile: StyleProfile) -> str:
    lines = []
    for spec in CHARACTERISTICS_SPEC:
        key = spec["key"]
        c: Characteristic | None = profile.get(key)
        if c is None:
            continue
        lines.append(f"【{c.label}】")
        lines.append(f"  描述：{c.value}")
        lines.append(f"  置信度：{c.confidence:.2f}")
        lines.append(f"  判断依据：{c.evidence}")
        if c.examples:
            lines.append("  例句：")
            for ex in c.examples:
                lines.append(f"    - \u201c{ex}\u201d")
        lines.append("")
    return "\n".join(lines)


def _build_llm_prompt(profile: StyleProfile) -> str:
    return _LLM_USER_TEMPLATE.format(
        formatted_profile=_format_profile_for_llm(profile)
    )


def _generate_llm_version(profile: StyleProfile, client: openai.OpenAI) -> str:
    response = client.chat.completions.create(
        model=get_model_name(),
        max_tokens=2048,
        messages=[
            {"role": "system", "content": _LLM_SYSTEM},
            {"role": "user", "content": _build_llm_prompt(profile)}
        ],
    )
    return response.choices[0].message.content.strip()


# ── 模板拼接版 ────────────────────────────────────────────────────────────────

def _generate_template_version(profile: StyleProfile) -> str:
    sections: list[str] = []

    # 1. 身份设定
    sections.append(
        "你现在需要完全模仿以下用户的说话风格进行回答。\n"
        "请严格遵守下方的风格描述，不要暴露你是 AI 的身份。\n"
        "模仿风格不能牺牲对话连贯性：必须结合当前上下文回答用户的问题，"
        "不要因为参考例句偏短就机械地只回复几个字；需要解释时可以自然展开到 1-3 句。\n"
    )

    # 2. 风格特征列表
    sections.append("## 风格特征\n")
    sections.append("以下特征按五类风格指标组织：\n")
    for spec in CHARACTERISTICS_SPEC:
        key = spec["key"]
        c: Characteristic | None = profile.get(key)
        if c is None or not c.value or c.value == "（未分析）":
            continue
        conf_tag = "（置信度较低，仅供参考）" if c.confidence < 0.6 else ""
        sections.append(f"**{c.label}**{conf_tag}：{c.value}\n")

    # 3. 参考例句
    sections.append("\n## 参考例句\n")
    sections.append(
        "以下是该用户的真实表达，模仿时参考其语气与句式：\n"
        "（以下例句仅展示说话格式，请只模仿句式结构与语气节奏，不要参考其中的具体内容）\n"
    )
    idx = 1
    for spec in CHARACTERISTICS_SPEC:
        key = spec["key"]
        c = profile.get(key)
        if c is None:
            continue
        for ex in c.examples:
            sections.append(f"{idx}. \u201c{ex}\u201d")
            idx += 1
            if idx > 12:
                break
        if idx > 12:
            break

    # 4. 低置信度说明
    low_keys = profile.low_confidence_keys(0.6)
    if low_keys:
        sections.append("\n## 不确定特征\n")
        sections.append(
            "以下特征分析置信度较低，遇到相关情景时保持风格中立即可：\n"
        )
        for k in low_keys:
            c = profile.get(k)
            if c:
                sections.append(f"- {c.label}")

    return "\n".join(sections)


def build_template_mimicry_prompt(profile: StyleProfile) -> str:
    """生成稳定可复现的模板拼接版风格模仿提示词。"""
    return _generate_template_version(profile)


# ── 公开 API ──────────────────────────────────────────────────────────────────

def build_mimicry_prompt_pair(
    profile: StyleProfile, client: openai.OpenAI
) -> MimicryPromptPair:
    """同时生成 LLM 版和模板拼接版两份提示词。"""
    llm_text = _generate_llm_version(profile, client)
    template_text = _generate_template_version(profile)
    return MimicryPromptPair(
        llm_generated=llm_text,
        template_assembled=template_text,
        profile_snapshot=profile,
        generated_at_version=profile.analysis_version,
    )
