"use client";
import dynamic from "next/dynamic";
import { useMemo } from "react";
import type { Projection } from "../lib/contracts";
import {
  capacityData,
  capacityOption,
  portOption,
  reachOption,
  trafficOption,
} from "../lib/charts";
import { summarize } from "../lib/metrics";

export const Chart = dynamic(() => import("./EChart"), {
  ssr: false,
  loading: () => (
    <div className="chart-loading" role="status">
      Grafik yükleniyor…
    </div>
  ),
});

export function OperationSummary({
  rows,
  minutes,
}: {
  rows: Projection[];
  minutes: number;
}) {
  const charts = useMemo(
    () => ({
      reach: reachOption(rows),
      ports: portOption(rows),
      traffic: trafficOption(rows),
      capacity: capacityOption(rows),
    }),
    [rows],
  );
  const summary = summarize(rows);
  const hasTraffic = rows.some((row) =>
    row.traffic.some((p) => p.rx_bps != null || p.tx_bps != null),
  );
  const capacity = capacityData(rows);
  const reachText = `${summary.reach.reachable} erişilebilir, ${summary.reach.unreachable} erişilemiyor, ${summary.reach.unknown} bilinmiyor`;
  const portText = `${summary.ports.up} aktif / ${summary.total} fiziksel port · ${summary.ports.unknown} bilinmiyor`;
  return (
    <section className="summary-grid" aria-label="Operasyon özeti">
      <section className="chart-panel">
        <div className="panel-heading">
          <h2>Cihaz erişilebilirliği</h2>
          <span>{rows.length} cihaz</span>
        </div>
        {rows.length ? (
          <Chart option={charts.reach} label={reachText} />
        ) : (
          <Empty text="Henüz izlenen cihaz yok" />
        )}
        <p className="chart-note">
          {rows.length
            ? reachText
            : "Cihaz eklendiğinde erişilebilirlik dağılımı burada görünür."}
        </p>
      </section>
      <section className="chart-panel">
        <div className="panel-heading">
          <h2>Aktif port oranı</h2>
          <strong>
            {summary.activeRatio == null
              ? "Veri yok"
              : `%${summary.activeRatio.toLocaleString("tr-TR", { maximumFractionDigits: 1 })}`}
          </strong>
        </div>
        {summary.total ? (
          <Chart option={charts.ports} label={portText} />
        ) : (
          <Empty text="Fiziksel port envanteri yok" />
        )}
        <p className="chart-note">
          {portText}. Pay: link up; payda: tüm fiziksel ağ portları. Kablo veya
          modül doluluğu değildir.
        </p>
      </section>
      <section className="chart-panel">
        <div className="panel-heading">
          <h2>Arayüz trafiği</h2>
          <span>
            Son{" "}
            {minutes === 1440
              ? "24 saat"
              : minutes === 60
                ? "1 saat"
                : `${minutes} dakika`}
          </span>
        </div>
        {hasTraffic ? (
          <Chart
            option={charts.traffic}
            label="Cihaz başına fiziksel ethernet arayüzlerinin RX ve TX trafik hızları, Mbit/s"
          />
        ) : (
          <Empty text="Bu zaman aralığında trafik örneği yok" />
        )}
        <p className="chart-note">
          RX ve TX ayrı yönlerdir. Gözlenen arayüz toplamları; benzersiz ağ
          trafiği değildir. Eksik örnekler boşluk bırakır.
          {rows.some((r) => r.telemetry?.interfaces.some((i) => i.rate_interval_seconds != null)) &&
            " Cihazın raporladığı ortalama hızların ölçüm penceresi port detayında belirtilir."}
          {rows.some((r) => r.history_truncated) &&
            " Yoğun kayıt: cihaz başına son 2880 örnek gösteriliyor."}
        </p>
      </section>
      <section className="chart-panel">
        <div className="panel-heading">
          <h2>Kapasite kullanımı</h2>
          <span>RX / TX · %</span>
        </div>
        {capacity.length ? (
          <Chart
            option={charts.capacity}
            label="Arayüz kapasitesine göre ayrı RX ve TX kullanım yüzdeleri"
          />
        ) : (
          <Empty text="Güncel hız ve kapasite birlikte mevcut değil" />
        )}
        <p className="chart-note">
          Her yön kendi bağlantı kapasitesine bölünür; tam duplex yönler
          toplanmaz.
        </p>
      </section>
    </section>
  );
}
export function Empty({ text }: { text: string }) {
  return (
    <div className="empty-state">
      <span className="empty-rule" aria-hidden="true" />
      <p>{text}</p>
    </div>
  );
}
