# mode3_10minstudy

这是一个中文说话风格学习与提示词生成工具。项目入口是 `main.py`，它读取单一说话人的纯文本样本，分析语言风格，并生成两版风格模仿提示词。

## 基本使用

```powershell
python main.py -i input_flutter_animation.txt -o output_prompt.txt
```

## Web 实验页面

项目也提供 FastAPI 单页 Web 应用，用于完成“语料采集 → 主动设定风格对话 → 学习风格对话 → 十分制评分”的完整实验流程。
页面支持输入用户名切换本地用户，并可为当前用户导入已经学习好的风格画像 JSON；新建实验时会自动使用该用户的当前风格画像。

```powershell
uvicorn web_app:app --reload --host 127.0.0.1 --port 8000
```

启动后打开：

```text
http://127.0.0.1:8000
```

评分提交后，实验记录会保存为 Markdown 和 JSON 到 `transcripts/web_sessions/`。
本地用户画像保存到 `transcripts/users/`，默认不提交到 Git。

## 访谈数据

`莫言余华：和年轻人谈谈心` 前 30 分钟数据已经整理为专门的输入/输出命名。

项目输入文件在：

```text
transcripts/inputs/
```

校对成果文件在：

```text
transcripts/outputs/
```

详细说明见：

```text
docs/moyan_yuhua_first30_dataset.md
```
