from __future__ import annotations

from pathlib import Path

import pytest

from jianyin_app.config import ModelConfig
from jianyin_app.model.onnx_detector import OnnxPrivacyFilter


@pytest.mark.slow
def test_real_model_detects_english_sample() -> None:
    model_dir = Path(__file__).resolve().parents[1] / "models" / "openai-privacy-filter-q4"
    if not (model_dir / "onnx" / "model_q4.onnx_data").is_file():
        pytest.skip("local Q4 model is not present")
    detector = OnnxPrivacyFilter(ModelConfig(model_dir=str(model_dir)))
    result = detector.detect(
        "Alice Johnson lives in Springfield. Her email is alice.johnson@example.com "
        "and her phone is 555-123-4567."
    )
    categories = {item.category for item in result.detections}
    assert "private_person" in categories
    assert "private_email" in categories or "private_phone" in categories
    assert result.stats["window_count"] >= 1
