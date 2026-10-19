import { api, hasSessionToken } from "./api";

type Activity = {
  action: "page.view" | "inventory.filter" | "port.select" | "topology.select";
  page: "dashboard" | "device" | "jobs" | "audit" | "account";
  device_id?: string;
  port_id?: string;
  node_id?: string;
  q?: string;
  type?: string;
  status?: string;
  minutes?: number;
};

// Supplemental, explicitly client-reported UI activity. Authoritative mutations
// are audited by the server; no keystrokes, form secrets or terminal data here.
export function recordActivity(value: Activity) {
  if (!hasSessionToken()) return;
  void api("/api/v1/activity", { method: "POST", body: JSON.stringify(value) }).catch(() => {
    // A transient activity failure must not replay an action or block navigation.
    // Authentication failures are still handled centrally by api().
  });
}
