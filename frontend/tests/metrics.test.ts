import { describe, expect, it } from "vitest";
import type { PhysicalPort, Projection } from "../lib/contracts";
import {
  filterDevices,
  formatRate,
  physicalPorts,
  summarize,
  displayProjection,
  sampleForPort,
} from "../lib/metrics";
import { capacityData, trafficOption } from "../lib/charts";

function row(): Projection {
  const port = (
    id: string,
    connector: PhysicalPort["connector"],
    parent: string | null = null,
  ): PhysicalPort => ({
    id,
    connector,
    component_id: "chassis",
    label: id,
    group: "test",
    ordinal: 1,
    verified_layout: false,
    parent_port_id: parent,
    description: null,
  });
  return {
    device: {
      id: "one",
      name: "Core",
      management_address: "192.0.2.1",
      device_type: "switch",
      site: "test",
      vendor: "",
      model: "",
      platform: "",
      serial: "",
      os_version: "",
      read_only: true,
      support_status: "generic_readonly",
      ssh_port: 22,
      collector: "external",
      credential_configured: false,
      host_key_fingerprint: null,
      inventory_observed_at: null,
      inventory_source: null,
      components: [{ id: "chassis", kind: "chassis", label: "Test" }],
      physical_ports: [
        port("p1", "rj45"),
        port("p2", "qsfp"),
        port("child", "qsfp", "p2"),
        port("console", "console"),
      ],
      interfaces: [{ id: "i1", name: "eth1", kind: "ethernet", if_index: 1 }],
      bindings: [
        {
          id: "binding",
          physical_port_id: "child",
          interface_id: "i1",
          binding_quality: "explicit",
        },
      ],
    },
    data_state: "current",
    reachability: "reachable",
    health_status: "unknown",
    last_success_at: null,
    topology: { nodes: [], links: [], observed_at: null, source: null },
    ports: {
      counts: { up: 1, down: 0, disabled: 0, unknown: 1 },
      total: 2,
      traffic_interface_ids: ["i1"],
      port_states: { p1: "up", p2: "unknown" },
      active_ratio: 50,
      rx_bps: 800,
      tx_bps: 700,
      measured_interfaces: 1,
      traffic_scope: "Test physical interfaces",
    },
    telemetry: {
      observed_at: "2026-01-01T00:00:00Z",
      stale_after_seconds: 120,
      received_at: "2026-01-01T00:00:00Z",
      source: "manual",
      reachability: "reachable",
      error: null,
      health: {
        status: "unknown",
        evaluation: null,
        cpu_percent: null,
        memory_percent: null,
        temperature_c: null,
        uptime_seconds: null,
        fan: null,
        power_supply: null,
        poe_watts: null,
        alerts: [],
      },
      interfaces: [
        {
          interface_id: "i1",
          capacity_bps: 1000,
          rx_bps: 800,
          tx_bps: 700,
          quality: "ok",
          admin_up: true,
          oper_up: true,
          rate_reason: null,
          duplex: "full",
          errors: null,
          discards: null,
          access_vlan: null,
          vlan_mode: "unknown",
          poe_watts: null,
          transceiver_present: null,
          transceiver_model: null,
          addresses: [],
          vrf: null,
        },
      ],
    },
    traffic: [
      {
        at: "2026-01-01T00:00:00Z",
        rx_bps: 800,
        tx_bps: null,
        measured_interfaces: 1,
      },
    ],
  };
}
describe("shared measurement projections", () => {
  it("preserves missing vs measured zero", () => {
    expect(formatRate(null)).toBe("Veri yok");
    expect(formatRate(0)).toBe("0 bit/s");
  });
  it("filters the same complete device scope by name/IP/type/status", () => {
    expect(
      filterDevices([row()], "192.0.2", "switch", "reachable"),
    ).toHaveLength(1);
    expect(filterDevices([row()], "Core", "router", "")).toHaveLength(0);
  });
  it("does not count console or breakout children", () => {
    expect(physicalPorts(row()).map((p) => p.id)).toEqual(["p1", "p2"]);
  });
  it("keeps unknowns in the stated denominator", () => {
    expect(summarize([row()]).activeRatio).toBe(50);
    const unknown = row();
    unknown.ports.counts = { up: 0, down: 0, disabled: 0, unknown: 2 };
    expect(summarize([unknown]).activeRatio).toBeNull();
  });
  it("never combines duplex directions for utilization", () => {
    expect(capacityData([row()])[0]).toMatchObject({ rx: 80, tx: 70 });
    const stale = row();
    stale.data_state = "stale";
    expect(capacityData([stale])).toEqual([]);
  });
  it("keeps stable per-device series ids and null samples", () => {
    const option = trafficOption([row()]);
    expect(JSON.stringify(option)).toContain('"id":"one-rx"');
    expect(JSON.stringify(option)).toContain("null");
  });
  it("expires cached observations when network refresh fails or time advances", () => {
    expect(
      displayProjection(row(), true, Date.parse("2026-01-01T00:00:01Z")),
    ).toMatchObject({
      health_status: "unknown",
      reachability: "unknown",
      ports: { rx_bps: null, active_ratio: null },
    });
    expect(
      displayProjection(row(), false, Date.parse("2026-01-01T00:03:00Z"))
        .data_state,
    ).toBe("stale");
  });
  it("breakout details and capacity use the child interface identity", () => {
    expect(
      sampleForPort(row(), row().device.physical_ports[1]).map(
        (s) => s.interface_id,
      ),
    ).toEqual(["i1"]);
  });
});
