from datetime import timedelta

import pytest
from app.contracts import ManagedDevice, Telemetry
from app.database import now
from app.telemetry import normalize, physical_summary
from conftest import inventory, observation


def batch(at, incoming, outgoing, **changes):
    return Telemetry.model_validate(observation(at, interfaces=[{"interface_id": "if1", "in_octets": incoming, "out_octets": outgoing, **changes}]))


def test_counter_rates_are_bits_per_second_and_directions_separate():
    at = now() - timedelta(seconds=30)
    first = normalize(batch(at, 100, 1000), None)
    assert first["interfaces"][0]["rx_bps"] is None
    second = normalize(batch(at + timedelta(seconds=10), 200, 3000), first)["interfaces"][0]
    assert second["rx_bps"] == 80 and second["tx_bps"] == 1600


@pytest.mark.parametrize("elapsed,incoming,discontinuity,reason", [(10, 2, None, "counter_reset_or_wrap"), (500, 200, None, "invalid_or_missing_interval"), (0, 200, None, "invalid_or_missing_interval"), (10, 200, "reboot", "counter_discontinuity")])
def test_counter_discontinuities_fail_closed(elapsed, incoming, discontinuity, reason):
    at = now() - timedelta(seconds=600)
    first = normalize(batch(at, 100, 100), None)
    result = normalize(batch(at + timedelta(seconds=elapsed), incoming, 300, discontinuity=discontinuity), first)["interfaces"][0]
    assert result["rx_bps"] is None and result["tx_bps"] is None and result["rate_reason"] == reason


def test_breakout_parent_and_logical_interfaces_not_double_counted():
    data = inventory()
    data["physical_ports"].extend([{**data["physical_ports"][0], "id": "child1", "parent_port_id": "p4"}, {**data["physical_ports"][1], "id": "child2", "parent_port_id": "p4"}])
    data["bindings"] = [{"id": "bc1", "physical_port_id": "child1", "interface_id": "if1", "binding_quality": "explicit"}, {"id": "bc2", "physical_port_id": "child2", "interface_id": "if2", "binding_quality": "explicit"}, {"id": "parent", "physical_port_id": "p4", "interface_id": "if3", "binding_quality": "explicit"}]
    data.pop("source"); data.pop("observed_at")
    device = ManagedDevice(id="test", name="test", management_address="127.0.0.1", site="lab", vendor="", platform="", model="", os_version="", serial="", support_status="generic_readonly", **data)
    summary = physical_summary(device, normalize(Telemetry.model_validate(observation()), None), False)
    assert summary["total"] == 4
    assert summary["counts"]["up"] == 1
    assert summary["traffic_interface_ids"] == ["if1", "if2"]
    assert summary["rx_bps"] == 800
