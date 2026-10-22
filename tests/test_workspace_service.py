from __future__ import annotations

from pathlib import Path

from jianyin_app.redaction.policy import default_ruleset
from jianyin_app.workspace.service import analyze_case, apply_case, export_documents, restore_case
from jianyin_app.workspace.store import CaseWorkspace
from tests.fakes import FakeDetector


def test_case_service_analyze_apply_restore_and_export(tmp_path: Path) -> None:
    workspace = CaseWorkspace(tmp_path / "workspace")
    case = workspace.create_case("服务测试")
    source = tmp_path / "材料.txt"
    original = "Alice 的电话是 13800138000。Bob 也在。\n"
    source.write_text(original, encoding="utf-8")
    document = workspace.import_document(case["id"], source)

    detector = FakeDetector(
        [
            ("Alice", "private_person", None),
            ("Bob", "private_person", None),
            ("13800138000", "private_phone", None),
        ]
    )
    draft = analyze_case(workspace, case["id"], detector, default_ruleset())
    assert len(draft.candidates) == 3
    assert workspace.draft_path(case["id"]).is_file()

    application = apply_case(workspace, case["id"], draft, export_docx_enabled=False)
    assert application.summary["applied_occurrence_count"] == 3
    redacted = workspace.redacted_text_path(case["id"], document["id"]).read_text(encoding="utf-8")
    assert "Alice" not in redacted
    assert "13800138000" not in redacted
    assert workspace.mapping_path(case["id"]).is_file()

    restored = restore_case(workspace, case["id"], export_docx_enabled=False)
    assert restored[document["id"]] == original
    assert workspace.restored_text_path(case["id"], document["id"]).read_text(encoding="utf-8") == original

    exported = export_documents(
        workspace,
        case["id"],
        [document["id"]],
        tmp_path / "export",
        include_md=True,
        include_docx=True,
        include_mapping=True,
    )
    assert len(exported) == 3
    assert all(path.is_file() for path in exported)
