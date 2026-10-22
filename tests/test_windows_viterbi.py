from __future__ import annotations

import numpy as np
import pytest

from jianyin_app.errors import ConfigurationError
from jianyin_app.model.viterbi import (
    ViterbiDecoder,
    build_label_info,
    labels_to_token_spans,
    parse_id2label,
    trim_and_deduplicate_spans,
)
from jianyin_app.model.windows import build_windows


def test_windows_cover_short_document() -> None:
    assert build_windows(0, 4, 1) == []
    windows = build_windows(3, 4, 1)
    assert [(item.start, item.end) for item in windows] == [(0, 3)]


def test_windows_cover_long_document_with_overlap() -> None:
    windows = build_windows(10, 4, 2)
    assert windows[0].start == 0
    assert windows[-1].end == 10
    covered = set()
    for window in windows:
        covered.update(range(window.start, window.end))
    assert covered == set(range(10))


def test_windows_reject_invalid_overlap() -> None:
    with pytest.raises(ConfigurationError):
        build_windows(10, 4, 4)


def test_labels_to_spans_and_trim() -> None:
    info = build_label_info(
        [
            "O",
            "B-private_person",
            "I-private_person",
            "E-private_person",
            "S-private_person",
        ]
    )
    spans = labels_to_token_spans([1, 2, 3, 0, 4], info)
    assert spans == [(1, 0, 3), (1, 4, 5)]
    trimmed = trim_and_deduplicate_spans([(1, 0, 3), (1, 0, 2)], "Alice")
    assert trimmed == [(1, 0, 3)]


def test_parse_id2label_accepts_string_keys() -> None:
    names = parse_id2label(
        {
            "id2label": {
                "0": "O",
                "1": "B-private_person",
                "2": "I-private_person",
                "3": "E-private_person",
                "4": "S-private_person",
            }
        }
    )
    assert names[0] == "O"
    assert names[-1] == "S-private_person"
    assert len(build_label_info(names).span_class_names) == 2


def test_viterbi_decodes_a_simple_span() -> None:
    info = build_label_info(
        [
            "O",
            "B-private_person",
            "I-private_person",
            "E-private_person",
            "S-private_person",
        ]
    )
    decoder = ViterbiDecoder(info)
    logits = np.full((5, 5), -20.0, dtype=np.float32)
    for index, label in enumerate([1, 2, 3, 0, 4]):
        logits[index, label] = 20.0
    assert decoder.decode(logits) == [1, 2, 3, 0, 4]

