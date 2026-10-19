import { theme } from "./theme";
import type { EChartsCoreOption } from "echarts/core";
import type { Projection } from "./contracts";
import { reachLabels, portLabels, summarize } from "./metrics";

export const colors = {
  reachable: theme["green"],
  unreachable: theme["red"],
  unknown: theme["unknown"],
  up: theme["green"],
  down: theme["down"],
  disabled: theme["disabled"],
  rx: theme["accent"],
  tx: theme["tx"],
};
const base: EChartsCoreOption = {
  textStyle: {
    fontFamily: "Arial, sans-serif",
    color: theme["muted"],
    fontSize: 11,
  },
  tooltip: {
    trigger: "axis",
    renderMode: "richText",
    backgroundColor: theme["surface"],
    borderColor: theme["border"],
    borderWidth: 1,
    textStyle: { color: theme["text"], fontSize: 12 },
  },
  grid: { left: 16, top: 18, right: 20, bottom: 10, containLabel: true },
};
export function reachOption(rows: Projection[]): EChartsCoreOption {
  const summary = summarize(rows);
  return {
    ...base,
    dataset: {
      dimensions: ["state", "count"],
      source: Object.entries(summary.reach).map(([state, count]) => ({
        state: reachLabels[state as keyof typeof reachLabels],
        count,
      })),
    },
    xAxis: {
      type: "category",
      axisTick: { show: false },
      axisLine: { lineStyle: { color: theme["border"] } },
    },
    yAxis: {
      type: "value",
      minInterval: 1,
      name: "Cihaz",
      splitLine: { lineStyle: { color: theme["grid"] } },
    },
    series: [
      {
        id: "reachability",
        type: "bar",
        barMaxWidth: 54,
        encode: { x: "state", y: "count" },
        label: { show: true, position: "top", color: theme["text"] },
        itemStyle: {
          color: (p: { dataIndex: number }) =>
            [colors.reachable, colors.unreachable, colors.unknown][p.dataIndex],
        },
      },
    ],
  };
}
export function portOption(rows: Projection[]): EChartsCoreOption {
  const summary = summarize(rows);
  return {
    ...base,
    grid: { left: 16, right: 20, containLabel: true, top: 30, bottom: 40 },
    dataset: {
      dimensions: ["scope", "up", "down", "disabled", "unknown"],
      source: [{ scope: "Fiziksel portlar", ...summary.ports }],
    },
    legend: {
      bottom: 0,
      itemWidth: 9,
      itemHeight: 9,
      textStyle: { color: theme["muted"], fontSize: 10 },
    },
    xAxis: {
      type: "value",
      minInterval: 1,
      splitLine: { lineStyle: { color: theme["grid"] } },
    },
    yAxis: { type: "category", show: false },
    series: Object.entries(portLabels).map(([key, name]) => ({
      id: `ports-${key}`,
      name,
      type: "bar",
      stack: "physical",
      barMaxWidth: 36,
      encode: { x: key, y: "scope" },
      itemStyle: { color: colors[key as keyof typeof colors] },
      label: {
        show: summary.ports[key as keyof typeof summary.ports] > 0,
        color: ["unknown", "down"].includes(key)
          ? theme["text"]
          : theme["surface"],
      },
    })),
  };
}
export function trafficOption(rows: Projection[]): EChartsCoreOption {
  return {
    ...base,
    grid: { left: 16, right: 20, top: 28, bottom: 48, containLabel: true },
    dataset: rows.map((row) => ({
      id: row.device.id,
      dimensions: ["at", "rx", "tx"],
      source: row.traffic.map((p) => [
        Date.parse(p.at),
        p.rx_bps == null ? null : p.rx_bps / 1e6,
        p.tx_bps == null ? null : p.tx_bps / 1e6,
      ]),
    })),
    xAxis: {
      type: "time",
      axisLine: { lineStyle: { color: theme["border"] } },
    },
    yAxis: {
      type: "value",
      name: "Mbit/s",
      splitLine: { lineStyle: { color: theme["grid"] } },
    },
    legend: {
      type: "scroll",
      bottom: 0,
      itemWidth: 15,
      itemHeight: 6,
      textStyle: { fontSize: 10 },
    },
    series: rows.flatMap((row) =>
      ["rx", "tx"].map((direction) => ({
        id: `${row.device.id}-${direction}`,
        name: `${row.device.name} ${direction.toUpperCase()}`,
        datasetId: row.device.id,
        type: "line",
        encode: { x: "at", y: direction },
        connectNulls: false,
        showSymbol: false,
        sampling: "lttb",
        lineStyle: {
          width: 1.8,
          type: direction === "rx" ? "solid" : "dashed",
        },
        itemStyle: { color: direction === "rx" ? colors.rx : colors.tx },
      })),
    ),
  };
}
export function capacityData(rows: Projection[]) {
  return rows.flatMap((row) =>
    row.data_state === "current"
      ? (row.telemetry?.interfaces ?? [])
          .filter(
            (s) =>
              s.capacity_bps != null &&
              row.ports.traffic_interface_ids.includes(s.interface_id) &&
              s.quality === "ok" &&
              (s.rx_bps != null || s.tx_bps != null),
          )
          .map((s) => ({
            id: `${row.device.id}:${s.interface_id}`,
            name: `${row.device.name} / ${row.device.interfaces.find((i) => i.id === s.interface_id)?.name ?? s.interface_id}`,
            rx: s.rx_bps == null ? null : (100 * s.rx_bps) / s.capacity_bps!,
            tx: s.tx_bps == null ? null : (100 * s.tx_bps) / s.capacity_bps!,
          }))
      : [],
  );
}
export function capacityOption(rows: Projection[]): EChartsCoreOption {
  const data = capacityData(rows);
  return {
    ...base,
    grid: { left: 12, top: 16, right: 25, bottom: 36, containLabel: true },
    dataset: { dimensions: ["name", "rx", "tx"], source: data },
    xAxis: {
      type: "value",
      name: "%",
      min: 0,
      max: Math.max(100, ...data.flatMap((p) => [p.rx ?? 0, p.tx ?? 0])),
      splitLine: { lineStyle: { color: theme["grid"] } },
    },
    yAxis: {
      type: "category",
      axisLabel: { width: 145, overflow: "truncate", fontSize: 10 },
      axisTick: { show: false },
      axisLine: { show: false },
    },
    legend: { bottom: 0 },
    dataZoom:
      data.length > 6
        ? [
            {
              type: "slider",
              yAxisIndex: 0,
              width: 12,
              right: 0,
              startValue: 0,
              endValue: 5,
            },
          ]
        : [],
    series: ["rx", "tx"].map((direction) => ({
      id: `capacity-${direction}`,
      name: direction.toUpperCase(),
      type: "bar",
      barMaxWidth: 12,
      encode: { x: direction, y: "name" },
      itemStyle: { color: direction === "rx" ? colors.rx : colors.tx },
    })),
  };
}
