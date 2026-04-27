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
# LLM 在分析时必须输出以下五类风格指标，中文标签用于展示。
CHARACTERISTICS_SPEC: list[dict] = [
    {
        "key": "lexical_complexity",
        "label": "词汇复杂度",
        "metrics": "平均词长、type-token ratio、高级词汇使用情况",
    },
    {
        "key": "syntactic_complexity",
        "label": "句法复杂度",
        "metrics": "平均句子长度、从句出现频率、词性分布",
    },
    {
        "key": "formality_indices",
        "label": "形式化指数",
        "metrics": "代词比例、功能词比例、正式表达与口语表达占比",
    },
    {
        "key": "emotiveness",
        "label": "情感表达度",
        "metrics": "感叹号、表情符号、强化词或情感词汇的使用频率",
    },
    {
        "key": "interpersonal_markers",
        "label": "人际交往标记",
        "metrics": "礼貌策略、免责声明、模糊语以及表达立场或礼貌程度的委婉语",
    },
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
