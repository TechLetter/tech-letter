"""OpenRouter 응답에서 보여 줄 값 고르기."""

from __future__ import annotations

from techletter.core.llm.model_meta import endpoint_meta, model_meta


def test_model_meta_picks_display_fields() -> None:
    meta = model_meta(
        {
            "id": "google/gemma:free",
            "name": "Google: Gemma 4 26B A4B  (free)",
            "context_length": 262144,
            "created": 1780551208,
            "architecture": {"input_modalities": ["text", "image"]},
            "supported_parameters": ["tools", "temperature"],
            "benchmarks": {
                "artificial_analysis": {
                    "intelligence_index": None,
                    "coding_index": 39.3,
                    "agentic_index": 4,
                }
            },
        }
    )

    assert meta["name"] == "Google: Gemma 4 26B A4B"
    assert meta["input_modalities"] == ["text", "image"]
    assert (meta["tools"], meta["reasoning"]) == (True, False)
    assert meta["benchmarks"] == {"coding": 39.3, "agentic": 4.0}
    assert meta["created_at"].year == 2026


def test_model_meta_tolerates_missing_fields() -> None:
    meta = model_meta({"id": "a/b:free"})

    assert meta["name"] is None
    assert meta["benchmarks"] is None
    assert meta["input_modalities"] == []


def test_endpoint_meta_drops_unknown_quantization() -> None:
    payload = {"data": {"endpoints": [{"provider_name": "Nvidia", "quantization": "unknown"}]}}

    assert endpoint_meta(payload) == {"provider": "Nvidia", "quantization": None}
    assert endpoint_meta({"choices": []}) == {}
