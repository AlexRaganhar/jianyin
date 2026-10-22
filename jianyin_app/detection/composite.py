"""Combine the ONNX model with optional Chinese rule detection."""

from __future__ import annotations

from typing import Any

from ..config import DetectionOptions
from .base import (
    CancelCheck,
    DetectionBatch,
    Detector,
    ProgressCallback,
    check_cancelled,
)
from .merge import merge_batches


class CompositeDetector:
    """Run the enabled detectors and return one canonical batch."""

    def __init__(
        self,
        model: Detector | None,
        chinese: Detector | None,
        *,
        options: DetectionOptions | None = None,
    ) -> None:
        self.model = model
        self.chinese = chinese
        self.options = options or DetectionOptions()

    @property
    def metadata(self) -> dict[str, Any]:
        return {
            "runtime": "composite",
            "model_enabled": self.options.model_enabled and self.model is not None,
            "chinese_rules": self.chinese.metadata if self.chinese is not None else None,
            "model": self.model.metadata if self.model is not None else None,
        }

    def detect(
        self,
        text: str,
        *,
        progress: ProgressCallback | None = None,
        cancel: CancelCheck | None = None,
    ) -> DetectionBatch:
        check_cancelled(cancel)
        batches: list[DetectionBatch] = []
        if self.options.model_enabled and self.model is not None:
            batches.append(self.model.detect(text, progress=progress, cancel=cancel))
        if self.chinese is not None and self.options.chinese.enabled_rule_ids():
            batches.append(self.chinese.detect(text, progress=progress, cancel=cancel))
        if not batches:
            return DetectionBatch(
                text=text,
                detections=(),
                warnings=("未启用任何检测器。",),
                stats={"runtime": "composite"},
            )
        merged = merge_batches(batches)
        merged.stats["runtime"] = "composite"
        merged.stats["model_enabled"] = self.options.model_enabled and self.model is not None
        merged.stats["chinese_rules"] = self.options.chinese.as_dict()
        return merged
