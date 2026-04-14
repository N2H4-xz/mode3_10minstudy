"""
main.py
CLI 入口。驱动完整的风格分析 → 提示词生成 → 验证 → 反馈调整流程。

用法：
    python main.py -i chat.txt
    python main.py -i chat.txt -o output_prompt.txt --max-loops 3
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
import openai
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich import box

import config as cfg
from analyzer import analyze_chat_log
from feedback import collect_feedback, display_refined_characteristics, refine_characteristics
from models import StyleProfile
from prompt_builder import build_mimicry_prompt_pair
from verifier import ask_user_approval, display_verification_results, run_verification


console = Console()


# ── 展示风格分析结果 ──────────────────────────────────────────────────────────

def display_profile(profile: StyleProfile) -> None:
    console.print()
    console.rule("[bold blue]风格分析结果[/bold blue]")

    stats = profile.raw_stats
    console.print(
        f"[dim]共 {stats.total_messages} 条消息，"
        f"平均每条 {stats.avg_chars_per_message:.1f} 字，"
        f"总计 {stats.total_chars} 字[/dim]"
    )
    console.print()

    from config import CHARACTERISTICS_SPEC
    for spec in CHARACTERISTICS_SPEC:
        key = spec["key"]
        c = profile.get(key)
        if c is None:
            continue
        conf_color = "green" if c.confidence >= 0.7 else ("yellow" if c.confidence >= 0.5 else "red")
        content = (
            f"[bold]{c.label}[/bold]  "
            f"[{conf_color}]置信度 {c.confidence:.2f}[/{conf_color}]\n\n"
            f"{c.value}\n\n"
            f"[dim]依据：{c.evidence}[/dim]"
        )
        if c.examples:
            content += "\n[dim]例句：[/dim]\n" + "\n".join(f'  [dim]- "{ex}"[/dim]' for ex in c.examples)
        console.print(Panel(content, border_style="blue", padding=(0, 1)))


# ── 主流程 ───────────────────────────────────────────────────────────────────

def run_pipeline(
    chat_text: str,
    client: openai.OpenAI,
    max_loops: int,
) -> tuple[str | None, StyleProfile]:
    """
    完整流程。返回 (最终输出文件内容 or None, 最终 StyleProfile)。
    """
    # 阶段 1：分析
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), transient=True) as p:
        p.add_task("正在分析聊天记录风格...", total=None)
        profile = analyze_chat_log(chat_text, client)

    display_profile(profile)

    final_pair = None

    for loop_num in range(1, max_loops + 1):
        console.print()
        if loop_num > 1:
            console.rule(f"[dim]第 {loop_num} 轮迭代[/dim]")

        # 阶段 2：生成提示词
        with Progress(SpinnerColumn(), TextColumn("{task.description}"), transient=True) as p:
            p.add_task("正在生成风格模仿提示词...", total=None)
            prompt_pair = build_mimicry_prompt_pair(profile, client)

        final_pair = prompt_pair

        # 阶段 3：验证
        with Progress(SpinnerColumn(), TextColumn("{task.description}"), transient=True) as p:
            p.add_task("正在用提示词回答验证问题...", total=None)
            results = run_verification(prompt_pair, client)

        display_verification_results(results, console)

        # 阶段 4：用户判断
        approved = ask_user_approval(console)
        if approved:
            console.print("[bold green]太好了！将输出最终提示词。[/bold green]")
            break

        if loop_num == max_loops:
            console.print(f"[yellow]已达最大调整次数（{max_loops}），输出当前版本。[/yellow]")
            break

        # 阶段 5：收集反馈
        target_feedback = collect_feedback(profile, console)
        if not target_feedback:
            console.print("[dim]未指定需要调整的特征，退出迭代。[/dim]")
            break

        # 阶段 6：定向调整
        updated_keys = [k for k, _ in target_feedback]
        with Progress(SpinnerColumn(), TextColumn("{task.description}"), transient=True) as p:
            p.add_task(f"正在重新分析 {len(updated_keys)} 个特征...", total=None)
            profile = refine_characteristics(chat_text, profile, target_feedback, client)

        display_refined_characteristics(profile, updated_keys, console)

    return final_pair, profile


# ── CLI ──────────────────────────────────────────────────────────────────────

@click.command()
@click.option(
    "--input", "-i",
    "input_file",
    required=True,
    type=click.Path(exists=True, readable=True),
    help="聊天记录文件路径（纯文本）",
)
@click.option(
    "--output", "-o",
    "output_file",
    default=None,
    type=click.Path(),
    help="输出提示词文件路径（可选，不指定则只在终端显示）",
)
@click.option(
    "--model",
    default=None,
    help="覆盖 .env 中的模型名称",
)
@click.option(
    "--max-loops",
    default=5,
    show_default=True,
    help="最大迭代轮数",
)
def main(input_file: str, output_file: str | None, model: str | None, max_loops: int) -> None:
    """说话风格学习与提示词生成工具。"""
    # 模型名覆盖
    if model:
        import os
        os.environ["MODEL_NAME"] = model

    # 读取聊天记录
    chat_text = Path(input_file).read_text(encoding="utf-8").strip()
    if not chat_text:
        console.print("[red]错误：聊天记录文件为空。[/red]")
        sys.exit(1)

    console.print(f"[bold]已读取聊天记录[/bold]（{len(chat_text)} 字）")

    # 初始化 Anthropic 客户端
    try:
        api_key = cfg.get_api_key()
        base_url = cfg.get_base_url()
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    client = openai.OpenAI(api_key=api_key, base_url=base_url)

    # 运行主流程
    final_pair, final_profile = run_pipeline(chat_text, client, max_loops)

    if final_pair is None:
        console.print("[red]未生成提示词，程序退出。[/red]")
        sys.exit(1)

    # 终端展示两版提示词
    console.print()
    console.rule("[bold magenta]最终提示词[/bold magenta]")
    console.print(Panel(final_pair.llm_generated, title="[bold]版本 A：LLM 生成[/bold]", border_style="magenta"))
    console.print(Panel(final_pair.template_assembled, title="[bold]版本 B：模板拼接[/bold]", border_style="cyan"))

    # 保存到文件
    if output_file:
        final_pair.save_to_file(output_file)
        console.print(f"\n[green]两版提示词已保存到：{output_file}[/green]")


if __name__ == "__main__":
    main()
