from app.prompts import prompt_registry
from app.agent.semantic_planner import RoutingDecision


def test_prompt_registry_covers_every_agent_stage_and_lock_is_current():
    required = {
        "routing", "rag_answer", "ops_planner", "ops_executor",
        "ops_replanner", "ops_report", "memory_extract", "conversation_summary",
    }
    assert all(prompt_registry.get(prompt_id).content for prompt_id in required)
    assert prompt_registry.validate_lock() == []


def test_prompt_fingerprint_records_all_reproducibility_hashes():
    fingerprint = prompt_registry.fingerprint("routing", output_schema={"type": "object"})
    assert fingerprint["prompt"] == "routing@1.0.0"
    assert all(len(fingerprint[key]) == 64 for key in (
        "content_hash", "tool_catalog_hash", "output_schema_hash", "bundle_hash",
    ))
    assert len(prompt_registry.bundle("routing", "rag_answer")["combination_hash"]) == 64


def test_routing_fingerprint_uses_actual_pydantic_output_schema():
    fingerprint = prompt_registry.fingerprint("routing")
    explicit = prompt_registry.fingerprint(
        "routing", output_schema=RoutingDecision.model_json_schema(),
    )
    assert fingerprint["output_schema_hash"] == explicit["output_schema_hash"]
