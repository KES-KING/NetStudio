"use client";
import useSWR from "swr";
import { api, errorMessage } from "../lib/api";
import type { AuditEvent, Job } from "../lib/contracts";
import { formatTime } from "../lib/metrics";
import { Empty } from "./OperationSummary";
import { useSession } from "./ConsoleShell";
export default function ActivityTable({ kind }: { kind: "jobs" | "audit" }) {
  const session = useSession(),
    allowed = kind === "jobs" || session.permissions.includes("audit.read");
  const { data, error, mutate, isLoading } = useSWR<(Job | AuditEvent)[]>(
    allowed ? `/api/v1/${kind}` : null,
    api,
    { refreshInterval: 15000 },
  );
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">YÖNETİM</p>
          <h1>{kind === "jobs" ? "İş geçmişi" : "Denetim kayıtları"}</h1>
          <p>
            {kind === "jobs"
              ? "Son 100 bağlantı ve veri toplama işi."
              : "Son 200 olay. Parola, erişim tokenı ve terminal içeriği kaydedilmez."}
          </p>
        </div>
        <button onClick={() => mutate()}>Yenile</button>
      </div>
      {!allowed ? (
        <Empty text="Bu kayıtları görüntüleme yetkiniz yok." />
      ) : error ? (
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
                <th>İş / olay</th>
                <th>Cihaz kimliği</th>
                <th>Durum / sonuç</th>
                <th>Kullanıcı / kayıt</th>
              </tr>
            </thead>
            <tbody>
              {data.map((value) =>
                "event" in value ? (
                  <tr key={value.id}>
                    <td>{formatTime(value.occurred_at)}</td>
                    <td>{value.event}</td>
                    <td className="mono">{value.device_id ?? "—"}</td>
                    <td>{value.outcome}</td>
                    <td>{value.user_id}</td>
                  </tr>
                ) : (
                  <tr key={value.id}>
                    <td>{formatTime(value.created_at)}</td>
                    <td>{value.kind}</td>
                    <td className="mono">{value.device_id}</td>
                    <td>
                      {value.status} {value.error_code ?? value.result_code}
                    </td>
                    <td className="mono">{value.id}</td>
                  </tr>
                ),
              )}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
