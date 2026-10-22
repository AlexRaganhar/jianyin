"""Token-window construction for long-document ONNX inference."""

from __future__ import annotations

from dataclasses import dataclass

from ..errors import ConfigurationError


@dataclass(frozen=True)
class TokenWindow:
    """One half-open token interval ``[start, end)``."""

    start: int
    end: int

    @property
    def length(self) -> int:
        return self.end - self.start


def build_windows(token_count: int, window_size: int, overlap_tokens: int) -> list[TokenWindow]:
    """Cover every token at least once, with optional overlap.

    The final window is shifted left when necessary so that the tail of the
    document is fully covered.  Windows are returned in ascending order.
    """
    if token_count < 0:
        raise ConfigurationError("token 数量不能为负数。")
    if window_size <= 0:
        raise ConfigurationError("窗口大小必须为正数。")
    if overlap_tokens < 0 or overlap_tokens >= window_size:
        raise ConfigurationError("窗口重叠必须是非负数，且小于窗口大小。")
    if token_count == 0:
        return []
    if token_count <= window_size:
        return [TokenWindow(0, token_count)]

    stride = window_size - overlap_tokens
    starts = list(range(0, token_count, stride))
    if starts[-1] + window_size < token_count:
        # Defensive: normally the arithmetic above already guarantees tail
        # coverage; keep this branch for unusual stride/window combinations.
        starts.append(token_count - window_size)

    windows: list[TokenWindow] = []
    seen: set[tuple[int, int]] = set()
    for start in sorted(set(starts)):
        end = min(start + window_size, token_count)
        if end <= start:
            continue
        key = (start, end)
        if key in seen:
            continue
        seen.add(key)
        windows.append(TokenWindow(start, end))

    if not windows:
        raise ConfigurationError("无法为文档构造推理窗口。")
    covered = 0
    for window in windows:
        if window.start > covered:
            raise ConfigurationError("推理窗口没有覆盖完整文档。")
        covered = max(covered, window.end)
    if covered < token_count:
        raise ConfigurationError("推理窗口没有覆盖文档末尾。")
    return windows
