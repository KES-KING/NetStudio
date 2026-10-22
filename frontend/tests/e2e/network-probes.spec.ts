import { expect, test, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";

test.skip(!process.env.NETSTUDIO_QA, "Requires isolated QA authentication; network data is a browser fixture.");
const evidence = join(tmpdir(), "netstudio-network-probe");

async function login(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() !== "error") return;
    if (message.location().url.endsWith("/api/v1/session/me") && message.text().includes("401")) return;
    errors.push(message.text());
  });
  await page.goto("/");
  await page.getByLabel("Kullanıcı adı", { exact: true }).fill("qa-admin");
  await page.getByLabel("Parola", { exact: true }).fill("test-only-password-1234");
  await page.getByRole("button", { name: "Giriş yap", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Ağ cihazları", exact: true })).toBeVisible();
  return errors;
}

test("network probe settings expose automatic enrollment, bounded approval and responsive status", async ({ page }) => {
  const at = new Date().toISOString();
  const state = {
    agents: [{ id: "agent-1", name: "QA trunk probe", site: "", enabled: true, online: true,
      interfaces: [{ name: "eth0.10", mac: "02:00:00:00:fe:10", addresses: ["192.0.2.254/24"] }],
      enrolled_at: at, last_seen_at: at, revoked_at: null }],
    sites: ["TEST FIXTURE / isolated"],
    proposals: [{ id: "a".repeat(64), site: "TEST FIXTURE / isolated", vlan: 10, vrf: null, vrf_known: true,
      network: "192.0.2.0/24", evidence_fingerprint: "b".repeat(64), conflict: false, requires_narrowing: false,
      evidence: [{ device_id: "qa-core", device_name: "QA-Core-01", interface_id: "if-vlan10", address: "192.0.2.1/24", observed_at: at }] }],
    scopes: [{ id: "scope-1", agent_id: "agent-1", site: "TEST FIXTURE / isolated", vlan: 10, vrf: null,
      interface_name: "eth0.10", source_ip: "192.0.2.254", source_cidr: "192.0.2.254/24",
      target_cidrs: ["192.0.2.0/24"], interval_seconds: 900, enabled: true, status: "active",
      next_due_at: at, last_started_at: at, last_completed_at: at, last_success_at: at, last_error: null }],
    runs: [{ id: "run-1", scope_id: "scope-1", status: "succeeded", target_count: 252, reply_count: 7,
      matched_count: 5, unknown_count: 2, duration_ms: 4100, error_code: null, completed_at: at }],
    defaults: { interval_seconds: 900, max_range_prefix: 22, max_targets: 4096, max_rate_pps: 64, heartbeat_seconds: 15 },
  };
  const mutations: { path: string; body: Record<string, unknown> }[] = [];
  await page.route("**/api/v1/network-probes**", async (route) => {
    const request = route.request(), url = new URL(request.url()), body = request.postDataJSON?.() ?? {};
    if (request.method() === "GET" && url.pathname === "/api/v1/network-probes") return route.fulfill({ json: state });
    mutations.push({ path: url.pathname, body });
    if (request.method() === "PATCH" && url.pathname.endsWith("/agents/agent-1")) {
      state.agents[0].site = String(body.site || "");
      return route.fulfill({ json: { id: "agent-1", site: state.agents[0].site } });
    }
    if (url.pathname.endsWith("/scopes")) return route.fulfill({ status: 201, json: state.scopes[0] });
    if (url.pathname.endsWith("/runs")) return route.fulfill({ status: 202, json: { task_id: "task-1", coalesced: false } });
    return route.fulfill({ json: { status: "ok" } });
  });
  await page.setViewportSize({ width: 1536, height: 1024 });
  const errors = await login(page);
  await page.goto("/settings/network-probes");
  await expect(page.getByRole("heading", { name: "VLAN ARP probe ajanları", exact: true })).toBeVisible();
  await expect(page.locator(".probe-grid strong", { hasText: "QA trunk probe" })).toBeVisible();
  await expect(page.getByText("5 eşleşme / 7 yanıt", { exact: true })).toBeVisible();
  await expect(page.locator(".probe-facts div").filter({ hasText: "Bilinmeyen yanıt" })).toContainText("2");

  await page.getByRole("button", { name: "Bu siteye ata", exact: true }).click();
  await expect.poll(() => mutations.some((item) => item.path.endsWith("/agents/agent-1")
    && item.body.site === "TEST FIXTURE / isolated")).toBeTruthy();
  await expect(page.getByText("Probe ajanı siteye atandı.", { exact: true })).toBeVisible();

  await page.locator("select[name=source_ip]").selectOption("192.0.2.254");
  await page.locator("input[name=acknowledged]").check();
  await page.getByRole("button", { name: "Kapsamı onayla", exact: true }).click();
  await expect.poll(() => mutations.some((item) => item.path.endsWith("/scopes")
    && item.body.active_broadcast_acknowledged === true && item.body.source_ip === "192.0.2.254")).toBeTruthy();
  await page.getByRole("button", { name: "Şimdi tara", exact: true }).click();
  await expect.poll(() => mutations.some((item) => item.path.endsWith("/runs"))).toBeTruthy();
  await mkdir(evidence, { recursive: true });
  await page.screenshot({ path: join(evidence, "network-probes-desktop.png"), fullPage: true, animations: "disabled" });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(1536);

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("heading", { name: "Onaylı tarama kapsamları", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.screenshot({ path: join(evidence, "network-probes-mobile.png"), fullPage: true, animations: "disabled" });
  await expect(page.locator("nextjs-portal")).toHaveCount(0);
  expect(errors).toEqual([]);
});
