export type Reachability = "reachable" | "unreachable" | "unknown";
export type PortState = "up" | "down" | "disabled" | "unknown";
export type HealthState =
  | "ok"
  | "warning"
  | "critical"
  | "unknown"
  | "unsupported";
export type PhysicalPort = {
  id: string;
  component_id: string;
  label: string;
  connector: "rj45" | "sfp" | "qsfp" | "management" | "console" | "unknown";
  group: string;
  ordinal: number;
  verified_layout: boolean;
  parent_port_id: string | null;
  description: string | null;
};
export type Interface = {
  id: string;
  name: string;
  kind: string;
  if_index: number | null;
};
export type DeviceCollector =
  | "external"
  | "auto"
  | "linux_ssh"
  | "huawei_vrp"
  | "cisco_ios"
  | "cisco_iosxe"
  | "cisco_nxos"
  | "juniper_junos";
export type DeviceManagementMode =
  | "standalone"
  | "controller_managed"
  | "cloud_managed"
  | "local_managed"
  | "unknown";
export type ProfileResolutionStatus =
  | "unresolved"
  | "matched"
  | "conflict"
  | "unsupported"
  | "manual_resolution_required"
  | "infrastructure_adapter"
  | "external";
export type Device = {
  id: string;
  name: string;
  management_address: string;
  site: string;
  device_type: "switch" | "router" | "firewall" | "server" | "other";
  vendor: string;
  model: string;
  platform: string;
  serial: string;
  os_version: string;
  read_only: boolean;
  support_status: string;
  ssh_port: number;
  collector: DeviceCollector;
  resolved_collector?: DeviceCollector | null;
  driver_version?: string | null;
  configured_profile_id?: string | null;
  resolved_profile_id?: string | null;
  profile_revision?: number | null;
  management_mode?: DeviceManagementMode;
  profile_resolution_status?: ProfileResolutionStatus;
  ssh_profile?: "auto" | "standard" | "huawei_legacy" | "legacy_sha1" | "legacy_cbc" | "advanced";
  allow_legacy_ssh?: boolean;
  ssh_algorithms?: Record<string, string[]>;
  snmp_configured?: boolean;
  credential_configured: boolean;
  host_key_fingerprint: string | null;
  inventory_observed_at: string | null;
  inventory_source: string | null;
  components: { id: string; label: string; kind: string; slot?: string }[];
  physical_ports: PhysicalPort[];
  interfaces: Interface[];
  bindings: {
    id: string;
    physical_port_id: string;
    interface_id: string;
    binding_quality: string;
  }[];
};
export type Sample = {
  interface_id: string;
  admin_up: boolean | null;
  oper_up: boolean | null;
  capacity_bps: number | null;
  rx_bps: number | null;
  tx_bps: number | null;
  quality: string;
  rate_reason: string | null;
  rate_interval_seconds?: number | null;
  duplex: string;
  errors: number | null;
  discards: number | null;
  tx_errors?: number | null;
  tx_discards?: number | null;
  pvid?: number | null;
  access_vlan: number | null;
  vlan_mode: string;
  poe_watts: number | null;
  transceiver_present: boolean | null;
  transceiver_model: string | null;
  addresses: string[];
  vrf: string | null;
};
export type Telemetry = {
  observed_at: string;
  received_at: string;
  source: string;
  stale_after_seconds: number;
  reachability: Reachability;
  error: string | null;
  interfaces: Sample[];
  neighbors?: { id: string; interface_id: string; label: string; addresses?: string[]; evidence: string }[];
  health: {
    status: HealthState;
    evaluation: string | null;
    cpu_percent: number | null;
    memory_percent: number | null;
    temperature_c: number | null;
    uptime_seconds: number | null;
    fan: string | null;
    power_supply: string | null;
    poe_watts: number | null;
    alerts: string[];
  };
};
export type TopologyNode = {
  id: string;
  name: string;
  kind: string;
  interface_id?: string;
  endpoint_id?: string;
  resolution_status?: string;
  observed_at?: string | null;
  detail: string;
  vrf?: string;
  vlan?: number;
};
export type Projection = {
  device: Device;
  telemetry: Telemetry | null;
  endpoints?: import("./topology").EndpointCollection;
  data_state: "no_data" | "current" | "stale" | "error" | "unreachable";
  reachability: Reachability;
  health_status: HealthState;
  ports: {
    counts: Record<PortState, number>;
    total: number;
    port_states: Record<string, PortState>;
    active_ratio: number | null;
    rx_bps: number | null;
    tx_bps: number | null;
    traffic_interface_ids: string[];
    measured_interfaces: number;
    traffic_scope: string;
  };
  topology: {
    nodes: TopologyNode[];
    links: {
      source: string;
      target: string;
      relation: "l3" | "l2" | "physical" | "endpoint";
      evidence: string;
    }[];
    observed_at: string | null;
    source: string | null;
  };
  traffic: {
    at: string;
    rx_bps: number | null;
    tx_bps: number | null;
    measured_interfaces: number;
  }[];
  last_success_at: string | null;
  history_truncated?: boolean;
};
export type Overview = {
  devices: Projection[];
  generated_at: string;
  range_minutes: number;
};
export type Session = {
  user_id: string;
  username: string;
  display_name: string;
  avatar_version: string | null;
  roles: UserRole[];
  site_ids: string[];
  permissions: string[];
  csrf_token: string;
};
export type SSHTicket = {
  id: string;
  websocket_path: string;
  expires_in: number;
};
export type DriverCommand = {
  text: string;
  group: "fast" | "health" | "network" | "inventory";
  parser: string;
  reference: string;
  required: boolean;
  privilege: string;
  timeout_seconds: number;
  max_bytes: number;
  parser_version: string;
};
export type DriverImplementationStatus =
  | "catalog_only"
  | "implemented"
  | "blocked"
  | "unsupported_by_protocol"
  | "unsupported_by_policy"
  | "retired";
export type DriverVerificationStatus =
  | "not_tested"
  | "unit_verified"
  | "fixture_verified"
  | "transport_lab_validated"
  | "physical_validated";
export type DriverReleaseStatus =
  | "hidden"
  | "experimental"
  | "candidate"
  | "supported";
export type DriverAliasPolicy =
  | "read_compatibility_alias_with_identity_revalidation"
  | "conditional_identity_match"
  | "manual_resolution_required";
export type DriverAlias = {
  id: string;
  target_profile_id: string | null;
  policy: DriverAliasPolicy;
  automatic: boolean;
};
export type DriverIdentitySummary = {
  vendors: string[];
  os_families: string[];
  management_modes: string[];
  model_patterns: string[];
  version_constraints: string[];
};
export type DriverTransportSummary = {
  state:
    | "implemented"
    | "planned"
    | "blocked"
    | "unsupported_by_protocol"
    | "unsupported_by_policy";
  security: string[];
  versions: string[];
  decision_gate: string | null;
};
export type DriverCapabilitySummary = {
  group: DriverCommand["group"];
  fields: string[];
  sources: ("ssh" | "snmp" | "api")[];
  verification_status: DriverVerificationStatus;
};
export type DriverAcceptanceSummary = {
  highest_level: DriverVerificationStatus;
  matching_unexpired_records: number;
  production_accepted: boolean;
};
export type DeviceCapabilityObservation = {
  profile_id: string;
  profile_revision: number;
  transport: "ssh" | "snmp" | "api";
  capability_id: string;
  status: string;
  reason_code: string | null;
  checked_at: string;
  expires_at: string;
  evidence_digest: string | null;
  stale: boolean;
};
export type DeviceCompatibility = {
  device_id: string;
  configured_profile_id: string | null;
  legacy_collector_id: string | null;
  resolved_profile_id: string | null;
  profile_revision: number | null;
  management_mode: DeviceManagementMode;
  resolution_status: ProfileResolutionStatus;
  resolution_confidence: number;
  resolution_conflicts: string[];
  identity_evidence: Partial<{
    vendor: string;
    model: string;
    os_family: string;
    os_version: string;
    hardware_revision: string;
    sys_object_id: string;
    management_mode: DeviceManagementMode;
  }>;
  resolved_at: string | null;
  implementation_status: DriverImplementationStatus | null;
  verification_status: DriverVerificationStatus;
  release_status: DriverReleaseStatus;
  runtime_collection_ready: boolean;
  capabilities: DeviceCapabilityObservation[];
  acceptance: DriverAcceptanceSummary;
};
export type DriverAcceptanceRecord = {
  source_revision: string;
  profile_id: string;
  profile_revision: number;
  vendor: string;
  model_family: string;
  exact_model: string;
  hardware_revision: string;
  os_family: string;
  os_version: string;
  management_mode: DeviceManagementMode;
  transport: "ssh" | "snmp" | "api";
  security_profile: string;
  capability_id: string;
  parser_version: string;
  test_suite_revision: string;
  validation_level: DriverVerificationStatus;
  result: "pass" | "fail" | "blocked" | "withdrawn";
  evidence_sha256: string;
  evidence_sanitized: true;
  observed_at: string;
  recorded_at: string;
  expires_at: string;
};
export type DriverProfileCatalogEntry = {
  schema_version: number;
  id: string;
  profile_revision: number;
  label: string;
  wave: "P0" | "P1" | "P2" | "P3" | "P4";
  aliases: string[];
  alias_policies: DriverAlias[];
  implementation_status: DriverImplementationStatus;
  verification_status: DriverVerificationStatus;
  release_status: DriverReleaseStatus;
  available: boolean;
  selectable: boolean;
  runtime_selection_id: string | null;
  identity: DriverIdentitySummary;
  transports: Partial<
    Record<"ssh" | "snmp" | "api", DriverTransportSummary>
  >;
  capabilities: Partial<Record<DriverCommand["group"], string[]>>;
  capability_summaries: DriverCapabilitySummary[];
  acceptance: DriverAcceptanceSummary;
  tested_versions: string[];
  commands: DriverCommand[];
  reason?: string;
};
export type DriverInfrastructureAdapter = {
  schema_version: number;
  id: string;
  revision: number;
  label: string;
  profile_kind: "infrastructure_adapter";
  role: string;
  runtime_selection_id: string;
  implementation_status: "implemented";
  verification_status: DriverVerificationStatus;
  release_status: DriverReleaseStatus;
  available: boolean;
  selectable: boolean;
  transports: Partial<
    Record<"ssh" | "snmp" | "api", DriverTransportSummary>
  >;
  capabilities: Partial<Record<DriverCommand["group"], string[]>>;
  acceptance: DriverAcceptanceSummary;
  tested_versions: string[];
  not_equivalent_to: string[];
  commands: DriverCommand[];
};
export type DriverCatalogEntry = {
  id: string;
  label: string;
  available: boolean;
  validation_level: string;
  tested_versions: string[];
  capabilities?: Partial<Record<DriverCommand["group"], string[]>>;
  commands: DriverCommand[];
  reason?: string;
  profile_kind?:
    | "driver_profile"
    | "infrastructure_adapter"
    | "legacy_unresolved";
  profile_schema_version?: number;
  canonical_profile_id?: string | null;
  profile_revision?: number | null;
  implementation_status?: DriverImplementationStatus;
  verification_status?: DriverVerificationStatus;
  release_status?: DriverReleaseStatus;
  selectable?: boolean;
  runtime_selection_id?: string | null;
  identity?: DriverIdentitySummary | null;
  transports?: Partial<
    Record<"ssh" | "snmp" | "api", DriverTransportSummary>
  >;
  acceptance?: DriverAcceptanceSummary;
  aliases?: string[];
  alias_policies?: DriverAlias[];
  resolution_status?:
    | "canonical"
    | "alias"
    | "manual_resolution_required"
    | "unknown";
};
export type DriverCatalog = {
  version: string;
  template_version: string;
  data_contract?: Partial<Record<DriverCommand["group"], string[]>>;
  drivers: DriverCatalogEntry[];
  schema_version?: number;
  catalog_revision?: string;
  profiles?: DriverProfileCatalogEntry[];
  infrastructure_adapters?: DriverInfrastructureAdapter[];
  aliases?: DriverAlias[];
  unresolved_aliases?: DriverAlias[];
};
export type Job = {
  id: string;
  kind: string;
  device_id: string;
  status: string;
  created_at: string;
  error_code: string | null;
  result_code: string | null;
};
export type AuditEvent = {
  id: string;
  user_id: string;
  device_id: string | null;
  event: string;
  outcome: string;
  session_id: string | null;
  occurred_at: string;
  username: string | null;
  roles: UserRole[] | null;
  target_type: string | null;
  target_id: string | null;
  request_id: string | null;
  method: string | null;
  route: string | null;
  remote_address: string | null;
  user_agent: string | null;
  status_code: number | null;
  duration_ms: number | null;
  details: Record<string, unknown>;
};

export type UserRole = "viewer" | "engineer" | "superadmin";
export type UserProfile = {
  id: string;
  username: string;
  display_name: string;
  role: UserRole;
  sites: string[];
  enabled: boolean;
  avatar_version: string | null;
  created_at: string | null;
  updated_at: string | null;
  reauthenticate?: boolean;
};
export type CursorPage<T> = { items: T[]; next_cursor: string | null };
export type NetworkProbeInterface = { name: string; mac: string; addresses: string[] };
export type NetworkProbeAgent = { id: string; name: string; site: string; enabled: boolean; online: boolean;
  interfaces: NetworkProbeInterface[]; enrolled_at: string; last_seen_at: string | null; revoked_at: string | null };
export type NetworkProbeProposal = { id: string; site: string; vlan: number; vrf: string | null; vrf_known: boolean;
  network: string; evidence_fingerprint: string; conflict: boolean; requires_narrowing: boolean;
  evidence: { device_id: string; device_name: string; interface_id: string; address: string; observed_at: string | null }[] };
export type NetworkProbeScope = { id: string; agent_id: string; site: string; vlan: number; vrf: string | null;
  interface_name: string; source_ip: string; source_cidr: string; target_cidrs: string[]; interval_seconds: number;
  enabled: boolean; status: "active" | "disabled" | "needs_review"; next_due_at: string; last_started_at: string | null;
  last_completed_at: string | null; last_success_at: string | null; last_error: string | null };
export type NetworkProbeRun = { id: string; scope_id: string; status: string; target_count: number; reply_count: number;
  matched_count: number; unknown_count: number; duration_ms: number; error_code: string | null; completed_at: string };
export type NetworkProbeState = { agents: NetworkProbeAgent[]; sites?: string[]; proposals: NetworkProbeProposal[]; scopes: NetworkProbeScope[];
  runs: NetworkProbeRun[]; defaults: { interval_seconds: number; max_range_prefix: number; max_targets: number;
    max_rate_pps: number; heartbeat_seconds: number } };
