import os
from pathlib import Path
from dotenv import load_dotenv

# 加载项目根目录的 .env 文件
_env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=_env_path)


def get_api_key() -> str:
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        raise ValueError("未找到 OPENAI_API_KEY，请在 .env 文件中配置。")
    return key


def get_base_url() -> str | None:
    return os.getenv("OPENAI_BASE_URL")


def get_model_name() -> str:
    return os.getenv("MODEL_NAME", "gpt-4o")


# ── 特征规格表 ──────────────────────────────────────────────────────────────
# LLM 在分析时必须输出以下 key，中文标签用于展示
CHARACTERISTICS_SPEC: list[dict] = [
    {"key": "sentence_length",         "label": "句子长度模式"},
    {"key": "punctuation_style",       "label": "标点与情绪表达"},
    {"key": "formality_level",         "label": "正式程度"},
    {"key": "logical_connectors",      "label": "逻辑连接词使用"},
    {"key": "response_completeness",   "label": "回答详略程度"},
    {"key": "topic_transition",        "label": "话题转换方式"},
    {"key": "message_structure",       "label": "消息结构（单行/多行）"},
    {"key": "opener_closer_phrases",   "label": "惯用开头/结尾语"},
    {"key": "question_usage",          "label": "疑问句使用习惯"},
    {"key": "vocabulary_characteristics", "label": "词汇特点"},
    {"key": "avg_word_length",         "label": "平均词长"},
    {"key": "type_token_ratio",        "label": "Type-token ratio"},
    {"key": "avg_sentence_length",     "label": "平均句长"},
    {"key": "clause_frequency",        "label": "从句频率"},
    {"key": "pos_distribution",        "label": "词性分布"},
    {"key": "pronoun_ratio",           "label": "代词比例"},
    {"key": "article_ratio",           "label": "冠词比例"},
    {"key": "function_word_ratio",     "label": "功能词比例"},
    {"key": "emotion_word_frequency",  "label": "情绪词频率"},
]

# key → label 快查
LABEL_MAP: dict[str, str] = {s["key"]: s["label"] for s in CHARACTERISTICS_SPEC}

# ── 固定验证问题 ────────────────────────────────────────────────────────────
VERIFICATION_QUESTIONS: list[str] = [
    "你今天怎么样？",
    "你觉得这个项目有什么问题吗？",
    "你平时喜欢做什么？",
    "遇到困难你一般怎么处理？",
    "你最近在关注什么？",
]
