"""B 站视频文稿 → 教科书式学习笔记（LLM 重构，非压缩摘要）。

格式基准见仓库根目录《你管这破玩意叫网络__BV号_笔记.md》：
中文序号章节 + 问题式标题，每章走「难题 → 方案 → 遗留问题」循环，
结构化信息配代码块/表格/ASCII 图，抽象规则落具体数字例子。
"""

from __future__ import annotations

from typing import Any, Callable

from app.services.llm_client import chat_completion

NOTES_PROMPT = """你是专业的技术视频编辑。下面是一段 B 站视频的完整转写稿，请把它**重构**成一份可独立阅读的学习笔记——读者没看过视频，也能仅凭这份笔记学会视频讲的内容。

## 硬性格式要求
1. 输出纯 Markdown 正文：一级标题 + 一段两三句的导语（概括整篇的主线），随后分章展开；章节之间用 `---` 分隔。
2. 二级标题用中文序号（一、二、三……）并采用**问题式标题**（如「电脑多了怎么办？」），沿用视频推进时抛出的问题；三级标题用 1.1、1.2 编号。
3. 每一章遵循同一叙事循环：**难题/缺陷 → 解决方案 → 关键细节 → 遗留问题**。上一章的「遗留问题」自然钩出下一章，保留视频"问题逼出方案"的推进感。
4. 结构化信息必须用对应形式呈现：
   - 表结构、配置示例、判断伪代码 → 代码块；
   - 拓扑、流程等空间关系 → ASCII 示意图；
   - 可枚举的对照（多个设备的运算结果、多张表的对比等）→ Markdown 表格；
   - 全篇最重要的 2~4 个核心要点 → 引用块（>）。
5. 抽象规则必须落到具体数字例子：视频里给过的例子照实还原；没给的可以自拟一组自洽的最小例子。
6. 关键术语首次出现时**加粗**，并在括号里给出英文或别名。
7. 保留视频的口语记忆锚点：口号、顺口溜、有代表性的玩笑，用引用块收录并标注（如 > 弹幕：……）。

## 内容要求
- 覆盖转写稿的全部知识要点，不得整块省略章节；允许合并口误、重复和口水话。
- 补充仅限于：通用领域的标准术语名（如英文原名）、为完整例子自拟的具体数字。**不得虚构视频没有讲的知识、案例或立场**。
- 结尾提炼一个对仗式的核心洞见（类似「铁打的 IP，流水的 MAC」），并用一两句话解释两端的分工。
- 不要输出"以下是笔记"之类的开场白，不要复述视频链接、UP主等元信息，直接给正文。

## 视频信息
- 标题：{title}
- UP主：{uploader}
- 章节分P：
{chapters}
- 简介：{description}

## 转写稿
{transcript}
"""


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        newline = text.find("\n")
        text = text[newline + 1:] if newline != -1 else text
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip()


async def generate_video_notes(
    video_payload: dict,
    config: Any = None,
    update_step: Callable[[str], None] | None = None,
) -> str:
    transcript = str(video_payload.get("transcript_text") or "").strip()
    if not transcript:
        raise RuntimeError("没有可用文稿，无法生成笔记。")
    step = update_step or (lambda message: None)
    step(f"文稿 {len(transcript)} 字，正在生成学习笔记...")

    prompt = NOTES_PROMPT.format(
        title=str(video_payload.get("title") or "未知").strip(),
        uploader=str(video_payload.get("uploader") or "").strip() or "未提供",
        chapters=str(video_payload.get("chapter_info") or "").strip() or "（未提供）",
        description=str(video_payload.get("description") or "").strip() or "（未提供）",
        transcript=transcript,
    )
    raw = await chat_completion(
        [
            {"role": "system", "content": "你是一名严谨的中文技术视频编辑，擅长把口播转写稿重构为结构清晰、可独立阅读的学习笔记。"},
            {"role": "user", "content": prompt},
        ],
        config,
    )
    notes = _strip_code_fence(raw)
    if not notes:
        raise RuntimeError("模型返回了空笔记。")
    return notes
