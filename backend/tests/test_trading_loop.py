import pytest

from backend.trading_api import get_poll_delay_seconds


@pytest.mark.parametrize(
    ("interval", "expected"),
    [
        ("1m", 15),
        ("5m", 75),
        ("15m", 225),
        ("30m", 300),
        ("1h", 300),
        ("4h", 300),
        ("1d", 300),
    ],
)
def test_poll_delay_is_timeframe_aware_and_bounded(interval, expected):
    assert get_poll_delay_seconds(interval) == expected


def test_poll_delay_rejects_unknown_interval():
    with pytest.raises(ValueError, match="Unsupported trading interval"):
        get_poll_delay_seconds("2h")
