"""排练驱动:一个**不联网、不调模型**的确定性 `LlmDriver`。

它存在的理由只有一个:让整条流水线(权限过滤 → 选材 → 作答 → 出处核验 →
弃答 → 转人工 → 记录)可以在没有 API key、没有网络的情况下被完整演示和验收。

它**不是模型,也不冒充模型** —— 它靠字符二元组重合度挑文档、靠逐字抄原文行
来造回答。回答质量当然远不如真模型,但**系统行为**(尤其是保密边界和出处核验)
和接真模型时一模一样。真实调用见 `llm.AnthropicDriver`。

顺带它还证明了驱动 seam 是真的:两个形态完全不同的 adapter 都只认
"prompt 进、文本出"这一个接口。
"""

from __future__ import annotations

import json
import re

from .notices import bigrams

_CATALOG_LINE = re.compile(r"^- 编号:(?P<id>.+?) \| 标题:(?P<title>.+?) \| 品类:(?P<category>.+?) \| 生效日期:(?P<date>.+?) \| 摘要:(?P<summary>.*)$")
_DOC_HEADER = re.compile(r"^=== 编号:(?P<id>.+?) \| 标题:.+? \| 品类:.+? \| 生效日期:.+? ===$")
_MAX_PICKS = 3


class RehearsalDriver:
    """离线排练用的确定性驱动。"""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        question = _question_of(prompt)
        if "JSON 数组" in prompt:
            return json.dumps(_select_documents(question, prompt), ensure_ascii=False)
        return _compose_answer(question, prompt)


def _question_of(prompt: str) -> str:
    for line in prompt.splitlines():
        if line.startswith("问题:"):
            return line[len("问题:") :].strip()
    return ""


def _select_documents(question: str, prompt: str) -> list[str]:
    grams = bigrams(question)
    scored: list[tuple[int, str]] = []
    for line in prompt.splitlines():
        match = _CATALOG_LINE.match(line.strip())
        if not match:
            continue
        haystack = f"{match['title']}{match['category']}{match['summary']}"
        score = len(grams & bigrams(haystack))
        if score:
            scored.append((score, match["id"]))
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    return [doc_id for _, doc_id in scored[:_MAX_PICKS]]


def _split_documents(prompt: str) -> dict[str, list[str]]:
    """把作答 prompt 拆回 {文档编号: 正文行}。"""
    documents: dict[str, list[str]] = {}
    current = None
    for line in prompt.splitlines():
        header = _DOC_HEADER.match(line.strip())
        if header:
            current = header["id"]
            documents[current] = []
            continue
        if current is not None and line.strip():
            documents[current].append(line.strip())
    return documents


def _weights(all_lines: list[str]) -> dict[str, float]:
    """罕见的二元组更值钱。

    「品类」「供应商」这种词到处都是,区分不出哪一行是答案;「账期」「ECT」
    只出现在一两行里,命中它才说明找对了地方。这是最土的 IDF,但足够让排练
    模式挑出的行像回事。
    """
    document_frequency: dict[str, int] = {}
    for line in all_lines:
        for gram in bigrams(line):
            document_frequency[gram] = document_frequency.get(gram, 0) + 1
    return {gram: 1.0 / count for gram, count in document_frequency.items()}


def _compose_answer(question: str, prompt: str) -> str:
    grams = bigrams(question)
    documents = _split_documents(prompt)
    weights = _weights([line for lines in documents.values() for line in lines])
    best_score, best_id, best_lines = 0.0, "", []

    for doc_id, lines in documents.items():
        # 跳过第一行:那几乎总是标题,而标题已经在知识目录里出现过了,
        # 拿它当答案等于把问题原样念一遍。
        for index, line in enumerate(lines):
            if index == 0:
                continue
            score = sum(weights.get(gram, 0.0) for gram in grams & bigrams(line))
            if score > best_score:
                # 连着往后多抄两行 —— 命中的往往是标题或表头,答案在紧随其后的行里。
                # 行与行之间没有跳过任何内容,所以整块仍然是原文的逐字子串。
                best_score, best_id, best_lines = score, doc_id, lines[index : index + 3]

    best_line = "\n".join(best_lines)

    if not best_score:
        return json.dumps(
            {
                "answered": False,
                "answer": "",
                "citations": [],
                "reason": "给到的文档里没有与问题相关的内容",
            },
            ensure_ascii=False,
        )

    return json.dumps(
        {
            "answered": True,
            "answer": f"根据库里的文档:{best_line}",
            "citations": [{"document_id": best_id, "quote": best_line}],
            "reason": "",
        },
        ensure_ascii=False,
    )
