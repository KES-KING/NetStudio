"use client";
import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { api, errorMessage } from "../lib/api";
import type {
  Device,
  APIController,
  DeviceControllerBinding,
  DeviceManagementMode,
  DriverCatalog,
} from "../lib/contracts";
import {
  blankCredentialDraft,
  implementedTransports,
  profileForDevice,
  type TransportKind,
} from "../lib/compatibility";
import { useSession } from "./ConsoleShell";
import useSWR from "swr";
import { HostDiscovery, SNMPSettings } from "./CollectionControls";
import { CatalogProfileFields, TransportPicker } from "./DriverProfileFields";

export function Dialog({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    const trigger = document.activeElement;
    dialog?.showModal();
    dialog
      ?.querySelector<HTMLElement>("[data-dialog-initial-focus]")
      ?.focus({ preventScroll: true });
    return () => {
      dialog?.close();
      // React can detach the dialog before the passive cleanup runs, so the
      // browser's native focus restoration alone is not sufficient here.
      if (trigger instanceof HTMLElement && trigger.isConnected)
        trigger.focus({ preventScroll: true });
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className="dialog"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      aria-label={title}
    >
      <div className="panel-heading">
        <h2>{title}</h2>
        <button onClick={onClose}>Kapat</button>
      </div>
      {children}
    </dialog>
  );
}

function CredentialFields({ optional = false, device }: { optional?: boolean; device?: Device }) {
  const [method, setMethod] = useState("password");
  const blank = blankCredentialDraft(device);
  return (
    <fieldset>
      <legend>SSH kimlik bilgileri{optional ? " · isteğe bağlı" : ""}</legend>
      <div className="form-grid">
        <label>
          SSH kullanıcı adı
          <input
            name="ssh_username"
            defaultValue={blank.username}
            autoComplete="off"
            maxLength={128}
            required={!optional}
          />
        </label>
        <label>
          Kimlik doğrulama
          <select
            name="method"
            value={method}
            onChange={(e) => setMethod(e.target.value)}
          >
            <option value="password">Parola</option>
            <option value="private_key">Özel anahtar</option>
          </select>
        </label>
      </div>
      {method === "password" ? (
        <label>
          Cihaz parolası
          <input
            name="password"
            defaultValue={blank.password}
            type="password"
            autoComplete="new-password"
            maxLength={32768}
          />
        </label>
      ) : (
        <>
          <label>
            Özel anahtar
            <textarea
              name="private_key"
              defaultValue={blank.private_key}
              rows={5}
              autoComplete="off"
              spellCheck={false}
              maxLength={32768}
            />
          </label>
          <label>
            Anahtar parolası (varsa)
            <input
            name="passphrase"
            defaultValue={blank.passphrase}
              type="password"
              autoComplete="new-password"
            />
          </label>
        </>
      )}
      <p className="field-help">
        Kaydedilen sırlar tekrar gösterilmez. Bu bilgiler yalnızca yetkili cihaz
        bağlantılarında kullanılır.
      </p>
    </fieldset>
  );
}
function credentials(data: FormData) {
  return {
    username: String(data.get("ssh_username") ?? ""),
    method: String(data.get("method") ?? "password"),
    password: String(data.get("password") ?? ""),
    private_key: String(data.get("private_key") ?? ""),
    passphrase: String(data.get("passphrase") ?? ""),
  };
}

function connectionSettings(data: FormData) {
  return {
    ssh_profile: data.get("ssh_profile") ?? "standard",
    legacy_ssh_confirmed: data.get("legacy_ssh_confirmed") === "on",
    allow_legacy_ssh: data.get("allow_legacy_ssh") === "on" || data.get("legacy_ssh_confirmed") === "on",
    ssh_algorithms: Object.fromEntries(["kex_algs", "server_host_key_algs", "signature_algs", "encryption_algs", "mac_algs"]
      .map(field => [field, data.getAll(field)])),
  };
}

function ConnectionFields({ device }: { device?: Device }) {
  const [profile, setProfile] = useState<string>(device?.ssh_profile ?? "auto");
  const { data: catalog } = useSWR<{ algorithms: Record<string, { id: string; legacy: boolean }[]> }>("/api/v1/ssh-profiles", api);
  return (
    <fieldset>
      <legend>SSH güvenlik profili</legend>
      <p className="field-help">
        Kanonik cihaz profili Uyumluluk panelinden yönetilir. Buradaki seçim
        yalnız SSH algoritma politikasını değiştirir.
      </p>
      <div className="form-grid ssh-policy-grid">
        <label>
          SSH uyumluluk profili
          <select name="ssh_profile" aria-label="SSH uyumluluk profili" value={profile} onChange={(event) => setProfile(event.target.value)}>
            <option value="auto">Otomatik</option>
            <option value="standard">Standart (önerilen)</option>
            <option value="huawei_legacy">Eski VRP</option>
            <option value="legacy_sha1">Eski SSH · SHA-1</option>
            <option value="legacy_cbc">Eski SSH · CBC/Group1</option>
            <option value="advanced">Gelişmiş</option>
          </select>
        </label>
      </div>
      {profile !== "huawei_legacy" && <label className="checkbox"><input type="checkbox" name="allow_legacy_ssh"
        defaultChecked={device?.allow_legacy_ssh ?? false} required={["legacy_sha1", "legacy_cbc"].includes(profile)} />
        Bu cihazda eski SSH algoritmalarına izin ver</label>}
      {profile === "advanced" && <div className="form-grid">{Object.entries(catalog?.algorithms ?? {}).map(([field, choices]) =>
        <label key={field}>{({ kex_algs: "Anahtar değişimi", server_host_key_algs: "Host imzası", signature_algs: "Kullanıcı anahtarı imzası",
          encryption_algs: "Şifreleme", mac_algs: "MAC" } as Record<string, string>)[field]}
          <select name={field} multiple defaultValue={device?.ssh_algorithms?.[field] ?? []}>
            {choices.map(choice => <option key={choice.id} value={choice.id}>{choice.id}{choice.legacy ? " · eski / riskli" : ""}</option>)}
          </select></label>)}</div>}
      <p className="field-help">
        Cihaz kaydı, bu yönetim IP adresi ve SSH portu için bağlantı onayıdır;
        cihaz başına .env izni gerekmez. Kurulum geneli ek ağ kısıtı varsa uygulanır.
        Host anahtarının ayrıca doğrulanması gerekir.
      </p>
      {profile === "huawei_legacy" && (
        <div className="notice warning">
          <p>Yalnız bu cihaz için SHA-1 anahtar değişimi, ssh-rsa ve aes128-cbc desteği eklenir.
            Eski algoritmalar daha zayıftır; mümkünse cihaz yazılımını güncelleyip Standart profile dönün.
            Host anahtarı doğrulaması korunur.</p>
          {device?.ssh_profile !== "huawei_legacy" && (
            <label className="checkbox">
              <input type="checkbox" name="legacy_ssh_confirmed" required />
              Bu cihaz için eski SSH algoritmalarının kullanımını onaylıyorum.
            </label>
          )}
        </div>
      )}
    </fieldset>
  );
}

const controllerProfiles = {
  cisco_meraki_ms: { vendor: "meraki", auth: "bearer", scopes: ["dashboard:general:config:read", "switch:config:read", "switch:telemetry:read"] },
  fortinet_fortiswitch_fortilink: { vendor: "fortigate", auth: "bearer", scopes: ["switch-controller:read"] },
  ubiquiti_unifi_switch: { vendor: "unifi", auth: "api_key", scopes: ["site:read", "device:read"] },
  ubiquiti_unifi_no_snmp: { vendor: "unifi", auth: "api_key", scopes: ["site:read", "device:read"] },
  tplink_omada_managed: { vendor: "omada", auth: "access_token", scopes: ["site:read", "device:read"] },
  tplink_omada_pro: { vendor: "omada_pro", auth: "access_token", scopes: ["site:read", "device:read"] },
} as const;

function ControllerSettings({
  device,
  profileId,
  onSaved,
}: {
  device: Device;
  profileId: string;
  onSaved: () => void;
}) {
  const policy = controllerProfiles[profileId as keyof typeof controllerProfiles];
  const { data: controllers, mutate: mutateControllers } = useSWR<APIController[]>(
    "/api/v1/controllers",
    api,
  );
  const bindingPath = `/api/v1/devices/${device.id}/controller-binding`;
  const { data: binding, mutate: mutateBinding } = useSWR<DeviceControllerBinding | null>(bindingPath, api);
  const compatible = (controllers ?? []).filter(
    (controller) => policy && controller.vendor === policy.vendor && controller.site === device.site,
  );
  const [selectedId, setSelectedId] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string>();
  const [message, setMessage] = useState<string>();
  const selected = compatible.find((controller) => controller.id === selectedId)
    ?? compatible.find((controller) => controller.id === binding?.controller_id)
    ?? compatible[0];

  if (!policy)
    return <p className="notice warning">Bu profil için controller kayıt politikası bulunamadı.</p>;

  async function createController(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    setBusy(true); setFailure(undefined); setMessage(undefined);
    try {
      const created = await api<APIController>("/api/v1/controllers", {
        method: "POST",
        body: JSON.stringify({
          name: values.get("controller_name"), vendor: policy.vendor, site: device.site,
          endpoint_kind: policy.vendor === "meraki" ? "cloud" : "local",
          address: policy.vendor === "meraki" ? null : values.get("address"),
          port: policy.vendor === "meraki" ? null : Number(values.get("port")),
          cloud_region: policy.vendor === "meraki" ? values.get("cloud_region") : null,
          ca_pem: policy.vendor === "meraki" ? null : String(values.get("ca_pem") ?? "") || null,
          external_scope_id: values.get("external_scope_id"),
          external_site_id: values.get("external_site_id"), enabled: true,
        }),
      });
      await mutateControllers(); setSelectedId(created.id); form.reset();
      setMessage("Controller kaydı oluşturuldu. Şimdi salt-okunur erişim anahtarını kaydedin.");
    } catch (error) { setFailure(errorMessage(error)); } finally { setBusy(false); }
  }

  async function saveSecret(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const form = event.currentTarget;
    const values = new FormData(form);
    const expiry = String(values.get("expires_at") ?? "");
    setBusy(true); setFailure(undefined); setMessage(undefined);
    try {
      await api(`/api/v1/controllers/${selected.id}/credentials`, {
        method: "PUT",
        body: JSON.stringify({ auth_kind: policy.auth, token: values.get("token"),
          scopes: policy.scopes, expires_at: expiry ? new Date(expiry).toISOString() : null }),
      });
      form.reset(); await mutateControllers(); onSaved();
      setMessage("Controller erişim anahtarı ayrı sır kasasında kaydedildi.");
    } catch (error) { setFailure(errorMessage(error)); } finally { setBusy(false); }
  }

  async function bind(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const values = new FormData(event.currentTarget);
    setBusy(true); setFailure(undefined); setMessage(undefined);
    try {
      await api(bindingPath, { method: "PUT", body: JSON.stringify({
        controller_id: selected.id, external_device_id: values.get("external_device_id"),
      }) });
      await mutateBinding(); onSaved();
      setMessage("Cihaz, controller içindeki kimliği ve sitesiyle eşlendi.");
    } catch (error) { setFailure(errorMessage(error)); } finally { setBusy(false); }
  }

  async function revokeSecret() {
    if (!selected) return;
    setBusy(true); setFailure(undefined);
    try {
      await api(`/api/v1/controllers/${selected.id}/credentials`, { method: "DELETE" });
      await mutateControllers(); onSaved(); setMessage("Controller erişim anahtarı iptal edildi.");
    } catch (error) { setFailure(errorMessage(error)); } finally { setBusy(false); }
  }

  async function unbind() {
    setBusy(true); setFailure(undefined);
    try {
      await api(bindingPath, { method: "DELETE" });
      await mutateBinding(); onSaved(); setMessage("Controller cihaz eşlemesi kaldırıldı.");
    } catch (error) { setFailure(errorMessage(error)); } finally { setBusy(false); }
  }

  return <section aria-label="Controller API bağlantısı">
    <p className="notice">
      API yönetimi SSH’den ayrıdır. Hedef URL girilmez; {policy.vendor === "meraki" ? "Meraki bölge adresi sabittir" : "yalnız kayıtlı controller IP adresine doğrulanmış TLS ile bağlanılır"}.
    </p>
    {compatible.length > 0 && <label>Controller kaydı
      <select value={selected?.id ?? ""} onChange={(event) => setSelectedId(event.target.value)}>
        {compatible.map((controller) => <option key={controller.id} value={controller.id}>
          {controller.name} · {controller.external_site_id}{controller.enabled ? "" : " · kapalı"}
        </option>)}
      </select>
    </label>}
    <details open={compatible.length === 0}><summary>Yeni controller kaydı</summary>
      <form onSubmit={createController}><div className="form-grid">
        <label>Kayıt adı<input name="controller_name" required maxLength={160} /></label>
        {policy.vendor === "meraki" ? <label>Bulut bölgesi<select name="cloud_region" defaultValue="global">
          <option value="global">Global</option><option value="canada">Kanada</option>
          <option value="india">Hindistan</option><option value="china">Çin</option>
        </select></label> : <>
          <label>Controller IP adresi<input name="address" required placeholder="IPv4 veya IPv6" /></label>
          <label>HTTPS portu<input name="port" type="number" min={1} max={65535} defaultValue={443} required /></label>
        </>}
        <label>{policy.vendor === "meraki" ? "Organization ID" : "Controller / tenant ID"}<input name="external_scope_id" required maxLength={160} /></label>
        <label>Controller site / network ID<input name="external_site_id" required maxLength={160} /></label>
      </div>
      {policy.vendor !== "meraki" && <label>Özel CA sertifikası (PEM, gerekiyorsa)<textarea name="ca_pem" rows={5} maxLength={32768} spellCheck={false} /></label>}
      <button disabled={busy}>Controller kaydını oluştur</button></form>
    </details>
    {selected && <>
      <fieldset><legend>Salt-okunur API erişimi · {selected.credential_configured ? "tanımlı" : "tanımlı değil"}</legend>
        <p className="field-help">Gerekli kapsamlar: {policy.scopes.join(", ")}. Token kaydedildikten sonra tekrar gösterilmez.</p>
        <form onSubmit={saveSecret}><div className="form-grid">
          <label>{policy.auth === "api_key" ? "API anahtarı" : policy.auth === "access_token" ? "OAuth erişim tokenı" : "Bearer erişim tokenı"}<input name="token" type="password" minLength={16} maxLength={16384} required autoComplete="new-password" /></label>
          <label>Geçerlilik sonu (varsa)<input name="expires_at" type="datetime-local" /></label>
        </div><button disabled={busy}>API erişimini kaydet</button></form>
        {selected.credential_configured && <button type="button" className="danger" disabled={busy} onClick={revokeSecret}>Kayıtlı API erişimini iptal et</button>}
      </fieldset>
      <fieldset><legend>Controller cihaz eşlemesi</legend>
        <p className="field-help">NetStudio sitesi: {device.site} · Controller sitesi: {selected.external_site_id}. Başka sitenin cihazı bu kayda bağlanamaz.</p>
        <form onSubmit={bind}><label>Controller cihaz kimliği / seri numarası<input name="external_device_id" required maxLength={160} defaultValue={binding?.external_device_id ?? ""} /></label>
          <button disabled={busy || !selected.credential_configured}>Cihaz eşlemesini kaydet</button></form>
        {binding && <button type="button" disabled={busy} onClick={unbind}>Cihaz eşlemesini kaldır</button>}
      </fieldset>
    </>}
    {message && <p className="notice success" role="status">{message}</p>}
    {failure && <p className="notice error" role="alert">{failure}</p>}
  </section>;
}

export function AddDevice({
  onClose,
  onSaved,
}: {
  onClose: () => void;
  onSaved: (device: Device) => void;
}) {
  const session = useSession();
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<string | null>(null);
  const errorRef = useRef<HTMLParagraphElement>(null);
  const { data: driverCatalog, error: catalogError } = useSWR<DriverCatalog>(
    "/api/v1/driver-catalog",
    api,
  );
  const [sourceMode, setSourceMode] = useState("profile");
  const [vendor, setVendor] = useState("");
  const [profileId, setProfileId] = useState("");
  const [managementMode, setManagementMode] = useState<DeviceManagementMode>("unknown");
  const [credentialTransport, setCredentialTransport] = useState<TransportKind | "">("");
  const selectedProfile = driverCatalog?.profiles?.find(
    (profile) => profile.id === profileId,
  ) ?? null;

  function selectProfile(id: string) {
    setProfileId(id);
    const profile = driverCatalog?.profiles?.find((candidate) => candidate.id === id);
    setCredentialTransport(implementedTransports(profile)[0] ?? "");
  }

  function changeSourceMode(mode: string) {
    setSourceMode(mode);
    setError(null);
    if (mode === "profile") {
      setCredentialTransport(implementedTransports(selectedProfile)[0] ?? "");
      return;
    }
    const adapterId = mode.startsWith("adapter:") ? mode.slice(8) : null;
    const adapter = driverCatalog?.infrastructure_adapters?.find(
      (candidate) => candidate.id === adapterId,
    );
    const adapterSSH = adapter?.transports.ssh?.state === "implemented";
    setCredentialTransport(mode === "auto" || adapterSSH ? "ssh" : "");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    setBusy(true);
    setError(null);
    const creds = credentials(data);
    const profileMode = sourceMode === "profile";
    const collector = sourceMode.startsWith("adapter:")
      ? sourceMode.slice(8)
      : sourceMode;
    const payload = {
      name: data.get("name"),
      management_address: data.get("management_address"),
      site: data.get("site"),
      device_type: data.get("device_type"),
      vendor: profileMode ? vendor : data.get("vendor"),
      model: data.get("model"),
      ssh_port: Number(data.get("ssh_port")),
      ...connectionSettings(data),
      ...(profileMode
        ? {
            configured_profile_id: profileId,
            management_mode: managementMode,
          }
        : { collector, management_mode: "unknown" }),
      credentials:
        credentialTransport === "ssh" && creds.username ? creds : null,
    };
    try {
      const device = await api<Device>("/api/v1/devices", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      form.reset();
      onSaved(device);
    } catch (e) {
      setError(errorMessage(e));
      requestAnimationFrame(() => errorRef.current?.focus());
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog title="Cihaz Ekle" onClose={onClose}>
      <form
        onSubmit={submit}
        onInvalid={(event) => {
          event.preventDefault();
          setError("Zorunlu alanları ve seçilebilir profil adımlarını tamamlayın.");
          requestAnimationFrame(() => errorRef.current?.focus());
        }}
        className="dialog-body device-create-form"
      >
        <div className="form-grid">
          <label>
            Cihaz adı
            <input
              name="name"
              required
              maxLength={160}
              autoFocus
              data-dialog-initial-focus
            />
          </label>
          <label>
            Yönetim IP adresi
            <input
              name="management_address"
              required
              placeholder="IPv4 veya IPv6"
              autoComplete="off"
            />
          </label>
          <label>
            Site
            <input
              name="site"
              required
              defaultValue={
                session.site_ids.includes("*") ? "" : session.site_ids[0]
              }
              maxLength={160}
            />
          </label>
          <label>
            Cihaz türü
            <select name="device_type">
              <option value="switch">Switch</option>
              <option value="router">Yönlendirici</option>
              <option value="firewall">Güvenlik duvarı</option>
              <option value="server">Sunucu</option>
              <option value="other">Diğer</option>
            </select>
          </label>
          <label>
            Model (biliniyorsa)
            <input name="model" maxLength={160} />
          </label>
          <label>
            SSH portu
            <input
              name="ssh_port"
              type="number"
              min={1}
              max={65535}
              defaultValue={22}
              required
            />
          </label>
        </div>
        <fieldset className="source-mode-selector">
          <legend>Profil kaynağı</legend>
          <label>
            Cihazı nasıl tanımlayacaksınız?
            <select
              aria-label="Profil kaynağı"
              value={sourceMode}
              onChange={(event) => changeSourceMode(event.target.value)}
            >
              <option value="profile">Üretici ve OS profilini seç</option>
              <option value="auto">SSH üzerinden otomatik kimlik algılama</option>
              <option value="external">Harici toplayıcı / yalnız envanter</option>
              {driverCatalog?.infrastructure_adapters?.filter((adapter) => adapter.selectable).map((adapter) => (
                <option key={adapter.id} value={`adapter:${adapter.id}`}>{adapter.label} · altyapı adaptörü</option>
              ))}
            </select>
          </label>
        </fieldset>
        {sourceMode === "profile" ? (
          <>
            {catalogError && <p className="notice error" role="alert">{errorMessage(catalogError)}</p>}
            <CatalogProfileFields
              catalog={driverCatalog}
              vendor={vendor}
              profileId={profileId}
              managementMode={managementMode}
              onVendorChange={setVendor}
              onProfileChange={selectProfile}
              onManagementModeChange={setManagementMode}
            />
            <TransportPicker
              profile={selectedProfile}
              value={credentialTransport}
              onChange={setCredentialTransport}
            />
          </>
        ) : (
          <fieldset>
            <legend>Kimlik bilgisi</legend>
            <label>
              Üretici (biliniyorsa)
              <input name="vendor" maxLength={120} />
            </label>
            <p className="field-help">
              {sourceMode === "external"
                ? "Harici mod cihaz bağlantısı kurmaz; SSH, SNMP veya API sırrı istenmez."
                : "Kimlik, ilk başarılı ve güvenli toplama sonrasında kanonik profile çözümlenir."}
            </p>
          </fieldset>
        )}
        {credentialTransport === "ssh" && (
          <>
            <ConnectionFields />
            <CredentialFields optional />
          </>
        )}
        {credentialTransport === "snmp" && (
          <p className="notice" role="status">
            Cihaz kaydedildikten sonra Bağlantı bilgileri ekranından SNMPv3
            authPriv hesabını ekleyin. Sır alanları API cevabından doldurulmaz.
          </p>
        )}
        {credentialTransport === "api" && (
          <p className="notice" role="status">
            Cihazı kaydettikten sonra Bağlantı bilgileri ekranından controller
            kaydını, salt-okunur API erişimini ve controller cihaz kimliğini eşleyin.
          </p>
        )}
        {error && (
          <p ref={errorRef} role="alert" tabIndex={-1} className="notice error form-error-summary">
            Form kaydedilemedi. Aşağıdaki hatayı düzeltip yeniden deneyin:<br />
            {error}
          </p>
        )}
        <div className="form-actions">
          <button type="button" onClick={onClose}>
            Vazgeç
          </button>
          <button className="primary" disabled={busy}>
            {busy ? "Kaydediliyor…" : "Cihazı kaydet"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}

export function ConnectionSettings({
  device,
  onClose,
  onSaved,
}: {
  device: Device;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<string | null>(null),
    [message, setMessage] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const { data: driverCatalog } = useSWR<DriverCatalog>(
    "/api/v1/driver-catalog",
    api,
  );
  const currentProfile = profileForDevice(driverCatalog, device);
  const availableTransports = currentProfile
    ? implementedTransports(currentProfile)
    : device.collector === "external"
      ? []
      : (["ssh"] as TransportKind[]);
  const [requestedTransport, setRequestedTransport] = useState<TransportKind>("ssh");
  const selectedTransport = availableTransports.includes(requestedTransport)
    ? requestedTransport
    : availableTransports[0] ?? "";
  async function saveSettings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await api(`/api/v1/devices/${device.id}/connection-settings`, {
        method: "PUT", body: JSON.stringify(connectionSettings(data)),
      });
      setMessage("SSH güvenlik profili kaydedildi. Değişiklik varsa açık SSH oturumları sonlandırıldı.");
      onSaved();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  async function saveCredentials(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    setBusy(true);
    setError(null);
    try {
      const result = await api<{ unchanged: boolean }>(
        `/api/v1/devices/${device.id}/credentials`,
        { method: "PUT", body: JSON.stringify(credentials(data)) },
      );
      form.reset();
      setMessage(
        result.unchanged
          ? "Kayıtlı kimlik bilgileri korundu."
          : "Kimlik bilgileri şifrelenerek kaydedildi.",
      );
      onSaved();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  async function saveKey(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    setBusy(true);
    setError(null);
    try {
      await api(`/api/v1/devices/${device.id}/host-key`, {
        method: "PUT",
        body: JSON.stringify({
          public_key: data.get("public_key"),
          fingerprint: data.get("fingerprint"),
          replace_existing: data.get("replace_existing") === "on",
        }),
      });
      form.reset();
      setMessage("Doğruladığınız host anahtarı kaydedildi.");
      onSaved();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  async function removeCredentials() {
    setBusy(true);
    setError(null);
    try {
      await api(`/api/v1/devices/${device.id}/credentials`, {
        method: "DELETE",
      });
      setMessage(
        "Cihaz kimlik bilgileri silindi; açık oturumlar sonlandırıldı.",
      );
      setConfirmDelete(false);
      onSaved();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog title={`${device.name} · Bağlantı bilgileri`} onClose={onClose}>
      <div className="dialog-body">
        {currentProfile ? (
          <TransportPicker
            profile={currentProfile}
            value={selectedTransport}
            onChange={setRequestedTransport}
          />
        ) : (
          <p className={`notice ${device.collector === "external" ? "" : "warning"}`}>
            {device.collector === "external"
              ? "Harici toplayıcı modunda cihaz sırrı istenmez. Önce Uyumluluk panelinden uygulanmış bir profil seçebilirsiniz."
              : "Cihaz henüz kanonik profile çözülmedi. Yalnız mevcut legacy SSH bağlantı yolu gösteriliyor."}
          </p>
        )}
        {selectedTransport === "ssh" && <>
          <form onSubmit={saveSettings}>
            <ConnectionFields key={`${device.id}:${device.ssh_profile}`} device={device} />
            <div className="form-actions">
              <button className="primary" disabled={busy}>SSH güvenlik profilini kaydet</button>
            </div>
          </form>
          <p className="notice">
            {device.credential_configured
              ? "SSH kimlik bilgisi tanımlı. Sır alanları güvenlik nedeniyle boş açılır; boş gönderim kayıtlı bilgileri korur."
              : "SSH kimlik bilgisi tanımlı değil."}
          </p>
          <form onSubmit={saveCredentials}>
            <CredentialFields device={device} />
            <div className="form-actions">
              <button className="primary" disabled={busy}>
                SSH kimlik bilgilerini kaydet
              </button>
            </div>
          </form>
          {device.credential_configured && (
            <div className="credential-delete">
              {confirmDelete ? (
                <>
                  <p>
                    SSH kimlik bilgileri silinecek ve açık oturumlar kapanacak.
                  </p>
                  <button
                    className="danger"
                    disabled={busy}
                    onClick={removeCredentials}
                  >
                    Silme işlemini onayla
                  </button>
                  <button onClick={() => setConfirmDelete(false)}>Vazgeç</button>
                </>
              ) : (
                <button onClick={() => setConfirmDelete(true)}>
                  Kayıtlı SSH kimlik bilgilerini sil
                </button>
              )}
            </div>
          )}
          <HostDiscovery device={device} onSaved={onSaved} />
          <details><summary>Gelişmiş · host anahtarını elle gir</summary><form onSubmit={saveKey}>
          <fieldset>
            <legend>SSH host anahtarı</legend>
            <p className="field-help">
              Cihazın public host anahtarını ve bağımsız güvenilir kanaldan
              doğruladığınız SHA256 fingerprint değerini girin. Anahtar
              değişirse bağlantı durdurulur.
            </p>
            {device.host_key_fingerprint && (
              <p className="mono break-text">
                Kayıtlı: {device.host_key_fingerprint}
              </p>
            )}
            <label>
              OpenSSH public host anahtarı
              <textarea
                name="public_key"
                required
                rows={3}
                spellCheck={false}
                maxLength={16384}
                placeholder="ssh-ed25519 …"
              />
            </label>
            <label>
              Doğrulanmış SHA256 fingerprint
              <input
                name="fingerprint"
                required
                placeholder="SHA256:…"
                maxLength={160}
              />
            </label>
            {device.host_key_fingerprint && (
              <label className="checkbox">
                <input name="replace_existing" type="checkbox" required />
                Kayıtlı anahtarın değiştirilmesini onaylıyorum.
              </label>
            )}
            <div className="form-actions">
              <button disabled={busy}>Host anahtarını kaydet</button>
            </div>
          </fieldset>
          </form></details>
        </>}
        {selectedTransport === "snmp" && (
          <SNMPSettings device={device} onSaved={onSaved} />
        )}
        {selectedTransport === "api" && (
          <ControllerSettings device={device} profileId={currentProfile?.id ?? ""} onSaved={onSaved} />
        )}
        {message && (
          <p role="status" className="notice success">
            {message}
          </p>
        )}
        {error && (
          <p role="alert" className="notice error">
            {error}
          </p>
        )}
      </div>
    </Dialog>
  );
}

export function InventoryImport({
  device,
  onClose,
  onSaved,
}: {
  device: Device;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [error, setError] = useState<string | null>(null),
    [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const file = new FormData(event.currentTarget).get("file") as File;
      if (!file || file.size > 4_000_000) throw new Error();
      const payload = JSON.parse(await file.text());
      await api(`/api/v1/devices/${device.id}/inventory`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      onSaved();
      onClose();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog title="Doğrulanmış envanteri aktar" onClose={onClose}>
      <form className="dialog-body" onSubmit={submit}>
        <p>
          Port, arayüz ve fiziksel eşleme kayıtlarını içeren envanter JSON
          dosyasını seçin. Gözlem kaynağı ve zamanı zorunludur; aktarım mevcut
          envanteri değiştirir.
        </p>
        <label>
          Envanter dosyası
          <input
            type="file"
            name="file"
            accept="application/json,.json"
            required
          />
        </label>
        {error && (
          <p className="notice error" role="alert">
            {error}
          </p>
        )}
        <button className="primary" disabled={busy}>
          Envanteri aktar
        </button>
      </form>
    </Dialog>
  );
}
