import time
from unittest.mock import patch

import pytest

import config
import ratelimit
from ratelimit import RateLimitExceeded


@pytest.fixture
def limiter_on():
    with patch.object(config, "RATE_LIMIT_ENABLED", True):
        yield


class TestDisabledByDefault:
    def test_no_limit_when_disabled(self):
        for _ in range(config.RATE_LIMIT_PER_HOUR * 3):
            ratelimit.check("1.2.3.4")


@pytest.mark.usefixtures("limiter_on")
class TestPerClientLimit:
    def test_allows_up_to_the_limit(self):
        with patch.object(config, "RATE_LIMIT_PER_HOUR", 3):
            for _ in range(3):
                ratelimit.check("1.2.3.4")

    def test_blocks_past_the_limit(self):
        with patch.object(config, "RATE_LIMIT_PER_HOUR", 2):
            ratelimit.check("1.2.3.4")
            ratelimit.check("1.2.3.4")
            with pytest.raises(RateLimitExceeded, match="Rate limit reached"):
                ratelimit.check("1.2.3.4")

    def test_clients_are_tracked_separately(self):
        with patch.object(config, "RATE_LIMIT_PER_HOUR", 1):
            ratelimit.check("1.1.1.1")
            ratelimit.check("2.2.2.2")  # different client, not blocked

    def test_window_slides(self):
        with patch.object(config, "RATE_LIMIT_PER_HOUR", 1):
            ratelimit.check("1.2.3.4")
            # An hour and a second later the earlier request has aged out.
            with patch("ratelimit.time.time", return_value=time.time() + 3601):
                ratelimit.check("1.2.3.4")

    def test_exception_carries_retry_after(self):
        with patch.object(config, "RATE_LIMIT_PER_HOUR", 1):
            ratelimit.check("1.2.3.4")
            with pytest.raises(RateLimitExceeded) as exc_info:
                ratelimit.check("1.2.3.4")
        assert 0 < exc_info.value.retry_after <= 3600


@pytest.mark.usefixtures("limiter_on")
class TestGlobalBudget:
    def test_global_cap_blocks_every_client(self):
        with patch.object(config, "RATE_LIMIT_GLOBAL_PER_DAY", 2), \
             patch.object(config, "RATE_LIMIT_PER_HOUR", 100):
            ratelimit.check("1.1.1.1")
            ratelimit.check("2.2.2.2")
            with pytest.raises(RateLimitExceeded, match="daily query budget"):
                ratelimit.check("3.3.3.3")

    def test_global_window_is_a_day(self):
        with patch.object(config, "RATE_LIMIT_GLOBAL_PER_DAY", 1):
            ratelimit.check("1.1.1.1")
            with patch("ratelimit.time.time", return_value=time.time() + 86401):
                ratelimit.check("2.2.2.2")


class TestSnapshot:
    def test_reports_usage(self, limiter_on):
        ratelimit.check("1.1.1.1")
        snap = ratelimit.snapshot()
        assert snap["enabled"] is True
        assert snap["queries_last_24h"] == 1
        assert snap["tracked_clients"] == 1

    def test_reset_clears_state(self, limiter_on):
        ratelimit.check("1.1.1.1")
        ratelimit.reset()
        assert ratelimit.snapshot()["queries_last_24h"] == 0
