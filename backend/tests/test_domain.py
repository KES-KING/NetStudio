from app.drivers import GenericReadOnlyDriver, UnsupportedCapability
from app.fixtures import build_fixture


def test_fixture_keeps_logical_interfaces_out_of_physical_ports():
    device = build_fixture()
    assert len(device.physical_ports) == 28
    bound_interface_ids = {binding.interface_id for binding in device.bindings}
    assert "Vlan10" not in {interface.name for interface in device.interfaces if interface.id in bound_interface_ids}
    assert {"Vlan10", "Loopback0", "Port-channel1"}.issubset({interface.name for interface in device.interfaces})


def test_fixture_port_ids_are_stable_and_explicitly_bound():
    device = build_fixture()
    assert device.physical_ports[0].id == "dev-demo-01-physical-01"
    assert device.bindings[0].physical_port_id == device.physical_ports[0].id
    assert device.bindings[0].binding_quality == "explicit"


def test_representative_48_plus_4_fixture_is_available():
    device = build_fixture("generic-lab-48rj45-4sfp", access_count=48)
    assert len(device.physical_ports) == 52
    assert len([port for port in device.physical_ports if port.group == "uplink"]) == 4
    assert device.model == "generic-lab-48rj45-4sfp"


def test_generic_driver_does_not_fake_write_success():
    driver = GenericReadOnlyDriver(build_fixture())
    capabilities = driver.discover_capabilities(None)
    assert capabilities["interface.access_vlan.set"]["effective_allowed"] is False
    try:
        driver.build_plan({}, {})
    except UnsupportedCapability as error:
        assert str(error) == "config.plan"
    else:
        raise AssertionError("read-only driver must reject config planning")
