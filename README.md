# mode3_10minstudy

这是一个中文说话风格学习与提示词生成工具。项目入口是 `main.py`，它读取单一说话人的纯文本样本，分析语言风格，并生成两版风格模仿提示词。

## 基本使用

```powershell
python main.py -i input_flutter_animation.txt -o output_prompt.txt
```

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
