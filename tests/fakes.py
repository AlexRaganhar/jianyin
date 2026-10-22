"""Shared test doubles."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from jianyin_app.detection.base import Detection, DetectionBatch


class FakeDetector:
    """Find a fixed set of strings and report them as model detections."""

    def __init__(
        self,
        tokens: Sequence[tuple[str, str, str | None]] | None = None,
        *,
        metadata: Mapping[str, Any] | None = None,
        warning: str | None = None,
    ) -> None:
        self.tokens = list(tokens or [])
        self._metadata = dict(metadata or {"runtime": "fake-model", "model_revision": "test"})
        self.warning = warning

    @property
    def metadata(self) -> dict[str, Any]:
        return dict(self._metadata)

    def detect(self, text: str, *, progress=None, cancel=None) -> DetectionBatch:
        detections: list[Detection] = []
        for token, category, subtype in self.tokens:
            start = text.find(token)
            while start >= 0:
                detections.append(
                    Detection(
                        category=category,
                        start=start,
                        end=start + len(token),
                        text=token,
                        source="model",
                        subtype=subtype,
                        priority=60,
                    )
                )
                start = text.find(token, start + 1)
        return DetectionBatch(
            text=text,
            detections=tuple(detections),
            warnings=(self.warning,) if self.warning else (),
            stats={"runtime": "fake-model", "detected_span_count": len(detections)},
        )


class StaticDetector:
    def __init__(self, detections_by_text: Mapping[str, Sequence[Detection]]) -> None:
        self.detections_by_text = detections_by_text

    @property
    def metadata(self) -> dict[str, Any]:
        return {"runtime": "static-fake"}

    def detect(self, text: str, *, progress=None, cancel=None) -> DetectionBatch:
        detections = self.detections_by_text.get(text, ())
        return DetectionBatch(text=text, detections=tuple(detections))

