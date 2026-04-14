"""
feedback.py
收集用户对特征分析的反馈，并定向调用 LLM 修正指定特征。
"""

from __future__ import annotations

import json
import re

import openai
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich import box

from config import CHARACTERISTICS_SPEC, LABEL_MAP, get_model_name
from models import Characteristic, StyleProfile


# ── 反馈收集 ────────────────────────────────────────────────────────────────

def collect_feedback(
    profile: StyleProfile,
    console: Console,
) -> list[tuple[str, str]]:
    """
    展示当前所有特征，让用户选择哪些不像，并可选填补充说明。
    返回 [(key, user_hint_or_empty), ...]
    """
    console.print()
    console.rule("[bold yellow]风格特征调整[/bold yellow]")

    # 展示特征表格
    table = Table(box=box.SIMPLE_HEAD, show_lines=True)
    table.add_column("编号", style="bold cyan", width=4)
    table.add_column("特征", width=16)
    table.add_column("当前描述", width=40)
    table.add_column("置信度", width=6)

    key_index: dict[str, int] = {}  # key -> 编号（1-based）
    index_key: dict[int, str] = {}  # 编号 -> key

    for i, spec in enumerate(CHARACTERISTICS_SPEC, 1):
        key = spec["key"]
        c = profile.get(key)
        val = c.value if c else "（无数据）"
        conf = f"{c.confidence:.2f}" if c else "-"
        table.add_row(str(i), spec["label"], val, conf)
        key_index[key] = i
        index_key[i] = key

    console.print(table)

    # 让用户输入编号
    console.print("请输入你觉得[bold red]不像[/bold red]的特征编号（用空格分隔），直接回车跳过：")
    raw = Prompt.ask("编号", default="")
    if not raw.strip():
        return []

    # 解析编号
    chosen_indices: list[int] = []
    for tok in raw.strip().split():
        try:
            idx = int(tok)
            if idx in index_key:
                chosen_indices.append(idx)
        except ValueError:
            pass

    if not chosen_indices:
        return []

    # 逐个收集补充说明
    feedback: list[tuple[str, str]] = []
    for idx in chosen_indices:
        key = index_key[idx]
        label = LABEL_MAP[key]
        hint = Prompt.ask(
            f"  [{idx}] {label} — 你觉得更偏向于（直接回车跳过）",
            default="",
        )
        feedback.append((key, hint.strip()))

    return feedback


# ── Refinement Prompt ───────────────────────────────────────────────────────

_REFINE_SYSTEM = """\
你是一位中文语言风格分析师。用户审阅了对其说话风格的分析结果，指出了其中部分特征描述不准确，并给出了主观感受。
你的任务是：重新分析原始聊天记录，只修正用户指出的那几个特征，其余特征保持不变。

修正要求：
1. 只输出需要修正的特征，不要输出其他特征。
2. 必须重新从原文中寻找支撑例句（3~5条，直接引用原文，最多5条）。
3. 用户的主观说明（user_hint）是重要参考，但仍需在原文中找到支撑，不能无依据地照单全收。
4. 如果原文证据不足，如实降低 confidence（低于 0.5）并在 evidence 中说明。
5. 若原来描述为单一模式，但用户提示为混合模式，请重新检查原文是否有混合证据。

输出格式：严格 JSON，只包含需要修正的特征：
{
  "refined_characteristics": {
    "<feature_key>": {
      "value": "<新的整体描述>",
      "examples": ["<原文例句1>", "..."],
      "evidence": "<修正理由>",
      "confidence": <0.0~1.0>
    }
  }
}
"""


def _build_refinement_user_message(
    chat_text: str,
    profile: StyleProfile,
    target_feedback: list[tuple[str, str]],
) -> str:
    lines = [
        "原始聊天记录：\n",
        f"<chat_log>\n{chat_text}\n</chat_log>\n",
        "---",
        "以下特征被用户指出描述不准确，请重新分析：\n",
    ]
    for key, hint in target_feedback:
        c = profile.get(key)
        current_val = c.value if c else "（无数据）"
        label = LABEL_MAP.get(key, key)
        lines.append(f"特征：{label}（key: {key}）")
        lines.append(f"  当前描述：{current_val}")
        if hint:
            lines.append(f"  用户补充说明：更偏向于 {hint}")
        else:
            lines.append("  用户补充说明：（无）")
        lines.append("")

    lines.append(f"请重新分析以上 {len(target_feedback)} 个特征，输出严格 JSON。")
    return "\n".join(lines)


def _extract_json(raw: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


# ── 公开 API ─────────────────────────────────────────────────────────────────

def refine_characteristics(
    chat_text: str,
    profile: StyleProfile,
    target_feedback: list[tuple[str, str]],
    client: openai.OpenAI,
) -> StyleProfile:
    """
    仅对 target_feedback 中指定的特征重新分析，其余特征完全不变。
    返回更新后的 StyleProfile（analysis_version 已自增）。
    """
    if not target_feedback:
        return profile

    user_msg = _build_refinement_user_message(chat_text, profile, target_feedback)
    response = client.chat.completions.create(
        model=get_model_name(),
        max_tokens=2048,
        messages=[
            {"role": "system", "content": _REFINE_SYSTEM},
            {"role": "user", "content": user_msg}
        ],
    )
    data = _extract_json(response.choices[0].message.content)
    refined = data.get("refined_characteristics", {})

    for key, item in refined.items():
        if key not in profile.characteristics:
            continue
        label = LABEL_MAP.get(key, key)
        examples = item.get("examples", [])
        if len(examples) > 5:
            examples = examples[:5]
        updated = Characteristic(
            key=key,
            label=label,
            value=str(item.get("value", "")),
            examples=examples,
            evidence=str(item.get("evidence", "")),
            confidence=float(item.get("confidence", 0.5)),
        )
        profile.update_characteristic(key, updated)

    return profile


# ── 展示调整结果 ──────────────────────────────────────────────────────────────

def display_refined_characteristics(
    profile: StyleProfile,
    updated_keys: list[str],
    console: Console,
) -> None:
    """只展示被修改过的特征。"""
    if not updated_keys:
        return
    console.print()
    console.rule("[bold green]调整后的特征[/bold green]")
    for key in updated_keys:
        c = profile.get(key)
        if c is None:
            continue
        content = (
            f"[bold]{c.label}[/bold]\n"
            f"描述：{c.value}\n"
            f"置信度：{c.confidence:.2f}  |  依据：{c.evidence}\n"
        )
        if c.examples:
            content += "例句：\n" + "\n".join(f'  - "{ex}"' for ex in c.examples)
        console.print(Panel(content, border_style="green"))
