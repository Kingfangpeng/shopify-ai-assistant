import hashlib
import json
from pathlib import Path

from scripts.generate_production_routing_cases import (
    ROUTES,
    SHOPIFY_TOOLS,
    build_suite,
    payload_bytes,
)


EVALUATION_DIR = Path(__file__).parents[1] / "fixtures" / "evaluation"


def test_generated_suite_has_required_scale_and_coverage():
    suite, manifest = build_suite()
    rows = [row for cases in suite.values() for row in cases]
    assert {name: len(cases) for name, cases in suite.items()} == {
        "core_gold.json": 300,
        "paraphrase_noise.json": 500,
        "multiturn_context.json": 250,
        "mixed_rag_shopify.json": 200,
        "safety_boundary.json": 250,
    }
    assert len(rows) == 1500
    assert len({row["id"] for row in rows}) == 1500
    assert len({row["question"] for row in rows}) == 1500
    assert {row["expected_route"] for row in rows} == ROUTES
    assert {tool for row in rows for tool in row["expected_tools"]} == set(SHOPIFY_TOOLS)
    assert manifest["total_cases"] == 1500


def test_checked_in_suite_matches_deterministic_generator():
    suite, manifest = build_suite()
    expected = {name: payload_bytes(rows) for name, rows in suite.items()}
    expected["manifest.json"] = payload_bytes(manifest)
    for name, content in expected.items():
        assert (EVALUATION_DIR / name).read_bytes() == content


def test_manifest_hashes_match_each_dataset_file():
    manifest = json.loads((EVALUATION_DIR / "manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        content = (EVALUATION_DIR / entry["path"]).read_bytes()
        assert hashlib.sha256(content).hexdigest() == entry["sha256"]
