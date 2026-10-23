"""Small real-model smoke test; prints aggregate counts only."""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jianyin_app.config import ChineseRuleOptions, DetectionOptions, ModelConfig  # noqa: E402
from jianyin_app.detection.chinese_rules import ChineseRuleDetector  # noqa: E402
from jianyin_app.detection.composite import CompositeDetector  # noqa: E402
from jianyin_app.model.onnx_detector import OnnxPrivacyFilter  # noqa: E402

SAMPLE = (
    "Alice Johnson lives at 123 Main Street, Springfield. "
    "Her email is alice.johnson@example.com and phone 555-123-4567. "
    "She was born on 1990-01-02.\n\n"
    "被告人张三，男，1985年3月12日出生，住广东省深圳市南山区科技园路88号3栋502室，"
    "手机13800138000，身份证号11010519491231002X。"
)


def main() -> int:
    parser = argparse.ArgumentParser(description="笺隐真实模型冒烟测试")
    parser.add_argument("--model-dir", help="Q4 ONNX 模型目录")
    args = parser.parse_args()
    started = time.perf_counter()
    model = OnnxPrivacyFilter(ModelConfig(model_dir=args.model_dir))
    chinese = ChineseRuleDetector(ChineseRuleOptions())
    detector = CompositeDetector(
        model,
        chinese,
        options=DetectionOptions(chinese=ChineseRuleOptions()),
    )
    result = detector.detect(SAMPLE)
    elapsed = time.perf_counter() - started
    counts = Counter((item.category, item.subtype or "") for item in result.detections)
    print(f"elapsed_seconds={elapsed:.2f}")
    print(f"detected_spans={len(result.detections)}")
    print(f"windows={result.stats.get('window_count')} tokens={result.stats.get('token_count')}")
    for (category, subtype), count in sorted(counts.items()):
        print(f"{category}/{subtype or '-'}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
