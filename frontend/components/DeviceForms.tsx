"use client";
import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { api, errorMessage } from "../lib/api";
import type { Device } from "../lib/contracts";
import { useSession } from "./ConsoleShell";
import useSWR from "swr";
import { HostDiscovery, SNMPSettings } from "./CollectionControls";

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

function CredentialFields({ optional = false }: { optional?: boolean }) {
  const [method, setMethod] = useState("password");
  return (
    <fieldset>
      <legend>SSH kimlik bilgileri{optional ? " · isteğe bağlı" : ""}</legend>
      <div className="form-grid">
        <label>
          SSH kullanıcı adı
          <input
            name="ssh_username"
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
    collector: data.get("collector"),
    ssh_profile: data.get("ssh_profile"),
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
      <legend>Veri toplama ve SSH uyumluluğu</legend>
      <div className="form-grid">
        <label>
          Veri kaynağı
          <select name="collector" aria-label="Veri kaynağı" defaultValue={device?.collector ?? "auto"}>
            <option value="auto">Otomatik sürücü seçimi</option>
            <option value="external">Harici toplayıcı / envanter aktarımı</option>
            <option value="linux_ssh">Linux · salt okunur SSH</option>
            <option value="huawei_vrp">Huawei VRP · salt okunur SSH</option>
            <option value="cisco_ios">Cisco IOS · Catalyst 2960-X salt okunur SSH</option>
            <option value="cisco_iosxe">Cisco IOS-XE · deneysel</option>
            <option value="cisco_nxos">Cisco NX-OS · JSON · deneysel</option>
            <option value="juniper_junos">Juniper Junos · XML · deneysel</option>
          </select>
        </label>
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
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    setBusy(true);
    setError(null);
    const creds = credentials(data);
    const payload = {
      name: data.get("name"),
      management_address: data.get("management_address"),
      site: data.get("site"),
      device_type: data.get("device_type"),
      vendor: data.get("vendor"),
      model: data.get("model"),
      ssh_port: Number(data.get("ssh_port")),
      ...connectionSettings(data),
      credentials: creds.username ? creds : null,
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
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog title="Cihaz Ekle" onClose={onClose}>
      <form onSubmit={submit} className="dialog-body">
        <div className="form-grid">
          <label>
            Cihaz adı
            <input name="name" required maxLength={160} autoFocus />
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
            Üretici (biliniyorsa)
            <input name="vendor" maxLength={120} />
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
        <ConnectionFields />
        <CredentialFields optional />
        {error && (
          <p role="alert" className="notice error">
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
      setMessage("Veri kaynağı ve SSH profili kaydedildi. Değişiklik varsa açık SSH oturumları sonlandırıldı.");
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
        <form onSubmit={saveSettings}>
          <ConnectionFields key={`${device.id}:${device.collector}:${device.ssh_profile}`} device={device} />
          <div className="form-actions">
            <button className="primary" disabled={busy}>Bağlantı ayarlarını kaydet</button>
          </div>
        </form>
        <p className="notice">
          {device.credential_configured
            ? "Kimlik bilgisi tanımlı. Sır alanını boş bırakmak kayıtlı bilgileri korur."
            : "Kimlik bilgisi tanımlı değil."}
        </p>
        <form onSubmit={saveCredentials}>
          <CredentialFields />
          <div className="form-actions">
            <button className="primary" disabled={busy}>
              Kimlik bilgilerini kaydet
            </button>
          </div>
        </form>
        {device.credential_configured && (
          <div className="credential-delete">
            {confirmDelete ? (
              <>
                <p>
                  Kimlik bilgileri silinecek ve açık SSH oturumları kapanacak.
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
                Kayıtlı kimlik bilgilerini sil
              </button>
            )}
          </div>
        )}
        <HostDiscovery device={device} onSaved={onSaved} />
        <SNMPSettings device={device} onSaved={onSaved} />
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
