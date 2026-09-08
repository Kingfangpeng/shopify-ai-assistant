"""版本化 Prompt 注册、组合指纹和 CI hash 校验。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.agent.tool_registry import tool_catalog_hash


ROOT = Path(__file__).resolve().parents[2]
PROMPT_DIR = ROOT / "prompts"


@dataclass(frozen=True)
class PromptEntry:
    prompt_id: str
    version: str
    file: str
    content: str
    content_hash: str


class PromptRegistry:
    def __init__(self) -> None:
        manifest = json.loads((PROMPT_DIR / "registry.json").read_text(encoding="utf-8"))
        self._entries: dict[str, PromptEntry] = {}
        for prompt_id, item in manifest["prompts"].items():
            content = (PROMPT_DIR / item["file"]).read_text(encoding="utf-8").strip()
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            self._entries[prompt_id] = PromptEntry(prompt_id, item["version"], item["file"], content, digest)

    def get(self, prompt_id: str) -> PromptEntry:
        try:
            return self._entries[prompt_id]
        except KeyError as exc:
            raise KeyError(f"Prompt 未注册: {prompt_id}") from exc

    def render(self, prompt_id: str, **values: Any) -> str:
        return self.get(prompt_id).content.format(**values)

    def fingerprint(
        self,
        prompt_id: str,
        *,
        output_schema: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        entry = self.get(prompt_id)
        schema_raw = json.dumps(output_schema or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        schema_hash = hashlib.sha256(schema_raw.encode("utf-8")).hexdigest()
        payload = f"{entry.prompt_id}@{entry.version}:{entry.content_hash}:{tool_catalog_hash()}:{schema_hash}"
        return {
            "prompt": f"{entry.prompt_id}@{entry.version}",
            "content_hash": entry.content_hash,
            "tool_catalog_hash": tool_catalog_hash(),
            "output_schema_hash": schema_hash,
            "bundle_hash": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        }

    def bundle(self, *prompt_ids: str) -> dict[str, Any]:
        versions = {prompt_id: self.fingerprint(prompt_id) for prompt_id in prompt_ids}
        raw = json.dumps(versions, sort_keys=True, separators=(",", ":"))
        return {"prompts": versions, "combination_hash": hashlib.sha256(raw.encode()).hexdigest()}

    def validate_lock(self) -> list[str]:
        lock = json.loads((PROMPT_DIR / "registry.lock.json").read_text(encoding="utf-8"))
        errors = []
        expected_keys = {f"{entry.prompt_id}@{entry.version}" for entry in self._entries.values()}
        if set(lock) != expected_keys:
            errors.append("Prompt lock 的条目与 registry 不一致")
        for entry in self._entries.values():
            key = f"{entry.prompt_id}@{entry.version}"
            if lock.get(key) != entry.content_hash:
                errors.append(f"{key} 内容已变化但版本或 lock 未更新")
        return errors


prompt_registry = PromptRegistry()
