"""Agent-friendly command line entry point for 笺隐."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from .config import (
    DEFAULT_OVERLAP_TOKENS,
    DEFAULT_WINDOW_SIZE,
    ModelConfig,
)
from .detection.base import ProgressCallback
from .detection.chinese_rules import ChineseRuleDetector
from .detection.composite import CompositeDetector
from .documents.docx_export import export_docx
from .documents.importers import read_text_file
from .errors import JianYinError, OperationCancelled
from .model.download import download_model
from .model.onnx_detector import OnnxPrivacyFilter
from .redaction.analysis import analyze_documents
from .redaction.apply import apply_draft
from .redaction.policy import RuleSet, default_ruleset
from .redaction.restore import restore_documents
from .redaction.schema import DocumentText, Draft
from .workspace.paths import atomic_write_text, write_json

CLI_SUFFIXES = {".txt", ".md", ".markdown"}
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_CANCELLED = 130


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jianyin",
        description="笺隐：本地、可审阅、可还原的文档脱敏工具。",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(subparser: argparse.ArgumentParser, *, needs_input: bool = True) -> None:
        if needs_input:
            subparser.add_argument("--input", required=True, help="TXT/Markdown 输入文件；使用 - 从标准输入读取。")
        subparser.add_argument("--output-md", help="脱敏/还原 Markdown 输出路径。")
        subparser.add_argument("--output-docx", help="可选 DOCX 输出路径（文本重排）。")
        subparser.add_argument("--mapping", help="映射 JSON 路径（apply/redact 必需，restore 为输入）。")
        subparser.add_argument("--draft", help="规则草稿 JSON 路径（apply 必需，analyze 为输出）。")
        subparser.add_argument("--model-dir", help="Q4 ONNX 模型目录。")
        subparser.add_argument("--rules", help="策略规则 JSON 路径；省略使用内置默认规则。")
        subparser.add_argument("--chinese-rules", help="中文补强规则配置 JSON 路径。")
        subparser.add_argument("--no-chinese", action="store_true", help="关闭中文规则补强。")
        subparser.add_argument(
            "--decode-mode",
            choices=("viterbi", "argmax"),
            default="viterbi",
            help="解码方式，默认 viterbi。",
        )
        subparser.add_argument(
            "--max-tokens",
            type=int,
            default=DEFAULT_WINDOW_SIZE,
            help=f"单个推理窗口的 token 数，默认 {DEFAULT_WINDOW_SIZE}。",
        )
        subparser.add_argument(
            "--overlap-tokens",
            type=int,
            default=DEFAULT_OVERLAP_TOKENS,
            help=f"窗口重叠 token 数，默认 {DEFAULT_OVERLAP_TOKENS}。",
        )
        subparser.add_argument("--offline", action="store_true", help="禁止下载模型，只使用本地模型。")
        subparser.add_argument("--progress", action="store_true", help="向 stderr 输出聚合进度 JSON。")
        subparser.add_argument("--force", action="store_true", help="允许覆盖已有输出。")

    analyze = subparsers.add_parser("analyze", help="检测敏感信息并生成规则草稿。")
    add_common(analyze)

    apply = subparsers.add_parser("apply", help="用已有规则草稿生成脱敏文本和映射。")
    add_common(apply)

    redact = subparsers.add_parser("redact", help="一次完成分析和应用。")
    add_common(redact)

    restore = subparsers.add_parser("restore", help="按映射还原脱敏文本。")
    add_common(restore)

    download = subparsers.add_parser("download-model", help="下载并校验 Q4 ONNX 模型。")
    download.add_argument("--model-dir", help="模型目标目录。")
    download.add_argument("--progress", action="store_true", help="向 stderr 输出进度 JSON。")
    return parser


def _safe_progress_printer(enabled: bool) -> ProgressCallback | None:
    if not enabled:
        return None

    def printer(event: Mapping[str, Any]) -> None:
        safe_keys = (
            "stage",
            "document_index",
            "document_count",
            "file_index",
            "total_files",
            "window_index",
            "window_count",
            "ocr_progress",
            "total_pages",
            "completed_pages",
            "failed_pages",
        )
        payload = {key: event[key] for key in safe_keys if key in event}
        if payload:
            print(json.dumps(payload, ensure_ascii=False), file=sys.stderr, flush=True)

    return printer


def _read_input(path_value: str) -> tuple[str | None, str, str]:
    if path_value == "-":
        text = sys.stdin.read()
        return None, text, "stdin"
    path = Path(path_value)
    if path.suffix.lower() not in CLI_SUFFIXES:
        raise JianYinError("CLI 只处理 TXT/Markdown；DOCX/PDF 请使用桌面工作台。")
    text, _encoding = read_text_file(path)
    return path, text, path.name


def _validate_outputs(input_path: Path | None, outputs: Sequence[Path], *, force: bool) -> None:
    resolved = [path.resolve(strict=False) for path in outputs]
    if len(set(resolved)) != len(resolved):
        raise JianYinError("多个输出路径不能相同。")
    if input_path is not None:
        source = input_path.resolve(strict=False)
        if source in resolved:
            raise JianYinError("输出文件不能覆盖输入文件。")
    for path in outputs:
        if path.exists() and not force:
            raise JianYinError(f"输出已存在：{path}；确认覆盖请添加 --force。")


def _write_text(path: Path, text: str) -> None:
    atomic_write_text(path, text)


def _build_rules(args: argparse.Namespace) -> RuleSet:
    return RuleSet.from_path(args.rules) if args.rules else default_ruleset()


def _build_detector(args: argparse.Namespace, progress: ProgressCallback | None) -> CompositeDetector:
    config = ModelConfig(
        model_dir=args.model_dir,
        window_size=args.max_tokens,
        overlap_tokens=args.overlap_tokens,
        decode_mode=args.decode_mode,
        offline=args.offline,
    ).normalized()
    model = OnnxPrivacyFilter(config)
    from .config import ChineseRuleOptions, DetectionOptions

    options = ChineseRuleOptions(
        cn_id=not args.no_chinese,
        cn_mobile=not args.no_chinese,
        cn_bank_card=not args.no_chinese,
        cn_name_context=not args.no_chinese,
        cn_landline=False,
        cn_date=False,
        cn_address=False,
    )
    chinese = ChineseRuleDetector(options, config_path=args.chinese_rules)
    return CompositeDetector(
        model,
        chinese,
        options=DetectionOptions(model_enabled=True, chinese=options),
    )


def _file_document(text: str, source_name: str, suffix: str = "text") -> DocumentText:
    return DocumentText(
        id="document",
        name=source_name,
        text=text,
        source_type=suffix,
        extraction_method="text",
        page_count=1,
    )


def _analyze_file(args: argparse.Namespace, progress: ProgressCallback | None) -> tuple[Draft, str]:
    input_path, text, source_name = _read_input(args.input)
    rules = _build_rules(args)
    detector = _build_detector(args, progress)
    draft = analyze_documents(
        [_file_document(text, source_name, input_path.suffix.lstrip(".") if input_path else "text")],
        detector,
        rules,
        scope="file",
        source_name=source_name,
        progress=progress,
    )
    return draft, source_name


def _apply_file(
    args: argparse.Namespace,
    text: str,
    source_name: str,
    draft: Draft,
    *,
    suffix: str = "text",
) -> tuple[str, dict[str, Any]]:
    output_md = Path(args.output_md)
    output_docx = Path(args.output_docx) if args.output_docx else None
    mapping_path = Path(args.mapping)
    _validate_outputs(
        Path(args.input) if args.input != "-" else None,
        [output_md, mapping_path] + ([output_docx] if output_docx else []),
        force=args.force,
    )
    document = _file_document(text, source_name, suffix)
    result = apply_draft(
        [document],
        draft,
        document_metadata={
            document.id: {
                "source_name": source_name,
                "display_name": source_name,
                "source_type": suffix,
                "extraction_method": "text",
                "page_count": 1,
            }
        },
        redacted_md_paths={document.id: str(output_md)},
        redacted_docx_paths={document.id: str(output_docx)} if output_docx else None,
    )
    _write_text(output_md, result.documents[document.id])
    if output_docx is not None:
        export_docx(result.documents[document.id], output_docx, title=f"脱敏文本 · {source_name}")
    write_json(mapping_path, result.mapping)
    return result.documents[document.id], result.mapping


def _command_analyze(args: argparse.Namespace) -> int:
    if not args.draft:
        raise JianYinError("analyze 需要 --draft 输出路径。")
    draft_path = Path(args.draft)
    _validate_outputs(Path(args.input) if args.input != "-" else None, [draft_path], force=args.force)
    draft, source_name = _analyze_file(args, _safe_progress_printer(args.progress))
    write_json(draft_path, draft.to_dict())
    _print_status(
        {
            "status": "ok",
            "command": "analyze",
            "input": source_name,
            "draft": str(draft_path),
            "summary": draft.summary,
            "review_required": True,
        }
    )
    return EXIT_OK


def _command_apply(args: argparse.Namespace) -> int:
    if not args.draft or not args.output_md or not args.mapping:
        raise JianYinError("apply 需要 --draft、--output-md 和 --mapping。")
    input_path, text, source_name = _read_input(args.input)
    try:
        draft = Draft.from_dict(json.loads(Path(args.draft).read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as error:
        raise JianYinError("规则草稿无法读取。") from error
    if draft.scope != "file":
        raise JianYinError("CLI 只能应用单文件草稿；案件草稿请使用桌面工作台。")
    _redacted, mapping = _apply_file(
        args,
        text,
        source_name,
        draft,
        suffix=input_path.suffix.lstrip(".") if input_path else "text",
    )
    _print_status(
        {
            "status": "ok",
            "command": "apply",
            "input": source_name,
            "outputs": _outputs_payload(args),
            "mapping": str(Path(args.mapping)),
            "summary": mapping.get("summary", {}),
            "review_required": True,
        }
    )
    return EXIT_OK


def _command_redact(args: argparse.Namespace) -> int:
    if not args.output_md or not args.mapping:
        raise JianYinError("redact 需要 --output-md 和 --mapping。")
    input_path, text, source_name = _read_input(args.input)
    output_md = Path(args.output_md)
    output_docx = Path(args.output_docx) if args.output_docx else None
    mapping_path = Path(args.mapping)
    _validate_outputs(
        input_path,
        [output_md, mapping_path] + ([output_docx] if output_docx else []),
        force=args.force,
    )
    rules = _build_rules(args)
    detector = _build_detector(args, _safe_progress_printer(args.progress))
    draft = analyze_documents(
        [_file_document(text, source_name, input_path.suffix.lstrip(".") if input_path else "text")],
        detector,
        rules,
        scope="file",
        source_name=source_name,
        progress=_safe_progress_printer(args.progress),
    )
    _redacted, mapping = _apply_file(
        args,
        text,
        source_name,
        draft,
        suffix=input_path.suffix.lstrip(".") if input_path else "text",
    )
    _print_status(
        {
            "status": "ok",
            "command": "redact",
            "input": source_name,
            "outputs": _outputs_payload(args),
            "mapping": str(Path(args.mapping)),
            "summary": mapping.get("summary", {}),
            "review_required": True,
        }
    )
    return EXIT_OK


def _command_restore(args: argparse.Namespace) -> int:
    if not args.output_md or not args.mapping:
        raise JianYinError("restore 需要 --output-md 和 --mapping。")
    input_path, text, source_name = _read_input(args.input)
    output_md = Path(args.output_md)
    output_docx = Path(args.output_docx) if args.output_docx else None
    _validate_outputs(
        input_path,
        [output_md] + ([output_docx] if output_docx else []),
        force=args.force,
    )
    try:
        mapping = json.loads(Path(args.mapping).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise JianYinError("映射文件无法读取。") from error
    document = _file_document(text, source_name, input_path.suffix.lstrip(".") if input_path else "text")
    restored = restore_documents([document], mapping)
    _write_text(output_md, restored[document.id])
    if output_docx is not None:
        export_docx(restored[document.id], output_docx, title=f"还原文本 · {source_name}")
    _print_status(
        {
            "status": "ok",
            "command": "restore",
            "input": source_name,
            "outputs": _outputs_payload(args),
            "document_count": 1,
            "review_required": True,
        }
    )
    return EXIT_OK


def _command_download(args: argparse.Namespace) -> int:
    path = download_model(args.model_dir, progress=_safe_progress_printer(args.progress))
    _print_status(
        {
            "status": "ok",
            "command": "download-model",
            "model_dir": str(path),
            "review_required": False,
        }
    )
    return EXIT_OK


def _outputs_payload(args: argparse.Namespace) -> dict[str, str]:
    outputs: dict[str, str] = {}
    if getattr(args, "output_md", None):
        outputs["md"] = str(Path(args.output_md))
    if getattr(args, "output_docx", None):
        outputs["docx"] = str(Path(args.output_docx))
    return outputs


def _print_status(payload: Mapping[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "analyze":
            return _command_analyze(args)
        if args.command == "apply":
            return _command_apply(args)
        if args.command == "redact":
            return _command_redact(args)
        if args.command == "restore":
            return _command_restore(args)
        if args.command == "download-model":
            return _command_download(args)
        parser.error("未知命令。")
        return EXIT_USAGE
    except OperationCancelled:
        _print_error("CANCELLED", "操作已取消。")
        return EXIT_CANCELLED
    except JianYinError as error:
        _print_error(getattr(error, "code", "JIANYIN_ERROR"), str(error))
        return EXIT_ERROR
    except KeyboardInterrupt:
        _print_error("CANCELLED", "操作已取消。")
        return EXIT_CANCELLED
    except Exception:
        _print_error("INTERNAL_ERROR", "操作未完成；未写入额外输出。")
        return EXIT_ERROR


def _print_error(code: str, message: str) -> None:
    print(json.dumps({"status": "error", "code": code, "message": message}, ensure_ascii=False), file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
