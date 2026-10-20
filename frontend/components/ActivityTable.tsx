"use client";
import useSWR from "swr";
import { api, errorMessage } from "../lib/api";
import type { Job } from "../lib/contracts";
import { formatTime } from "../lib/metrics";
import { Empty } from "./OperationSummary";
const kinds: Record<string, string> = {
  ssh_discovery: "SSH anahtar keşfi", connection_test: "Bağlantı testi", inventory_read: "Veri toplama",
};
const statuses: Record<string, string> = {
  queued: "Bekliyor", running: "Çalışıyor", succeeded: "Tamamlandı", partial: "Kısmi",
  blocked: "Engellendi", cancelled: "İptal edildi", failed: "Başarısız",
};
export default function ActivityTable() {
  const { data, error, mutate, isLoading } = useSWR<Job[]>(
    "/api/v1/jobs",
    api,
    { refreshInterval: 15000 },
  );
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">YÖNETİM</p>
          <h1>İş geçmişi</h1>
          <p>Son 100 bağlantı ve veri toplama işi.</p>
        </div>
        <button onClick={() => mutate()}>Yenile</button>
      </div>
      {error ? (
        <p role="alert" className="notice error">
          {errorMessage(error)}
        </p>
      ) : isLoading ? (
        <Empty text="Kayıtlar yükleniyor…" />
      ) : !data?.length ? (
        <Empty text="Henüz kayıt yok." />
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Zaman</th>
                <th>İş</th>
                <th>Cihaz kimliği</th>
                <th>Durum / sonuç</th>
                <th>Kayıt</th>
              </tr>
            </thead>
            <tbody>
              {data.map((value) => (
                  <tr key={value.id}>
                    <td>{formatTime(value.created_at)}</td>
                    <td>{kinds[value.kind] ?? value.kind}</td>
                    <td className="mono">{value.device_id}</td>
                    <td>
                      {statuses[value.status] ?? value.status} {value.error_code ?? value.result_code}
                    </td>
                    <td className="mono">{value.id}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
