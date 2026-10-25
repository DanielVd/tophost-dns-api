import pytest

from tophost_api.canary_policy import transient_streak


@pytest.mark.parametrize(
    ("current", "history", "expected"),
    [
        (0, [10, 10], 0),
        (20, [10, 10], 0),
        (30, [10, 10], 0),
        (10, [], 1),
        (10, [10], 2),
        (10, [10, 10], 3),
        (10, [10, 10, 10], 3),
        (10, [0, 10], 1),
        (10, [20, 10], 1),
        (10, [30, 10], 1),
        (10, [None, 10], 1),
        (10, [10, None, 10], 2),
    ],
)
def test_transient_streak(current, history, expected):
    assert transient_streak(current, history) == expected


def test_transient_streak_custom_threshold():
    assert transient_streak(10, [10, 10], threshold=4) == 3


def test_transient_streak_invalid_threshold():
    with pytest.raises(ValueError):
        transient_streak(10, [], threshold=0)
