from collections import deque

_durations_ms: deque[float] = deque(maxlen=500)


def record_duration(ms: float) -> None:
    _durations_ms.append(ms)


def average_duration_ms() -> float | None:
    if not _durations_ms:
        return None
    return sum(_durations_ms) / len(_durations_ms)


def sample_count() -> int:
    return len(_durations_ms)
