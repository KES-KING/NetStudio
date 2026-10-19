"use client";

import { useEffect, useRef } from "react";
import {
  init,
  use as registerCharts,
  type ECharts,
  type EChartsCoreOption,
} from "echarts/core";
import { BarChart, LineChart, GraphChart } from "echarts/charts";
import {
  AriaComponent,
  DatasetComponent,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  DataZoomComponent,
} from "echarts/components";
import { SVGRenderer } from "echarts/renderers";

registerCharts([
  BarChart,
  LineChart,
  GraphChart,
  AriaComponent,
  DatasetComponent,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  DataZoomComponent,
  SVGRenderer,
]);

export default function EChart({
  option,
  label,
  onSelect,
  className = "",
}: {
  option: EChartsCoreOption;
  label: string;
  onSelect?: (id: string) => void;
  className?: string;
}) {
  const container = useRef<HTMLDivElement>(null);
  const instance = useRef<ECharts | null>(null);
  const select = useRef(onSelect);
  useEffect(() => {
    select.current = onSelect;
  }, [onSelect]);
  useEffect(() => {
    if (!container.current) return;
    const chart = init(container.current, undefined, { renderer: "svg" });
    instance.current = chart;
    chart.on("click", (event: { data?: unknown }) => {
      const value = event.data as { id?: string } | undefined;
      if (value?.id) select.current?.(value.id);
    });
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(container.current);
    return () => {
      observer.disconnect();
      chart.off("click");
      chart.dispose();
      instance.current = null;
    };
  }, []);
  useEffect(() => {
    instance.current?.setOption(
      {
        ...option,
        animation: false,
        aria: { enabled: true, label: { description: label } },
      },
      { notMerge: true, lazyUpdate: true },
    );
  }, [option, label]);
  return (
    <div
      className={`echart ${className}`}
      ref={container}
      role="img"
      aria-label={label}
      data-chart="echarts"
    />
  );
}
