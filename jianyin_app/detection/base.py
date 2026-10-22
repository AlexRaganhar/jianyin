"""Shared detection dataclasses and interfaces."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol, Sequence

from ..errors import OperationCancelled

ProgressCallback = Callable[[Mapping[str, Any]], None]
CancelCheck = Callable[[], bool]


@dataclass(frozen=True)
class Detection:
    """One sensitive span, expressed against the original input text."""

    category: str
    start: int
    end: int
    text: str
    source: str = "model"
    subtype: str | None = None
    priority: int = 60

    def with_source(self, source: str, *, priority: int) -> "Detection":
        return Detection(
            category=self.category,
            start=self.start,
            end=self.end,
            text=self.text,
            source=source,
            subtype=self.subtype,
            priority=max(self.priority, priority),
        )


@dataclass(frozen=True)
class DetectionBatch:
    """Detector output for exactly one input string."""

    text: str
    detections: tuple[Detection, ...]
    warnings: tuple[str, ...] = ()
    stats: Mapping[str, Any] = field(default_factory=dict)


class Detector(Protocol):
    """Minimal interface shared by the ONNX model and test doubles."""

    @property
    def metadata(self) -> dict[str, Any]: ...

    def detect(
        self,
        text: str,
        *,
        progress: ProgressCallback | None = None,
        cancel: CancelCheck | None = None,
    ) -> DetectionBatch: ...


def check_cancelled(cancel: CancelCheck | None) -> None:
    if cancel is not None and cancel():
        raise OperationCancelled()


def emit_progress(progress: ProgressCallback | None, payload: Mapping[str, Any]) -> None:
    if progress is None:
        return
    try:
        progress(dict(payload))
    except Exception:
        # A display callback must never interrupt a local analysis.
        pass


def batch_from_detections(
    text: str,
    detections: Sequence[Detection],
    *,
    warnings: Sequence[str] = (),
    stats: Mapping[str, Any] | None = None,
) -> DetectionBatch:
    return DetectionBatch(
        text=text,
        detections=tuple(detections),
        warnings=tuple(warnings),
        stats=dict(stats or {}),
    )
