# 莫言余华访谈前30分钟数据说明

本文档说明 `莫言余华：和年轻人谈谈心` 前 30 分钟转写数据在本项目里的用法。

## 项目用法

当前项目的入口是 `main.py`，输入必须是一份“单一说话人”的纯文本样本。

不要直接把完整访谈、完整 SRT、或多说话人 Markdown 喂给 `main.py`，否则会把主持人、莫言、余华和现场插话混成一个风格。

推荐命令：

```powershell
python main.py -i transcripts\inputs\input_style_moyan_yuhua_first30_moyan.txt -o output_moyan_prompt.txt
python main.py -i transcripts\inputs\input_style_moyan_yuhua_first30_yuhua.txt -o output_yuhua_prompt.txt
python main.py -i transcripts\inputs\input_style_moyan_yuhua_first30_host_lina.txt -o output_host_lina_prompt.txt
```

## 推荐输入文件

这些文件专门用于 `main.py -i`：

| 文件 | 说明 |
| --- | --- |
| `transcripts/inputs/input_style_moyan_yuhua_first30_moyan.txt` | 莫言单人风格样本 |
| `transcripts/inputs/input_style_moyan_yuhua_first30_yuhua.txt` | 余华单人风格样本 |
| `transcripts/inputs/input_style_moyan_yuhua_first30_host_lina.txt` | 主持人李娜单人风格样本 |

## 推荐输出文件

这些文件是校对后的资料成果，不建议直接作为风格学习输入：

| 文件 | 说明 |
| --- | --- |
| `transcripts/outputs/output_moyan_yuhua_first30_by_speaker_corrected.md` | 按主持人、莫言、余华汇总的校对版 |
| `transcripts/outputs/output_moyan_yuhua_first30_speaker_labeled_corrected.md` | 按时间顺序排列的校对版轮次稿 |
| `transcripts/outputs/output_moyan_yuhua_first30_corrected_turns.srt` | 按说话轮次生成的校对版字幕 |

## 回查文件

这些文件用于核对时间戳和说话人归属：

| 文件 | 说明 |
| --- | --- |
| `transcripts/audit/audit_moyan_yuhua_first30_moyan_timed.txt` | 莫言校对文本，带时间戳 |
| `transcripts/audit/audit_moyan_yuhua_first30_yuhua_timed.txt` | 余华校对文本，带时间戳 |
| `transcripts/audit/audit_moyan_yuhua_first30_host_lina_timed.txt` | 主持人李娜校对文本，带时间戳 |

## 中间文件

以下文件是自动转写、聚类或旧版输出，主要用于追溯处理过程：

| 文件 | 说明 |
| --- | --- |
| `transcripts/moyan_yuhua_first30_whisper.json` | Whisper 原始分段 JSON |
| `transcripts/moyan_yuhua_first30_whisper.txt` | Whisper 原始分段 TXT |
| `transcripts/moyan_yuhua_first30_whisper.srt` | Whisper 原始 SRT |
| `transcripts/moyan_yuhua_first30_clustered.json` | 声学聚类辅助结果 |
| `transcripts/moyan_yuhua_first30_*_input.txt` | 旧命名兼容文件，内容与 `transcripts/inputs/input_*` 对应 |
| `transcripts/moyan_yuhua_first30_*_timed.txt` | 旧命名兼容文件，内容与 `transcripts/audit/audit_*` 对应 |

## 重新生成

校对文本由脚本生成：

```powershell
python tools\correct_moyan_yuhua_transcripts.py
```

脚本会同时生成推荐命名文件和旧命名兼容文件。
