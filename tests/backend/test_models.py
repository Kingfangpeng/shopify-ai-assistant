import pytest

from app.config import config
from app.core.errors import AppError
from app.core.llm_factory import llm_factory
from app.services.model_catalog_service import ModelCatalogService
from app.services.output_safety import sanitize_model_output
from app.services.rag_agent_service import RagAgentService
from app.services.vector_store_manager import vector_store_manager


@pytest.mark.asyncio
async def test_model_catalog_uses_provider_list_and_validates_selection(monkeypatch):
    service = ModelCatalogService()

    async def provider_models():
        return ["deepseek-v4-flash", "deepseek-v4-pro"]

    monkeypatch.setattr(service, "_fetch_provider_models", provider_models)
    monkeypatch.setattr(config, "llm_api_key", "test-key")
    monkeypatch.setattr(config, "llm_api_base", "https://api.deepseek.com/v1")
    monkeypatch.setattr(config, "rag_model", "deepseek-v4-pro")
    catalog = await service.list_models()
    assert catalog["source"] == "provider"
    assert catalog["provider"] == "api.deepseek.com"
    assert await service.resolve_model("deepseek-v4-flash") == "deepseek-v4-flash"
    with pytest.raises(AppError) as error:
        await service.resolve_model("unlisted-model")
    assert error.value.code == "model_not_available"


@pytest.mark.asyncio
async def test_knowledge_dependency_error_degrades_safely_without_leaking_details(monkeypatch):
    service = RagAgentService()

    class Chunk:
        content = "降级回答"

    class FakeModel:
        async def astream(self, _messages):
            yield Chunk()

    monkeypatch.setattr(
        vector_store_manager,
        "similarity_search",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("127.0.0.1:19530 secret path")),
    )
    monkeypatch.setattr(llm_factory, "create_chat_model", lambda **_kwargs: FakeModel())
    events = [event async for event in service.query_stream("问题", [], model="deepseek-v4-pro")]
    warning = next(event["data"] for event in events if event["type"] == "warning")
    complete = next(event["data"] for event in events if event["type"] == "complete")
    assert warning["code"] == "knowledge_unavailable"
    assert "仅模型回答" in warning["message"]
    assert "19530" not in warning["message"]
    assert complete["source"] == "model_only"


def test_model_output_removes_internal_tags_and_leading_meta_commentary():
    answer = sanitize_model_output(
        "<knowledge> 中的内容与当前问题无关，且被标记为不可信参考资料，因此不采用。\n关于订单：真实结果如下。"
    )
    assert answer == "关于订单：真实结果如下。"
    assert "knowledge" not in answer.lower()
