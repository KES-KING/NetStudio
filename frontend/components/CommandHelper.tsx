"use client";
import { useState } from "react";
import useSWR from "swr";
import { api, errorMessage } from "../lib/api";
import {
  commandDriverFor,
  commandGroupLabels,
  groupedCommands,
  matchSourceLabels,
  validationLabels,
} from "../lib/command-helper";
import type { Device, DriverCatalog } from "../lib/contracts";

export function CommandHelper({
  device,
  onClose,
}: {
  device: Device;
  onClose: () => void;
}) {
  const { data, error, isLoading, mutate } = useSWR<DriverCatalog>(
    "/api/v1/driver-catalog",
    api,
    { revalidateOnFocus: false },
  );
  const [copyMessage, setCopyMessage] = useState("");
  const match = commandDriverFor(device);
  const driver = match
    ? data?.drivers.find(
        (candidate) => candidate.id === match.id && candidate.available,
      )
    : undefined;

  async function copyCommand(command: string) {
    try {
      await navigator.clipboard.writeText(command);
      setCopyMessage(`“${command}” panoya kopyalandı.`);
    } catch {
      setCopyMessage("Pano izni yok. Komutu seçip tarayıcı menüsünden kopyalayın.");
    }
  }

  return (
    <section className="panel command-helper" aria-label="Komut yardımcısı">
      <div className="panel-heading">
        <div>
          <h2>Komut yardımcısı</h2>
          {driver && <span className="command-helper-driver">{driver.label}</span>}
        </div>
        <button onClick={onClose}>Kapat</button>
      </div>
      <div className="command-helper-body">
        <p className="command-helper-intro">
          Bu öneriler otomatik çalıştırılmaz. Bir komutu kopyalayıp terminale
          kendiniz yapıştırabilirsiniz; uzak hesabın yetkileri geçerlidir.
        </p>
        {isLoading && <p className="command-helper-state">Komut kataloğu yükleniyor…</p>}
        {error && (
          <div className="command-helper-state" role="alert">
            <p>{errorMessage(error)}</p>
            <button onClick={() => void mutate()}>Yeniden dene</button>
          </div>
        )}
        {!isLoading && !error && !match && (
          <p className="command-helper-state">
            Üretici veya platform eşleştirilemedi. Yanlış cihaz komutu
            önermemek için liste gösterilmiyor.
          </p>
        )}
        {!isLoading && !error && match && !driver && (
          <p className="command-helper-state">
            Bu platform için kullanılabilir bir komut kataloğu bulunamadı.
          </p>
        )}
        {driver && (
          <>
            <div className="command-helper-meta">
              <span>{match && matchSourceLabels[match.source]}</span>
              <span>
                {validationLabels[driver.validation_level] ??
                  driver.validation_level}
              </span>
            </div>
            {driver.commands.length === 0 ? (
              <p className="command-helper-state">
                Bu platform için doğrulanmış komut önerisi henüz yok.
              </p>
            ) : (
              groupedCommands(driver).map(({ group, commands }) => (
                <section className="command-group" key={group}>
                  <h3>{commandGroupLabels[group]}</h3>
                  <ul>
                    {commands.map((command) => (
                      <li key={command.text}>
                        <code>{command.text}</code>
                        <button
                          aria-label={`${command.text} komutunu kopyala`}
                          title="Komutu kopyala"
                          onClick={() => void copyCommand(command.text)}
                        >
                          Kopyala
                        </button>
                      </li>
                    ))}
                  </ul>
                </section>
              ))
            )}
          </>
        )}
      </div>
      <p className="command-helper-feedback" role="status" aria-live="polite">
        {copyMessage}
      </p>
    </section>
  );
}
