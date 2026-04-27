# 项目文件结构说明

本文档整理当前项目 `mode3_10minstudy` 的目录结构、文件职责和后续维护建议。

## 总览

```text
mode3_10minstudy/
├── main.py
├── config.py
├── analyzer.py
├── prompt_builder.py
├── verifier.py
├── feedback.py
├── models.py
├── requirements.txt
├── README.md
├── docs/
├── tools/
├── tests/
├── transcripts/
├── input_flutter_animation.txt
├── output_flutter_animation.txt
└── moyan_yuhua_first30.wav
```

## 核心程序文件

| 路径 | 作用 |
| --- | --- |
| `main.py` | CLI 入口，串联风格分析、提示词生成、验证和反馈调整流程。 |
| `config.py` | 读取 `.env` 配置，提供模型名称、API Key、风格特征规格和验证问题。 |
| `analyzer.py` | 调用 LLM 分析单一说话人的文本样本，生成 `StyleProfile`。 |
| `prompt_builder.py` | 基于风格画像生成两版风格模仿提示词：LLM 整理版和模板拼接版。 |
| `verifier.py` | 用固定问题验证生成提示词的风格表现，并展示验证结果。 |
| `feedback.py` | 收集用户反馈，按反馈修正低置信度或不满意的风格特征。 |
| `models.py` | 定义项目内的数据结构，包括 `Characteristic`、`RawStats`、`StyleProfile`、`MimicryPromptPair`。 |

## 配置与说明文件

| 路径 | 作用 |
| --- | --- |
| `.env` | 本地运行配置，通常包含 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`MODEL_NAME` 等敏感信息。 |
| `.gitattributes` | Git 属性配置。 |
| `requirements.txt` | Python 依赖：`openai`、`click`、`rich`、`python-dotenv`。 |
| `README.md` | 项目简介和基础使用方式。 |
| `CLAUDE.md` | 当前为空，可用于后续记录 Claude/Codex 相关协作说明。 |

## 文档目录

```text
docs/
├── moyan_yuhua_first30_dataset.md
└── project_structure.md
```

| 路径 | 作用 |
| --- | --- |
| `docs/moyan_yuhua_first30_dataset.md` | 说明“莫言余华：和年轻人谈谈心”前 30 分钟数据在项目中的用法。 |
| `docs/project_structure.md` | 当前文件，即项目结构说明。 |

## 转写与样本数据

`transcripts/` 是当前项目的数据主目录，包含音频、自动转写、中间处理结果、校对结果和推荐输入文件。

```text
transcripts/
├── audio/
├── audit/
├── inputs/
├── outputs/
├── audio_*.json
├── audio_*.txt
├── audio_style_profile.json
├── moyan_yuhua_first30_*.json
├── moyan_yuhua_first30_*.md
├── moyan_yuhua_first30_*.srt
└── style_learning_*.*
```

### 推荐作为 `main.py -i` 输入的文件

```text
transcripts/inputs/
├── input_style_moyan_yuhua_first30_host_lina.txt
├── input_style_moyan_yuhua_first30_moyan.txt
└── input_style_moyan_yuhua_first30_yuhua.txt
```

这些文件已经拆成单一说话人的纯文本样本，适合作为风格学习输入。

### 推荐保留的校对输出

```text
transcripts/outputs/
├── output_moyan_yuhua_first30_by_speaker_corrected.md
├── output_moyan_yuhua_first30_corrected_turns.srt
├── output_moyan_yuhua_first30_speaker_labeled_corrected.md
├── output_style_prompt_moyan.txt
└── output_style_prompt_yuhua.txt
```

这些文件是校对结果或已生成的风格提示词输出，适合归档和复用。

### 回查与审计文件

```text
transcripts/audit/
├── audit_moyan_yuhua_first30_host_lina_timed.txt
├── audit_moyan_yuhua_first30_moyan_timed.txt
└── audit_moyan_yuhua_first30_yuhua_timed.txt
```

这些文件保留时间戳，主要用于回查说话人归属和校对依据。

### 音频文件

```text
transcripts/audio/
├── audio_20260412_1919.wav
├── audio_20260417_1850.wav
└── audio_20260426_1557.wav
```

根目录下还有一个较大的 `moyan_yuhua_first30.wav`，建议后续统一移动到 `transcripts/audio/` 或单独的 `assets/audio/` 目录。

## 工具脚本

```text
tools/
└── correct_moyan_yuhua_transcripts.py
```

该脚本用于重新生成莫言余华访谈的校对文本、推荐命名文件和旧命名兼容文件。

## 测试目录

```text
tests/
└── __pycache__/
```

当前没有实际测试文件，只有 Python 缓存目录。后续可以补充针对 `analyzer.py`、`prompt_builder.py` 和数据解析逻辑的单元测试。

## 根目录样例文件

| 路径 | 作用 |
| --- | --- |
| `input_flutter_animation.txt` | 示例输入文本。 |
| `output_flutter_animation.txt` | 示例输出提示词。 |

这两个文件适合作为最小运行样例；如果样例增多，建议后续迁移到 `examples/`。

## 缓存与本地状态

| 路径 | 说明 |
| --- | --- |
| `.git/` | Git 仓库数据。 |
| `.claude/` | 本地 Claude 配置或状态目录。 |
| `__pycache__/` | Python 运行缓存，可忽略。 |
| `tests/__pycache__/` | Python 测试缓存，可忽略。 |

## 建议的后续整理方向

1. 将根目录音频 `moyan_yuhua_first30.wav` 迁移到 `transcripts/audio/`，减少根目录噪音。
2. 新建 `examples/`，放置 `input_flutter_animation.txt` 和 `output_flutter_animation.txt`。
3. 清理或忽略 `__pycache__/`、`tests/__pycache__/` 等缓存文件。
4. 在 `tests/` 中补充最小单元测试，至少覆盖提示词拼接、数据模型方法和配置读取。
5. 对 `transcripts/` 下旧命名兼容文件建立保留规则，避免推荐文件和旧文件长期混用。
