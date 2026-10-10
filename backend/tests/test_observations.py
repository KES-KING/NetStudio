from datetime import datetime, timedelta, timezone

from app.fixtures import build_fixture
from app.observations import CounterSample, FixtureCollector, calculate_counter_rate


BASE = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)


def test_counter_rate_uses_high_capacity_octets_and_seconds():
    previous = CounterSample("if-1", 1_000, 2_000, BASE)
    current = CounterSample("if-1", 2_000, 4_000, BASE + timedelta(seconds=10))
    result = calculate_counter_rate(previous, current)
    assert result.quality == "ok"
    assert result.rx_bps == 800.0
    assert result.tx_bps == 1600.0


def test_counter_reset_creates_a_gap_instead_of_a_fake_rate():
    previous = CounterSample("if-1", 10_000, 10_000, BASE)
    current = CounterSample("if-1", 100, 120, BASE + timedelta(seconds=10))
    result = calculate_counter_rate(previous, current)
    assert result.quality == "unknown"
    assert result.rx_bps is None
    assert result.reason == "counter_reset"


def test_fixture_collector_only_returns_interfaces_and_no_network_result():
    snapshot = FixtureCollector().collect(build_fixture())
    assert snapshot.source == "fixture"
    assert snapshot.quality == "ok"
    assert len(snapshot.observations) == 28
    assert all(item.interface_name.startswith(("GigabitEthernet", "TenGigabitEthernet")) for item in snapshot.observations)
    assert all(item.oper_up.observed_at == snapshot.observed_at for item in snapshot.observations)
    assert all(item.oper_up.poll_id == snapshot.poll_id for item in snapshot.observations)
