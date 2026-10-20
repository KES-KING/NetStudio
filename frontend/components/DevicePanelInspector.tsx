"use client";

import { useId, useLayoutEffect, useRef, useState } from "react";
import type { PhysicalPort, Projection } from "../lib/contracts";
import { formatTime } from "../lib/metrics";
import { placePortPopover } from "../lib/port-popover";
import { DevicePanel, PortDetails } from "./DevicePanel";

export function PortPopover({
  row, port, anchor, onClose, zoom = 100,
}: {
  row: Projection;
  port: PhysicalPort;
  anchor: HTMLButtonElement;
  onClose: () => void;
  zoom?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const reposition = useRef<() => void>(() => {});
  const id = useId();
  useLayoutEffect(() => {
    const popup = ref.current!;
    let frame = 0;
    // A manual popover also works inside the fullscreen dialog's top layer.
    // Older browsers retain the fixed-position fallback.
    if (typeof popup.showPopover === "function") popup.showPopover();
    else popup.removeAttribute("popover");
    anchor.setAttribute("aria-controls", id);
    anchor.setAttribute("aria-expanded", "true");
    const position = () => {
      frame = 0;
      if (!anchor.isConnected) return;
      const viewport = window.visualViewport;
      const bounds = {
        width: viewport?.width ?? window.innerWidth,
        height: viewport?.height ?? window.innerHeight,
        left: viewport?.offsetLeft ?? 0,
        top: viewport?.offsetTop ?? 0,
      };
      // Keep fullscreen close/zoom controls usable, even on landscape phones.
      const stage = anchor.closest(".inspector-stage")?.getBoundingClientRect();
      if (stage) {
        const bottom = Math.min(bounds.top + bounds.height, stage.bottom);
        bounds.top = Math.max(bounds.top, stage.top);
        bounds.height = Math.max(0, bottom - bounds.top);
      }
      // First apply responsive width so wrapped content height is measured correctly.
      popup.style.width = `${Math.min(380, bounds.width - 24)}px`;
      const placement = placePortPopover(anchor.getBoundingClientRect(), bounds, popup.scrollHeight + 2);
      popup.style.left = `${placement.left}px`;
      popup.style.top = `${placement.top}px`;
      popup.style.maxHeight = `${placement.maxHeight}px`;
      popup.dataset.side = placement.side;
    };
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(position);
    };
    reposition.current = position;
    const escape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      event.stopPropagation();
      onClose();
    };
    position();
    popup.querySelector<HTMLButtonElement>("button")?.focus({ preventScroll: true });
    // Only the open inspector owns these listeners. Scrolling a chassis also repositions it.
    document.addEventListener("scroll", schedule, true);
    window.addEventListener("resize", schedule);
    window.visualViewport?.addEventListener("resize", schedule);
    window.visualViewport?.addEventListener("scroll", schedule);
    window.addEventListener("keydown", escape, true);
    const observer = new ResizeObserver(schedule);
    observer.observe(anchor);
    observer.observe(popup);
    if (popup.firstElementChild) observer.observe(popup.firstElementChild);
    return () => {
      document.removeEventListener("scroll", schedule, true);
      window.removeEventListener("resize", schedule);
      window.visualViewport?.removeEventListener("resize", schedule);
      window.visualViewport?.removeEventListener("scroll", schedule);
      window.removeEventListener("keydown", escape, true);
      observer.disconnect();
      cancelAnimationFrame(frame);
      anchor.removeAttribute("aria-controls");
      anchor.removeAttribute("aria-expanded");
      const restoreFocus = popup.contains(document.activeElement);
      if (typeof popup.hidePopover === "function" && popup.matches(":popover-open")) popup.hidePopover();
      if (restoreFocus && anchor.isConnected) anchor.focus({ preventScroll: true });
    };
  }, [anchor, id, onClose]);
  useLayoutEffect(() => { reposition.current(); }, [zoom, row]);
  return (
    <div ref={ref} id={id} popover="manual" className="port-popover">
      <PortDetails row={row} port={port} onClose={onClose} />
    </div>
  );
}

export function DevicePanelInspector({
  row, selected, anchor, onSelect, onClosePort, onClose,
}: {
  row: Projection;
  selected?: PhysicalPort;
  anchor?: HTMLButtonElement;
  onSelect: (port: PhysicalPort, anchor: HTMLButtonElement) => void;
  onClosePort: () => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [zoom, setZoom] = useState(125);
  useLayoutEffect(() => {
    const dialog = ref.current!;
    const previous = document.activeElement;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog.showModal();
    return () => {
      dialog.close();
      document.body.style.overflow = overflow;
      if (previous instanceof HTMLElement && previous.isConnected) previous.focus({ preventScroll: true });
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className="panel-inspector"
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault();
        if (anchor) onClosePort();
        else onClose();
      }}
    >
      <header className="inspector-header">
        <div>
          <p className="inspector-eyebrow">CİHAZ ÖN PANELİ</p>
          <h2 id={titleId}>{row.device.name} <span>· {row.device.model || "Model belirtilmedi"}</span></h2>
        </div>
        <button autoFocus onClick={onClose} aria-label="Tam ekranı kapat">Kapat <span aria-hidden="true">×</span></button>
      </header>
      <div className="inspector-toolbar">
        <p>Porta tıklayın · Geniş paneli yatay kaydırın</p>
        <div className="inspector-zoom" role="group" aria-label="Ön panel yakınlaştırma">
          <button aria-label="Ön paneli uzaklaştır" disabled={zoom <= 100} onClick={() => setZoom((value) => value - 25)}>−</button>
          <output aria-label="Ön panel yakınlaştırma oranı">{zoom}%</output>
          <button aria-label="Ön paneli yakınlaştır" disabled={zoom >= 250} onClick={() => setZoom((value) => value + 25)}>+</button>
          <button onClick={() => setZoom(125)}>Sıfırla</button>
        </div>
      </div>
      <div className="inspector-stage">
        <div className="inspector-panel" style={{ zoom: zoom / 100 }}>
          <DevicePanel row={row} selectedId={selected?.id} onSelect={onSelect} />
        </div>
      </div>
      <footer className="inspector-footer">
        <span>Şematik envanter · Fiziksel kablo bağlantısı kanıtı değildir.</span>
        <span>Port gözlemi: {formatTime(row.telemetry?.observed_at)}</span>
      </footer>
      {selected && anchor && <PortPopover row={row} port={selected} anchor={anchor} onClose={onClosePort} zoom={zoom} />}
    </dialog>
  );
}
