"""Safe, user-facing error types for 笺隐.

Messages are deliberately written so that they never contain source text,
replacement values, passwords, or model input content.  Callers may display
``str(error)`` without leaking case material.
"""

from __future__ import annotations


class JianYinError(Exception):
    """Base class for every expected 笺隐 failure."""

    code = "JIANYIN_ERROR"
    default_message = "操作未完成。"

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.default_message
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message


class ConfigurationError(JianYinError):
    code = "CONFIG_INVALID"
    default_message = "配置无效，请检查本地设置。"


class UserInputError(JianYinError):
    code = "INPUT_INVALID"
    default_message = "输入参数无效。"


class ModelError(JianYinError):
    code = "MODEL_ERROR"
    default_message = "模型运行时出错。"


class ModelNotFoundError(ModelError):
    code = "MODEL_MISSING"
    default_message = "未找到本地模型。请下载模型或指定 --model-dir。"


class ModelDownloadError(ModelError):
    code = "MODEL_DOWNLOAD_FAILED"
    default_message = "无法下载模型。请检查网络，或手动放置 Q4 ONNX 文件。"


class ModelInferenceError(ModelError):
    code = "MODEL_INFERENCE_FAILED"
    default_message = "模型推理失败，未写入任何输出。"


class ModelOutputError(ModelError):
    code = "MODEL_OUTPUT_INVALID"
    default_message = "模型输出与原文不一致，已拒绝写入可能错位的结果。"


class DocumentError(JianYinError):
    code = "DOCUMENT_ERROR"
    default_message = "文档无法处理。"


class UnsupportedDocumentError(DocumentError):
    code = "DOCUMENT_UNSUPPORTED"
    default_message = "不支持该文件类型。"


class OcrError(DocumentError):
    code = "OCR_FAILED"
    default_message = "本地 OCR 转换未完成。"


class RuleError(JianYinError):
    code = "RULE_INVALID"
    default_message = "脱敏规则无效。"


class PolicyError(RuleError):
    code = "POLICY_INVALID"
    default_message = "策略规则文件无效。"


class DraftError(RuleError):
    code = "DRAFT_INVALID"
    default_message = "规则草稿无效。"


class WorkspaceError(JianYinError):
    code = "WORKSPACE_ERROR"
    default_message = "本地工作区无法读写。"


class RestoreError(JianYinError):
    code = "RESTORE_MISMATCH"
    default_message = "脱敏文本已被改动，无法按映射安全还原；未写入还原文件。"


class OperationCancelled(JianYinError):
    code = "CANCELLED"
    default_message = "操作已取消。"
