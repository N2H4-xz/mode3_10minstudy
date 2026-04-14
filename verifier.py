"""
verifier.py
用生成的提示词回答固定验证问题，展示给用户，收集是否满意。
"""

from __future__ import annotations

import openai
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table
from rich import box

from config import VERIFICATION_QUESTIONS, get_model_name
from models import MimicryPromptPair


# ── 回答生成 ────────────────────────────────────────────────────────────────

def _answer_questions(
    system_prompt: str,
    client: openai.OpenAI,
) -> list[tuple[str, str]]:
    """用给定 system_prompt 依次回答所有固定验证问题，返回 [(question, answer), ...]。"""
    results = []
    for question in VERIFICATION_QUESTIONS:
        response = client.chat.completions.create(
            model=get_model_name(),
            max_tokens=512,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ],
        )
        answer = response.choices[0].message.content.strip()
        results.append((question, answer))
    return results


def run_verification(
    prompt_pair: MimicryPromptPair,
    client: openai.OpenAI,
) -> dict[str, list[tuple[str, str]]]:
    """
    对 llm_generated 和 template_assembled 两个 prompt 各回答固定问题。
    返回 {"llm": [...], "template": [...]}
    """
    llm_qa = _answer_questions(prompt_pair.llm_generated, client)
    tmpl_qa = _answer_questions(prompt_pair.template_assembled, client)
    return {"llm": llm_qa, "template": tmpl_qa}


# ── 展示 ────────────────────────────────────────────────────────────────────

def display_verification_results(
    results: dict[str, list[tuple[str, str]]],
    console: Console,
) -> None:
    """分段展示两版验证问答。"""
    for version_key, label in [("llm", "版本 A：LLM 生成提示词"), ("template", "版本 B：模板拼接提示词")]:
        qa_pairs = results.get(version_key, [])
        console.print()
        console.rule(f"[bold cyan]{label}[/bold cyan]")
        for i, (q, a) in enumerate(qa_pairs, 1):
            table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
            table.add_column("角色", style="bold", width=4)
            table.add_column("内容")
            table.add_row("问", f"[yellow]{q}[/yellow]")
            table.add_row("答", a)
            console.print(Panel(table, title=f"[dim]Q{i}[/dim]", border_style="dim"))


# ── 用户判断 ────────────────────────────────────────────────────────────────

def ask_user_approval(console: Console) -> bool:
    """询问用户两版回答是否像其说话风格，返回 True 表示满意。"""
    console.print()
    console.print("[bold]请查看以上两版回答。[/bold]")
    return Confirm.ask("这些回答像你平时说话的方式吗？", default=False)
