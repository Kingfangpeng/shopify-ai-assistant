import json
from pathlib import Path

from scripts.evaluate_rag import ndcg_at_k, reciprocal_rank, summarize


FIXTURES = Path(__file__).parents[1] / "fixtures"


def test_frozen_rag_dataset_has_required_volume_and_generation_subset():
    corpus = [json.loads(line) for line in (FIXTURES / "rag_eval_corpus.jsonl").read_text(encoding="utf-8").splitlines()]
    cases = [json.loads(line) for line in (FIXTURES / "rag_eval_cases.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(corpus) == 100
    assert len(cases) == 500
    assert sum(bool(row["generation_eval"]) for row in cases) == 120
    assert len({row["id"] for row in cases}) == 500
    assert {row["user_id"] for row in corpus} == {"eval-user-a", "eval-user-b"}


def test_rag_metrics_measure_rank_and_permission_leakage():
    assert reciprocal_rank(["x", "gold"], {"gold"}) == 0.5
    assert ndcg_at_k(["gold"], {"gold"}) == 1
    summary = summarize([
        {"answerable": True, "recall_at_5": 1.0, "reciprocal_rank": 1.0, "ndcg_at_10": 1.0,
         "permission_leakage": 0.0, "latency_ms": 10},
        {"answerable": False, "recall_at_5": 0.0, "reciprocal_rank": 0.0, "ndcg_at_10": 1.0,
         "permission_leakage": 1.0, "latency_ms": 20},
    ])
    assert summary["recall_at_5"] == 1
    assert summary["permission_leakage_rate"] == 0.5
