from __future__ import annotations

import pytest

from jianyin_app.errors import RestoreError
from jianyin_app.redaction.analysis import analyze_documents
from jianyin_app.redaction.apply import apply_draft
from jianyin_app.redaction.policy import default_ruleset
from jianyin_app.redaction.restore import restore_documents
from jianyin_app.redaction.schema import CandidateRule, DocumentText, Draft, Occurrence
from tests.fakes import FakeDetector


def _documents() -> list[DocumentText]:
    return [
        DocumentText("doc1", "材料一.md", "Alice met Bob. Phone 13800138000."),
        DocumentText("doc2", "材料二.md", "Bob called Alice."),
    ]


def _detector() -> FakeDetector:
    return FakeDetector(
        [
            ("Alice", "private_person", None),
            ("Bob", "private_person", None),
            ("13800138000", "private_phone", None),
        ]
    )


def test_analyze_groups_shared_values_and_apply_restore_exactly() -> None:
    documents = _documents()
    draft = analyze_documents(
        documents,
        _detector(),
        default_ruleset(),
        scope="case",
        case={"id": "case1", "name": "测试案件"},
    )
    assert draft.summary["candidate_rule_count"] == 3
    alice = next(item for item in draft.candidates if item.source == "Alice")
    bob = next(item for item in draft.candidates if item.source == "Bob")
    assert alice.detected_count == 2
    assert bob.detected_count == 2
    assert alice.literal_count == 2
    assert alice.target == "[姓名1]"
    assert bob.target == "[姓名2]"

    application = apply_draft(documents, draft)
    assert application.mapping["schema_version"] == 3
    assert application.mapping["scope"] == "case"
    assert "Alice" not in application.documents["doc1"]
    assert "Bob" not in application.documents["doc1"]
    assert "Bob" not in application.documents["doc2"]
    assert "13800138000" not in application.documents["doc1"]
    assert application.mapping["summary"]["applied_occurrence_count"] == 5

    restored = restore_documents(
        [
            DocumentText("doc1", "材料一.md", application.documents["doc1"]),
            DocumentText("doc2", "材料二.md", application.documents["doc2"]),
        ],
        application.mapping,
    )
    assert restored["doc1"] == documents[0].text
    assert restored["doc2"] == documents[1].text


def test_apply_all_false_only_replaces_detected_occurrence() -> None:
    text = "Alice met Alice."
    document = DocumentText("doc", "材料.md", text)
    draft = Draft(
        scope="file",
        source_name="材料.md",
        candidates=[
            CandidateRule(
                id=1,
                category="private_person",
                source="Alice",
                target="[姓名1]",
                apply_all=False,
                match_mode="literal",
                detection_sources=["model"],
                detected_count=1,
                occurrences=[Occurrence("doc", 0, 5, "model")],
            )
        ],
    )
    application = apply_draft([document], draft)
    assert application.documents["doc"].count("Alice") == 1
    assert application.documents["doc"].startswith("[姓名1]")


def test_manual_rule_applies_to_all_literal_occurrences() -> None:
    text = "Carol met Carol."
    document = DocumentText("doc", "材料.md", text)
    draft = Draft(
        scope="file",
        source_name="材料.md",
        candidates=[
            CandidateRule(
                id=1,
                category="private_person",
                source="Carol",
                target="[姓名1]",
                apply_all=True,
                match_mode="literal",
                detection_sources=["manual"],
                detected_count=0,
            )
        ],
    )
    application = apply_draft([document], draft)
    assert application.documents["doc"] == "[姓名1] met [姓名1]."
    assert application.mapping["mappings"][0]["occurrences"]


def test_restore_refuses_modified_redacted_text() -> None:
    documents = _documents()
    draft = analyze_documents(
        documents,
        _detector(),
        default_ruleset(),
        scope="case",
        case={"id": "case1", "name": "测试案件"},
    )
    application = apply_draft(documents, draft)
    modified = application.documents["doc1"].replace("[姓名1]", "Alice", 1)
    with pytest.raises(RestoreError):
        restore_documents([DocumentText("doc1", "材料一.md", modified)], application.mapping)


def test_no_detections_produces_unchanged_text_and_empty_mapping() -> None:
    document = DocumentText("doc", "材料.md", "没有敏感信息。")
    draft = analyze_documents(
        [document],
        FakeDetector([]),
        default_ruleset(),
        scope="file",
        source_name="材料.md",
    )
    assert draft.candidates == []
    application = apply_draft([document], draft)
    assert application.documents["doc"] == document.text
    assert application.mapping["mappings"] == []
    restored = restore_documents([DocumentText("doc", "材料.md", application.documents["doc"])], application.mapping)
    assert restored["doc"] == document.text


def test_existing_manual_and_edited_targets_are_preserved() -> None:
    document = DocumentText("doc", "材料.md", "Alice and Carol.")
    first = analyze_documents(
        [document],
        FakeDetector([("Alice", "private_person", None)]),
        default_ruleset(),
        scope="file",
        source_name="材料.md",
    )
    alice = first.candidates[0]
    alice.target = "当事人甲"
    alice.target_edited = True
    first.candidates.append(
        CandidateRule(
            id=2,
            category="private_person",
            source="Carol",
            target="当事人乙",
            target_edited=True,
            detection_sources=["manual"],
            apply_all=True,
        )
    )
    second = analyze_documents(
        [document],
        FakeDetector([("Alice", "private_person", None)]),
        default_ruleset(),
        scope="file",
        source_name="材料.md",
        existing_draft=first,
        preserve_existing=True,
    )
    by_source = {candidate.source: candidate for candidate in second.candidates}
    assert by_source["Alice"].target == "当事人甲"
    assert by_source["Carol"].target == "当事人乙"
    assert by_source["Carol"].is_manual


def test_page_marker_is_not_changed() -> None:
    text = "<!-- PDF page 1 -->\nAlice"
    document = DocumentText("doc", "材料.md", text)
    draft = analyze_documents(
        [document],
        FakeDetector([("Alice", "private_person", None)]),
        default_ruleset(),
        scope="file",
        source_name="材料.md",
    )
    application = apply_draft([document], draft)
    assert application.documents["doc"].startswith("<!-- PDF page 1 -->")
    assert "Alice" not in application.documents["doc"]

