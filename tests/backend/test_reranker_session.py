import sys
from types import SimpleNamespace

from app.config import config
from app.services.reranker_service import RerankerService


def test_flashrank_cpu_session_uses_bounded_threads(tmp_path, monkeypatch):
    model_file = tmp_path / "ranker.onnx"
    model_file.write_bytes(b"test-model-placeholder")
    created = {}

    class SessionOptions:
        def __init__(self):
            self.entries = {}

        def add_session_config_entry(self, key, value):
            self.entries[key] = value

    def inference_session(path, *, sess_options, providers):
        created.update(path=path, options=sess_options, providers=providers)
        return "tuned-session"

    fake_ort = SimpleNamespace(
        SessionOptions=SessionOptions,
        ExecutionMode=SimpleNamespace(ORT_SEQUENTIAL="sequential"),
        GraphOptimizationLevel=SimpleNamespace(ORT_ENABLE_ALL="all"),
        InferenceSession=inference_session,
    )
    monkeypatch.setitem(sys.modules, "onnxruntime", fake_ort)
    monkeypatch.setattr(config, "reranker_intra_op_threads", 99)
    ranker = SimpleNamespace(session="default-session")

    RerankerService._tune_cpu_session(ranker, tmp_path)

    assert ranker.session == "tuned-session"
    assert created["options"].intra_op_num_threads == 16
    assert created["options"].inter_op_num_threads == 1
    assert created["providers"] == ["CPUExecutionProvider"]
    assert created["options"].entries["session.intra_op.spin_backoff_max"] == "8"
