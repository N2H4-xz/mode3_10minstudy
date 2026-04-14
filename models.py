from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Characteristic:
    key: str
    label: str            # 中文标签
    value: str            # LLM 对该特征的整体描述
    examples: list[str]   # 从原文中摘取的例句，最多 5 条
    evidence: str         # 判断依据（一句话）
    confidence: float     # 0.0~1.0，LLM 自评置信度


@dataclass
class RawStats:
    total_messages: int
    avg_chars_per_message: float
    total_chars: int


@dataclass
class StyleProfile:
    characteristics: dict[str, Characteristic]
    raw_stats: RawStats
    source_length_chars: int
    analysis_version: int = 1

    def get(self, key: str) -> Characteristic | None:
        return self.characteristics.get(key)

    def update_characteristic(self, key: str, updated: Characteristic) -> None:
        """精确替换单个特征，analysis_version 自增。"""
        self.characteristics[key] = updated
        self.analysis_version += 1

    def low_confidence_keys(self, threshold: float = 0.6) -> list[str]:
        return [k for k, c in self.characteristics.items() if c.confidence < threshold]


@dataclass
class MimicryPromptPair:
    llm_generated: str       # LLM 整理生成的风格模仿提示词
    template_assembled: str  # 直接由 StyleProfile 数据拼接的提示词
    profile_snapshot: StyleProfile
    generated_at_version: int

    def save_to_file(self, path: str) -> None:
        sep = "=" * 60 + "\n"
        content = (
            sep
            + "【版本 A：LLM 生成提示词】\n"
            + sep + "\n"
            + self.llm_generated
            + "\n\n"
            + sep
            + "【版本 B：模板拼接提示词】\n"
            + sep + "\n"
            + self.template_assembled
            + "\n"
        )
        Path(path).write_text(content, encoding="utf-8")
