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
_INTERNAL_TAG_OPENINGS = tuple(
    prefix
    for name in ("knowledge", "untrusted_knowledge", "shopify_tool_results")
    for prefix in (f"<{name}", f"</{name}")
)
_LEADING_META_PREFIXES = (
    "中的内容",
    "知识库内容",
    "知识库中的内容",
    "参考资料内容",
    "参考资料中的内容",
)
_LEADING_META_BUFFER_LIMIT = 400


def _possible_internal_tag_fragment(value: str) -> bool:
    """判断结尾是否可能是被模型分片拆开的内部标签。"""
    lowered = value.casefold()
    if not lowered.startswith("<") or ">" in lowered:
        return False
    for opening in _INTERNAL_TAG_OPENINGS:
        if opening.startswith(lowered):
            return True
        if lowered.startswith(opening):
            suffix = lowered[len(opening):]
            return not suffix or suffix[0].isspace()
    return False


def sanitize_model_output(value: object, limit: int = 50_000) -> str:
    text = str(value or "")[:limit]
    text = "".join(char for char in text if char in "\n\t" or ord(char) >= 32)
    text = _INTERNAL_TAG_RE.sub("", text)
    last_open = text.rfind("<")
    if last_open >= 0 and _possible_internal_tag_fragment(text[last_open:]):
        text = text[:last_open]
    text = _LEADING_KNOWLEDGE_META_RE.sub("", text)
    return text.strip()


class StreamingOutputSanitizer:
    """在不泄漏拆分内部标签的前提下，尽早释放模型文本。"""

    def __init__(self, limit: int = 50_000) -> None:
        self.limit = limit
        self._received = 0
        self._tag_pending = ""
        self._prefix_pending = ""
        self._prefix_resolved = False
        self._started = False
        self._trailing_whitespace = ""

    def feed(self, value: object) -> str:
        if self._received >= self.limit:
            return ""
        raw = str(value or "")
        remaining = self.limit - self._received
        raw = raw[:remaining]
        self._received += len(raw)
        clean = "".join(char for char in raw if char in "\n\t" or ord(char) >= 32)
        return self._feed_prefix(self._remove_tags(clean), final=False)

    def finish(self) -> str:
        pending = self._tag_pending
        self._tag_pending = ""
        if _possible_internal_tag_fragment(pending):
            pending = ""
        else:
            pending = _INTERNAL_TAG_RE.sub("", pending)
        return self._feed_prefix(pending, final=True)

    def _remove_tags(self, text: str) -> str:
        self._tag_pending += text
        output: list[str] = []
        while self._tag_pending:
            match = _INTERNAL_TAG_RE.search(self._tag_pending)
            if match:
                output.append(self._tag_pending[:match.start()])
                self._tag_pending = self._tag_pending[match.end():]
                continue
            last_open = self._tag_pending.rfind("<")
            if last_open >= 0 and _possible_internal_tag_fragment(self._tag_pending[last_open:]):
                output.append(self._tag_pending[:last_open])
                self._tag_pending = self._tag_pending[last_open:]
            else:
                output.append(self._tag_pending)
                self._tag_pending = ""
            break
        return "".join(output)

    def _feed_prefix(self, text: str, *, final: bool) -> str:
        if self._prefix_resolved:
            return self._trim_stream(text, final=final)

        self._prefix_pending += text
        stripped = self._prefix_pending.lstrip()
        if not final:
            if not stripped:
                return ""
            if any(prefix.startswith(stripped) for prefix in _LEADING_META_PREFIXES):
                return ""
            if any(stripped.startswith(prefix) for prefix in _LEADING_META_PREFIXES):
                cleaned = _LEADING_KNOWLEDGE_META_RE.sub("", self._prefix_pending)
                if cleaned == self._prefix_pending and len(self._prefix_pending) < _LEADING_META_BUFFER_LIMIT:
                    return ""
                self._prefix_pending = cleaned

        content = sanitize_model_output(self._prefix_pending)
        self._prefix_pending = ""
        self._prefix_resolved = True
        return self._trim_stream(content, final=final)

    def _trim_stream(self, text: str, *, final: bool) -> str:
        content = self._trailing_whitespace + text
        self._trailing_whitespace = ""
        if not self._started:
            content = content.lstrip()
        if not content:
            return ""
        if final:
            content = content.rstrip()
            if content:
                self._started = True
            return content
        last_nonspace = len(content.rstrip())
        if last_nonspace == 0:
            self._trailing_whitespace = content
            return ""
        output = content[:last_nonspace]
        self._trailing_whitespace = content[last_nonspace:]
        self._started = True
        return output
