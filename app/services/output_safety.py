"""清理模型回答中的内部提示标记和无意义元话术。"""

from __future__ import annotations

import re


_INTERNAL_TAG_RE = re.compile(
    r"</?(?:knowledge|untrusted_knowledge|shopify_tool_results)(?:\s[^>]*)?>",
    re.IGNORECASE,
)
_LEADING_KNOWLEDGE_META_RE = re.compile(
    r"^\s*(?:中的内容|知识库(?:中的)?内容|参考资料(?:中的)?内容).{0,240}?"
    r"(?:与当前问题无关|不相关|不采用|未采用|不使用).{0,80}?[。.!]\s*",
    re.IGNORECASE | re.DOTALL,
)


def sanitize_model_output(value: object, limit: int = 50_000) -> str:
    text = str(value or "")[:limit]
    text = "".join(char for char in text if char in "\n\t" or ord(char) >= 32)
    text = _INTERNAL_TAG_RE.sub("", text)
    text = _LEADING_KNOWLEDGE_META_RE.sub("", text)
    return text.strip()
