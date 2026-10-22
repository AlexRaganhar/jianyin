from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from jianyin_app.config import ModelConfig
from jianyin_app.errors import ModelInferenceError, OperationCancelled
from jianyin_app.model import onnx_detector
from jianyin_app.model.onnx_detector import OnnxPrivacyFilter


class Encoded:
    def __init__(self, text: str) -> None:
        self.ids = [100 + index for index in range(len(text))]
        self.offsets = [(index, index + 1) for index in range(len(text))]


class FakeTokenizer:
    def encode(self, text: str, *, add_special_tokens: bool) -> Encoded:
        assert add_special_tokens is False
        return Encoded(text)


class FakeInput:
    def __init__(self, name: str, value_type: str) -> None:
        self.name = name
        self.type = value_type


class FakeOutput:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeSession:
    def __init__(self) -> None:
        self.inputs: dict[str, np.ndarray] | None = None

    @staticmethod
    def get_inputs() -> list[FakeInput]:
        return [
            FakeInput("input_ids", "tensor(int64)"),
            FakeInput("attention_mask", "tensor(int64)"),
        ]

    @staticmethod
    def get_outputs() -> list[FakeOutput]:
        return [FakeOutput("logits")]

    def run(self, output_names: list[str], inputs: dict[str, np.ndarray]) -> list[np.ndarray]:
        self.inputs = inputs
        token_count = int(inputs["input_ids"].shape[1])
        logits = np.full((1, token_count, 5), -20.0, dtype=np.float32)
        if token_count == 1:
            labels = [4]
        else:
            labels = [1] + [2] * max(token_count - 2, 0) + [3]
        for index, label in enumerate(labels[:token_count]):
            logits[0, index, label] = 20.0
        return [logits]


def _write_model_directory(root: Path) -> None:
    (root / "onnx").mkdir(parents=True)
    (root / "config.json").write_text(
        json.dumps(
            {
                "id2label": {
                    "0": "O",
                    "1": "B-private_person",
                    "2": "I-private_person",
                    "3": "E-private_person",
                    "4": "S-private_person",
                }
            }
        ),
        encoding="utf-8",
    )
    (root / "tokenizer.json").write_text("{}", encoding="utf-8")
    (root / "viterbi_calibration.json").write_text(
        json.dumps(
            {
                "operating_points": {
                    "default": {
                        "biases": {
                            "transition_bias_background_stay": 0.0,
                            "transition_bias_background_to_start": 0.0,
                            "transition_bias_inside_to_continue": 0.0,
                            "transition_bias_inside_to_end": 0.0,
                            "transition_bias_end_to_background": 0.0,
                            "transition_bias_end_to_start": 0.0,
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (root / "onnx" / "model_q4.onnx").write_bytes(b"fake")
    (root / "onnx" / "model_q4.onnx_data").write_bytes(b"fake")


def test_detector_uses_window_logits_and_restores_offsets(monkeypatch, tmp_path) -> None:
    _write_model_directory(tmp_path)
    monkeypatch.setattr(onnx_detector, "ensure_model", lambda *args, **kwargs: tmp_path)
    session = FakeSession()
    detector = OnnxPrivacyFilter(
        ModelConfig(model_dir=str(tmp_path)),
        session_factory=lambda _path: session,
        tokenizer_factory=lambda _path: FakeTokenizer(),
    )
    result = detector.detect("Alice")
    assert len(result.detections) == 1
    assert result.detections[0].category == "private_person"
    assert result.detections[0].text == "Alice"
    assert result.detections[0].start == 0
    assert result.detections[0].end == 5
    assert result.stats["window_count"] == 1
    assert session.inputs is not None
    assert session.inputs["input_ids"].dtype == np.int64


def test_detector_trims_trailing_punctuation(monkeypatch, tmp_path) -> None:
    _write_model_directory(tmp_path)
    monkeypatch.setattr(onnx_detector, "ensure_model", lambda *args, **kwargs: tmp_path)
    detector = OnnxPrivacyFilter(
        ModelConfig(model_dir=str(tmp_path)),
        session_factory=lambda _path: FakeSession(),
        tokenizer_factory=lambda _path: FakeTokenizer(),
    )
    result = detector.detect("Alice.")
    assert result.detections[0].text == "Alice"


def test_detector_splits_long_documents_into_windows(monkeypatch, tmp_path) -> None:
    _write_model_directory(tmp_path)
    monkeypatch.setattr(onnx_detector, "ensure_model", lambda *args, **kwargs: tmp_path)
    detector = OnnxPrivacyFilter(
        ModelConfig(model_dir=str(tmp_path), window_size=512, overlap_tokens=128),
        session_factory=lambda _path: FakeSession(),
        tokenizer_factory=lambda _path: FakeTokenizer(),
    )
    text = "Alice" * 120
    result = detector.detect(text)
    assert result.stats["window_count"] > 1
    assert result.stats["token_count"] == 600


def test_detector_rejects_missing_inputs(monkeypatch, tmp_path) -> None:
    _write_model_directory(tmp_path)
    monkeypatch.setattr(onnx_detector, "ensure_model", lambda *args, **kwargs: tmp_path)

    class BadSession(FakeSession):
        @staticmethod
        def get_inputs() -> list[FakeInput]:
            return [FakeInput("input_ids", "tensor(int64)")]

    detector = OnnxPrivacyFilter(
        ModelConfig(model_dir=str(tmp_path)),
        session_factory=lambda _path: BadSession(),
        tokenizer_factory=lambda _path: FakeTokenizer(),
    )
    with pytest.raises(ModelInferenceError):
        detector.detect("Alice")


def test_detector_propagates_cancellation() -> None:
    detector = OnnxPrivacyFilter(ModelConfig())
    with pytest.raises(OperationCancelled):
        detector.detect("Alice", cancel=lambda: True)

