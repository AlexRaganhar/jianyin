"""Q4 ONNX adapter for OpenAI Privacy Filter.

The graph is run on overlapping token windows.  Per-token log probabilities
are averaged over every window that covers a token, then a single Viterbi
decode is applied to the whole document.  This follows the official runtime's
window/aggregation model while avoiding independent chunk-boundary decisions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from ..config import MODEL_REPOSITORY, MODEL_REVISION, MODEL_VARIANT, ModelConfig
from ..detection.base import (
    CancelCheck,
    Detection,
    DetectionBatch,
    ProgressCallback,
    check_cancelled,
    emit_progress,
)
from ..errors import ModelError, ModelInferenceError, ModelOutputError, OperationCancelled
from .download import ensure_model
from .labels import normalize_category
from .viterbi import (
    LabelInfo,
    ViterbiDecoder,
    build_label_info,
    labels_to_token_spans,
    load_viterbi_biases,
    parse_id2label,
    trim_and_deduplicate_spans,
)
from .windows import build_windows

SessionFactory = Callable[[Path], Any]
TokenizerFactory = Callable[[Path], Any]


@dataclass(frozen=True)
class _Runtime:
    model_dir: Path
    session: Any
    tokenizer: Any
    input_dtypes: Mapping[str, np.dtype[Any]]
    output_name: str
    label_info: LabelInfo
    decoder: ViterbiDecoder | None
    config: ModelConfig


def _read_json(path: Path) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ModelError(f"无法读取模型元数据：{path.name}") from error
    if not isinstance(payload, Mapping):
        raise ModelError(f"模型元数据格式无效：{path.name}")
    return payload


def _onnx_dtype(value_type: str) -> np.dtype[Any]:
    if "int64" in value_type:
        return np.dtype(np.int64)
    if "int32" in value_type:
        return np.dtype(np.int32)
    if "bool" in value_type:
        return np.dtype(np.bool_)
    raise ModelError(f"ONNX 模型输入类型不受支持：{value_type}")


def _log_softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - np.max(logits, axis=-1, keepdims=True)
    return shifted - np.log(np.sum(np.exp(shifted), axis=-1, keepdims=True))


def _create_cpu_session(model_path: Path) -> Any:
    try:
        import onnxruntime as ort
    except ModuleNotFoundError as error:
        raise ModelInferenceError(
            "未安装 ONNX Runtime。请在项目目录执行 `python -m pip install -e .`。"
        ) from error
    try:
        return ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    except Exception as error:
        raise ModelInferenceError("无法加载 Q4 ONNX 模型，请检查模型文件完整性。") from error


def _load_fast_tokenizer(tokenizer_path: Path) -> Any:
    try:
        from tokenizers import Tokenizer
    except ModuleNotFoundError as error:
        raise ModelInferenceError(
            "未安装 tokenizers。请在项目目录执行 `python -m pip install -e .`。"
        ) from error
    try:
        return Tokenizer.from_file(str(tokenizer_path))
    except Exception as error:
        raise ModelInferenceError("无法加载 Q4 ONNX 模型所需的 tokenizer.json。") from error


_TRAILING_PUNCTUATION = set(".,;:!?，。；：！？、）】》」』\"'")
_LEADING_PUNCTUATION = set("（【《「『\"'")


def _trim_punctuation(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start] in _LEADING_PUNCTUATION:
        start += 1
    while end > start and text[end - 1] in _TRAILING_PUNCTUATION:
        end -= 1
    return start, end


class OnnxPrivacyFilter:
    """Lazy CPU-only Q4 ONNX detector shared by CLI and GUI."""

    def __init__(
        self,
        config: ModelConfig | None = None,
        *,
        session_factory: SessionFactory | None = None,
        tokenizer_factory: TokenizerFactory | None = None,
    ) -> None:
        self.config = (config or ModelConfig()).normalized()
        self._session_factory = session_factory or _create_cpu_session
        self._tokenizer_factory = tokenizer_factory or _load_fast_tokenizer
        self._runtime: _Runtime | None = None

    @property
    def metadata(self) -> dict[str, Any]:
        model_dir = self.config.model_dir
        if self._runtime is not None:
            model_dir = str(self._runtime.model_dir)
        return {
            "runtime": "onnxruntime-q4",
            "model_repository": MODEL_REPOSITORY,
            "model_revision": MODEL_REVISION,
            "model_variant": MODEL_VARIANT,
            "model_dir": str(model_dir) if model_dir else "",
            "window_size": self.config.window_size,
            "overlap_tokens": self.config.overlap_tokens,
            "decode_mode": self.config.decode_mode,
            "device": "cpu",
        }

    def reset(self) -> None:
        self._runtime = None

    def _get_runtime(self, progress: ProgressCallback | None = None) -> _Runtime:
        if self._runtime is not None:
            return self._runtime
        model_dir = ensure_model(
            self.config.model_dir,
            allow_download=not self.config.offline,
            offline=self.config.offline,
            progress=progress,
        )
        config = _read_json(model_dir / "config.json")
        class_names = parse_id2label(config)
        label_info = build_label_info(class_names)
        try:
            tokenizer = self._tokenizer_factory(model_dir / "tokenizer.json")
        except ModelError:
            raise
        except Exception as error:
            raise ModelInferenceError("无法加载模型所需的 tokenizer.json。") from error
        session = self._session_factory(model_dir / "onnx" / "model_q4.onnx")
        inputs = {item.name: item for item in session.get_inputs()}
        missing = {"input_ids", "attention_mask"} - set(inputs)
        if missing:
            raise ModelInferenceError("Q4 ONNX 模型缺少 input_ids 或 attention_mask 输入。")
        outputs = list(session.get_outputs())
        if not outputs:
            raise ModelInferenceError("Q4 ONNX 模型没有可用输出。")
        output_name = next((item.name for item in outputs if item.name == "logits"), outputs[0].name)
        input_dtypes = {
            name: _onnx_dtype(inputs[name].type) for name in ("input_ids", "attention_mask")
        }
        biases = load_viterbi_biases(model_dir / "viterbi_calibration.json")
        decoder = (
            ViterbiDecoder(label_info, biases) if self.config.decode_mode == "viterbi" else None
        )
        self._runtime = _Runtime(
            model_dir=model_dir,
            session=session,
            tokenizer=tokenizer,
            input_dtypes=input_dtypes,
            output_name=output_name,
            label_info=label_info,
            decoder=decoder,
            config=self.config,
        )
        return self._runtime

    def _predict_window(self, runtime: _Runtime, token_ids: Sequence[int]) -> np.ndarray:
        input_ids = np.asarray([list(token_ids)], dtype=runtime.input_dtypes["input_ids"])
        attention_mask = np.ones(input_ids.shape, dtype=runtime.input_dtypes["attention_mask"])
        try:
            result = runtime.session.run(
                [runtime.output_name],
                {"input_ids": input_ids, "attention_mask": attention_mask},
            )
        except Exception as error:
            raise ModelInferenceError("Q4 ONNX 模型推理失败，请检查模型和本机运行环境。") from error
        if not result:
            raise ModelInferenceError("Q4 ONNX 模型未返回 logits。")
        logits = np.asarray(result[0], dtype=np.float32)
        expected_classes = len(runtime.label_info.token_to_span_label)
        if (
            logits.ndim != 3
            or logits.shape[0] != 1
            or logits.shape[1] != len(token_ids)
            or logits.shape[2] != expected_classes
        ):
            raise ModelInferenceError("Q4 ONNX 模型输出形状与模型配置不一致。")
        return _log_softmax(logits[0])

    def detect(
        self,
        text: str,
        *,
        progress: ProgressCallback | None = None,
        cancel: CancelCheck | None = None,
    ) -> DetectionBatch:
        check_cancelled(cancel)
        if not isinstance(text, str):
            raise ModelInferenceError("输入文本类型无效。")
        if len(text) > self.config.max_characters:
            raise ModelInferenceError(
                f"文档超过 {self.config.max_characters:,} 字符，请拆分后再处理。"
            )
        if not text:
            return DetectionBatch(text=text, detections=(), stats={"token_count": 0, "window_count": 0})

        try:
            runtime = self._get_runtime(progress)
            encoded = runtime.tokenizer.encode(text, add_special_tokens=False)
            token_ids = tuple(int(token) for token in encoded.ids)
            offsets = tuple((int(start), int(end)) for start, end in encoded.offsets)
            if len(token_ids) != len(offsets):
                raise ModelOutputError("分词结果与字符偏移数量不一致。")
            if not token_ids:
                return DetectionBatch(text=text, detections=(), stats={"token_count": 0, "window_count": 0})
            if len(token_ids) > self.config.max_tokens:
                raise ModelInferenceError(
                    f"文档超过 {self.config.max_tokens:,} token，请拆分后再处理。"
                )

            windows = build_windows(
                len(token_ids), self.config.window_size, self.config.overlap_tokens
            )
            class_count = len(runtime.label_info.token_to_span_label)
            totals = np.zeros((len(token_ids), class_count), dtype=np.float32)
            counts = np.zeros(len(token_ids), dtype=np.int32)

            for index, window in enumerate(windows, start=1):
                check_cancelled(cancel)
                log_probs = self._predict_window(runtime, token_ids[window.start : window.end])
                totals[window.start : window.end] += log_probs
                counts[window.start : window.end] += 1
                emit_progress(
                    progress,
                    {
                        "stage": "model_window",
                        "window_index": index,
                        "window_count": len(windows),
                        "token_count": len(token_ids),
                    },
                )

            if not np.all(counts > 0):
                raise ModelInferenceError("推理窗口没有覆盖完整文档。")
            averaged = totals / counts[:, None]
            labels = (
                runtime.decoder.decode(averaged)
                if runtime.decoder is not None
                else np.argmax(averaged, axis=1).astype(int).tolist()
            )
            token_spans = labels_to_token_spans(labels, runtime.label_info)
            candidate_spans: list[tuple[int, int, int]] = []
            for label, token_start, token_end in token_spans:
                if not (0 <= label < len(runtime.label_info.span_class_names)):
                    continue
                if not (0 <= token_start < token_end <= len(offsets)):
                    continue
                char_start = offsets[token_start][0]
                char_end = offsets[token_end - 1][1]
                if 0 <= char_start < char_end <= len(text):
                    candidate_spans.append((label, char_start, char_end))
            character_spans = trim_and_deduplicate_spans(candidate_spans, text)

            detections: list[Detection] = []
            for label, start, end in character_spans:
                raw_category = runtime.label_info.span_class_names[label]
                if raw_category == "O":
                    continue
                start, end = _trim_punctuation(text, start, end)
                if end <= start:
                    continue
                category = normalize_category(raw_category)
                detections.append(
                    Detection(
                        category=category,
                        start=start,
                        end=end,
                        text=text[start:end],
                        source="model",
                        priority=60,
                    )
                )

            warnings: list[str] = []
            if not detections:
                warnings.append("模型未识别到敏感信息；请人工复核，尤其是中文姓名和地址。")
            stats = {
                "token_count": len(token_ids),
                "window_count": len(windows),
                "detected_span_count": len(detections),
                "decode_mode": self.config.decode_mode,
            }
            return DetectionBatch(
                text=text,
                detections=tuple(detections),
                warnings=tuple(warnings),
                stats=stats,
            )
        except (ModelError, ModelOutputError, OperationCancelled):
            raise
        except Exception as error:
            raise ModelInferenceError("Q4 ONNX 脱敏识别失败，请检查模型目录和运行环境。") from error
