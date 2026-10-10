"""Representative non-Cisco fixtures for deterministic development."""

from __future__ import annotations

from datetime import timedelta

from .models import Device, Interface, Observation, PhysicalComponent, PhysicalPort, PortBinding, ReadQuality, utc_now


def observation(value, *, source: str = "fixture", stale_after_seconds: int = 90) -> Observation:
    now = utc_now()
    return Observation(
        value=value,
        observed_at=now,
        received_at=now,
        stale_after_seconds=stale_after_seconds,
        source=source,
        quality=ReadQuality.OK,
    )


def build_fixture(model_key: str = "generic-lab-24rj45-4sfp", access_count: int = 24) -> Device:
    device_id = "dev-demo-01"
    chassis_id = f"{device_id}-chassis"
    components = [PhysicalComponent(id=chassis_id, kind="chassis", label="Demo chassis", serial="DEMO-READONLY")]
    physical_ports: list[PhysicalPort] = []
    interfaces: list[Interface] = []
    bindings: list[PortBinding] = []

    for ordinal in range(1, access_count + 1):
        port_id = f"{device_id}-physical-{ordinal:02d}"
        interface_id = f"{device_id}-if-{ordinal:02d}"
        physical_ports.append(PhysicalPort(id=port_id, component_id=chassis_id, label=f"Gi0/{ordinal}", connector="rj45", group="access", ordinal=ordinal))
        interfaces.append(
            Interface(
                id=interface_id,
                name=f"GigabitEthernet0/{ordinal}",
                kind="ethernet",
                if_index=ordinal,
                admin_up=observation(True),
                oper_up=observation(ordinal not in {7, 19}),
                speed_mbps=observation(1000),
                access_vlan=observation(20 if ordinal % 3 else 30),
            )
        )
        bindings.append(PortBinding(id=f"binding-{ordinal:02d}", physical_port_id=port_id, interface_id=interface_id, binding_quality="explicit"))

    for uplink in range(1, 5):
        ordinal = access_count + uplink
        port_id = f"{device_id}-physical-u{uplink}"
        interface_id = f"{device_id}-if-u{uplink}"
        physical_ports.append(PhysicalPort(id=port_id, component_id=chassis_id, label=f"Te0/{uplink}", connector="sfp", group="uplink", ordinal=ordinal))
        interfaces.append(
            Interface(
                id=interface_id,
                name=f"TenGigabitEthernet0/{uplink}",
                kind="ethernet",
                if_index=ordinal,
                admin_up=observation(True),
                oper_up=observation(uplink in {1, 2}),
                speed_mbps=observation(10000),
                access_vlan=None,
            )
        )
        bindings.append(PortBinding(id=f"binding-u{uplink}", physical_port_id=port_id, interface_id=interface_id, binding_quality="explicit"))

    # Logical interfaces are deliberately present in inventory but have no physical binding.
    interfaces.extend(
        [
            Interface(id=f"{device_id}-svi-10", name="Vlan10", kind="svi", if_index=1010, admin_up=observation(True), oper_up=observation(True), speed_mbps=observation(0)),
            Interface(id=f"{device_id}-loopback-0", name="Loopback0", kind="loopback", if_index=2000, admin_up=observation(True), oper_up=observation(True), speed_mbps=observation(0)),
            Interface(id=f"{device_id}-port-channel-1", name="Port-channel1", kind="port_channel", if_index=3001, admin_up=observation(True), oper_up=observation(True), speed_mbps=observation(20000)),
        ]
    )

    return Device(
        id=device_id,
        name="SW-DEMO-01",
        management_address="192.0.2.10",
        site="LAB / Demo",
        vendor="Example Networks",
        platform="generic-lab",
        model=model_key,
        os_version="fixture-0",
        serial="DEMO-READONLY",
        read_only=True,
        support_status="demo_fixture",
        components=components,
        physical_ports=physical_ports,
        interfaces=interfaces,
        bindings=bindings,
    )

