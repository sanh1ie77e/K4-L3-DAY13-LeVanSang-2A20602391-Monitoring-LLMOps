from __future__ import annotations

from app.mock_llm import FakeLLM
from app.mock_rag import retrieve
from app import mock_llm


class RecordingGenerationClient:
    def __init__(self) -> None:
        self.updates: list[dict] = []

    def update_current_generation(self, **kwargs) -> None:
        self.updates.append(kwargs)


def test_retrieval_and_generation_are_observed_children() -> None:
    assert hasattr(retrieve, "__wrapped__")
    assert hasattr(FakeLLM.generate, "__wrapped__")


def test_generation_records_model_usage_and_cost_without_raw_io(monkeypatch) -> None:
    client = RecordingGenerationClient()
    monkeypatch.setattr(mock_llm, "get_langfuse_client", lambda: client)

    response = FakeLLM.generate.__wrapped__(FakeLLM(), "safe prompt")

    update = client.updates[-1]
    assert update["model"] == "claude-sonnet-4-5"
    assert update["usage_details"] == {
        "input": response.usage.input_tokens,
        "output": response.usage.output_tokens,
        "total": response.usage.input_tokens + response.usage.output_tokens,
    }
    assert update["cost_details"]["total"] > 0
    assert "input" not in update
    assert "output" not in update
