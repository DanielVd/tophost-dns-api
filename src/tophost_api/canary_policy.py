"""Pure policy for escalating consecutive scheduled canary failures."""

from __future__ import annotations


def transient_streak(
    current_code: int,
    previous_codes: list[int | None],
    *,
    threshold: int = 3,
) -> int:
    """Count consecutive transient results, newest previous run first.

    None means a missing/unreadable artifact and breaks the streak.
    Authentication, protocol drift and recovery also break the streak.
    """
    if threshold < 1:
        raise ValueError("threshold must be positive")

    if current_code != 10:
        return 0

    count = 1
    for code in previous_codes:
        if code != 10:
            break
        count += 1
        if count >= threshold:
            break
    return count
