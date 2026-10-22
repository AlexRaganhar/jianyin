"""BIOES-constrained Viterbi decoding for the privacy label space."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from ..errors import ModelError

VITERBI_BIAS_KEYS: tuple[str, ...] = (
    "transition_bias_background_stay",
    "transition_bias_background_to_start",
    "transition_bias_inside_to_continue",
    "transition_bias_inside_to_end",
    "transition_bias_end_to_background",
    "transition_bias_end_to_start",
)

_NEG_INF = -1e9


@dataclass(frozen=True)
class LabelInfo:
    """Resolved mapping from token labels to boundary-aware span labels."""

    token_to_span_label: Mapping[int, int]
    token_boundary_tags: Mapping[int, str | None]
    span_class_names: tuple[str, ...]
    background_token_label: int
    background_span_label: int


def build_label_info(class_names: Sequence[str]) -> LabelInfo:
    """Build and validate label lookup tables from ``config.json``'s id2label."""
    names = tuple(str(name).strip() for name in class_names)
    if not names or names[0] != "O":
        raise ModelError("模型标签定义无效：缺少背景标签 O。")
    if len(set(names)) != len(names):
        raise ModelError("模型标签定义无效：存在重复标签。")

    span_class_names: list[str] = ["O"]
    span_lookup: dict[str, int] = {"O": 0}
    token_to_span: dict[int, int] = {}
    boundary_tags: dict[int, str | None] = {}
    boundary_labels: defaultdict[str, set[str]] = defaultdict(set)
    background_index: int | None = None

    for index, name in enumerate(names):
        if name == "O":
            background_index = index
            token_to_span[index] = 0
            boundary_tags[index] = None
            continue
        if "-" not in name:
            raise ModelError("模型标签定义无效：非背景标签必须是 BIOES 形式。")
        boundary, span_name = name.split("-", 1)
        if boundary not in {"B", "I", "E", "S"} or not span_name:
            raise ModelError("模型标签定义无效：非背景标签必须是 BIOES 形式。")
        span_index = span_lookup.get(span_name)
        if span_index is None:
            span_index = len(span_class_names)
            span_class_names.append(span_name)
            span_lookup[span_name] = span_index
        token_to_span[index] = span_index
        boundary_tags[index] = boundary
        boundary_labels[span_name].add(boundary)

    if background_index is None:
        raise ModelError("模型标签定义无效：缺少背景标签 O。")
    for span_name, tags in boundary_labels.items():
        if tags != {"B", "I", "E", "S"}:
            raise ModelError(f"模型标签定义不完整：类别 {span_name!r} 缺少 BIOES 标签。")

    return LabelInfo(
        token_to_span_label=token_to_span,
        token_boundary_tags=boundary_tags,
        span_class_names=tuple(span_class_names),
        background_token_label=background_index,
        background_span_label=0,
    )


def load_viterbi_biases(path: str | Path) -> dict[str, float]:
    """Read the six official transition biases from the calibration artifact."""
    calibration_path = Path(path)
    try:
        payload = json.loads(calibration_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ModelError("无法读取 viterbi_calibration.json。") from error
    try:
        raw = payload["operating_points"]["default"]["biases"]
    except (KeyError, TypeError) as error:
        raise ModelError("viterbi_calibration.json 格式无效。") from error
    if not isinstance(raw, Mapping) or set(raw) != set(VITERBI_BIAS_KEYS):
        raise ModelError("viterbi_calibration.json 的校准参数不完整。")
    try:
        return {key: float(raw[key]) for key in VITERBI_BIAS_KEYS}
    except (TypeError, ValueError) as error:
        raise ModelError("viterbi_calibration.json 含有无效数值。") from error


def zero_biases() -> dict[str, float]:
    return {key: 0.0 for key in VITERBI_BIAS_KEYS}


class ViterbiDecoder:
    """Constrained Viterbi decoder with the official transition biases."""

    def __init__(self, label_info: LabelInfo, biases: Mapping[str, float] | None = None) -> None:
        self._label_info = label_info
        self._biases = dict(zero_biases())
        if biases:
            for key in VITERBI_BIAS_KEYS:
                if key in biases:
                    self._biases[key] = float(biases[key])
        class_count = len(label_info.token_to_span_label)
        self._start_scores = np.full(class_count, _NEG_INF, dtype=np.float32)
        self._end_scores = np.full(class_count, _NEG_INF, dtype=np.float32)
        self._transition_scores = np.full((class_count, class_count), _NEG_INF, dtype=np.float32)
        self._build_scores()

    def _is_background(self, span: int | None, index: int) -> bool:
        return span == self._label_info.background_span_label or index == self._label_info.background_token_label

    def _valid_transition(
        self,
        tag: str | None,
        span: int | None,
        next_tag: str | None,
        next_span: int | None,
        next_index: int,
    ) -> bool:
        next_is_background = self._is_background(next_span, next_index)
        if (next_span is None or next_tag is None) and not next_is_background:
            return False
        if span is None or tag is None:
            return next_is_background or next_tag in {"B", "S"}
        if span == self._label_info.background_span_label or tag in {"E", "S"}:
            return next_is_background or next_tag in {"B", "S"}
        return tag in {"B", "I"} and span == next_span and next_tag in {"I", "E"}

    def _transition_bias(
        self,
        tag: str | None,
        span: int | None,
        next_tag: str | None,
        next_span: int | None,
        index: int,
        next_index: int,
    ) -> float:
        if self._is_background(span, index):
            if self._is_background(next_span, next_index):
                return self._biases["transition_bias_background_stay"]
            if next_tag in {"B", "S"}:
                return self._biases["transition_bias_background_to_start"]
            return 0.0
        if tag in {"B", "I"}:
            if next_tag == "I" and span == next_span:
                return self._biases["transition_bias_inside_to_continue"]
            if next_tag == "E" and span == next_span:
                return self._biases["transition_bias_inside_to_end"]
            return 0.0
        if tag in {"E", "S"}:
            if self._is_background(next_span, next_index):
                return self._biases["transition_bias_end_to_background"]
            if next_tag in {"B", "S"}:
                return self._biases["transition_bias_end_to_start"]
        return 0.0

    def _build_scores(self) -> None:
        info = self._label_info
        class_count = len(info.token_to_span_label)
        for index in range(class_count):
            tag = info.token_boundary_tags.get(index)
            span = info.token_to_span_label.get(index)
            if tag in {"B", "S"} or index == info.background_token_label:
                self._start_scores[index] = 0.0
            if tag in {"E", "S"} or index == info.background_token_label:
                self._end_scores[index] = 0.0
            for next_index in range(class_count):
                next_tag = info.token_boundary_tags.get(next_index)
                next_span = info.token_to_span_label.get(next_index)
                if self._valid_transition(tag, span, next_tag, next_span, next_index):
                    self._transition_scores[index, next_index] = self._transition_bias(
                        tag, span, next_tag, next_span, index, next_index
                    )

    def decode(self, log_probs: np.ndarray) -> list[int]:
        """Decode ``[seq_len, num_classes]`` log probabilities into label ids."""
        array = np.asarray(log_probs, dtype=np.float32)
        if array.ndim != 2:
            raise ModelError("模型输出的标签维度无效。")
        if array.shape[1] != self._transition_scores.shape[0]:
            raise ModelError("模型输出的标签数量与配置不一致。")
        if array.shape[0] == 0:
            return []

        scores = array[0] + self._start_scores
        backpointers = np.empty((array.shape[0] - 1, array.shape[1]), dtype=np.int32)
        for index in range(1, array.shape[0]):
            transitions = scores[:, None] + self._transition_scores
            backpointers[index - 1] = np.argmax(transitions, axis=0)
            scores = np.max(transitions, axis=0) + array[index]

        if not np.isfinite(scores).any():
            return np.argmax(array, axis=1).astype(int).tolist()

        last_label = int(np.argmax(scores + self._end_scores))
        path = np.empty(array.shape[0], dtype=np.int32)
        path[-1] = last_label
        for index in range(array.shape[0] - 2, -1, -1):
            path[index] = backpointers[index, path[index + 1]]
        return path.astype(int).tolist()


def labels_to_token_spans(labels: Sequence[int], info: LabelInfo) -> list[tuple[int, int, int]]:
    """Convert per-token BIOES ids into ``(span_label, start_token, end_token)``."""
    spans: list[tuple[int, int, int]] = []
    current_label: int | None = None
    start_index: int | None = None
    previous_index: int | None = None

    for token_index, label_id in enumerate(labels):
        span_label = info.token_to_span_label.get(int(label_id))
        boundary = info.token_boundary_tags.get(int(label_id))
        if span_label is None:
            continue
        if span_label == info.background_span_label:
            if current_label is not None and start_index is not None:
                spans.append((current_label, start_index, token_index))
            current_label = None
            start_index = None
        elif boundary == "S":
            if current_label is not None and start_index is not None and previous_index is not None:
                spans.append((current_label, start_index, previous_index + 1))
            spans.append((span_label, token_index, token_index + 1))
            current_label = None
            start_index = None
        elif boundary == "B":
            if current_label is not None and start_index is not None and previous_index is not None:
                spans.append((current_label, start_index, previous_index + 1))
            current_label = span_label
            start_index = token_index
        elif boundary == "I":
            if current_label is None or current_label != span_label:
                if current_label is not None and start_index is not None and previous_index is not None:
                    spans.append((current_label, start_index, previous_index + 1))
                current_label = span_label
                start_index = token_index
        elif boundary == "E":
            if current_label is None or current_label != span_label or start_index is None:
                if current_label is not None and start_index is not None and previous_index is not None:
                    spans.append((current_label, start_index, previous_index + 1))
                spans.append((span_label, token_index, token_index + 1))
            else:
                spans.append((current_label, start_index, token_index + 1))
            current_label = None
            start_index = None
        else:
            if current_label is not None and start_index is not None and previous_index is not None:
                spans.append((current_label, start_index, previous_index + 1))
            current_label = None
            start_index = None
        previous_index = token_index

    if current_label is not None and start_index is not None and previous_index is not None:
        spans.append((current_label, start_index, previous_index + 1))
    return spans


def trim_and_deduplicate_spans(
    spans: Sequence[tuple[int, int, int]], text: str
) -> list[tuple[int, int, int]]:
    """Trim whitespace and keep a deterministic longest span per label."""
    per_label: defaultdict[int, list[tuple[int, int]]] = defaultdict(list)
    for label, start, end in spans:
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if end > start:
            per_label[label].append((start, end))

    kept: list[tuple[int, int, int]] = []
    for label, candidates in per_label.items():
        accepted: list[tuple[int, int]] = []
        for start, end in sorted(candidates, key=lambda item: (item[0], -(item[1] - item[0]))):
            if any(not (end <= old_start or start >= old_end) for old_start, old_end in accepted):
                continue
            accepted.append((start, end))
        kept.extend((label, start, end) for start, end in accepted)
    return sorted(kept, key=lambda item: (item[1], item[2], item[0]))


def parse_id2label(config: Mapping[str, Any]) -> tuple[str, ...]:
    """Read ``id2label`` from a model config, accepting string or int keys."""
    raw = config.get("id2label")
    if not isinstance(raw, Mapping):
        raise ModelError("模型 config.json 缺少 id2label。")
    try:
        count = len(raw)
        names = []
        for index in range(count):
            value = raw.get(str(index), raw.get(index))
            if value is None:
                raise KeyError(index)
            names.append(str(value).strip())
    except (KeyError, TypeError) as error:
        raise ModelError("模型 config.json 中的 id2label 定义无效。") from error
    return tuple(names)
