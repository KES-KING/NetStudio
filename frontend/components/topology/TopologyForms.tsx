"use client";
import { useState } from "react";
import { Dialog } from "../DeviceForms";
import { type ManualLink, type NetworkGraph, type TopologyBoard, type Zone } from "../../lib/topology";

export function AddZone({ board, onAdd, onClose }: { board: TopologyBoard; onAdd: (zone: Zone) => void; onClose: () => void }) {
  return <Dialog title="Zone ekle" onClose={onClose}><form className="topology-form" onSubmit={(e) => {
    e.preventDefault(); const data = new FormData(e.currentTarget);
    onAdd({ id: crypto.randomUUID(), name: String(data.get("name")).trim(), x: 30 + (board.zones.length % 3) * 680, y: 30 + Math.floor(board.zones.length / 3) * 600, width: 620, height: 540, tone: data.get("tone") as Zone["tone"] });
  }}><label>Zone adı<input name="name" required maxLength={80} pattern=".*\S.*" autoFocus /></label>
    <label>Yüzey tonu<select name="tone"><option value="slate">Gri</option><option value="blue">Mavi gri</option><option value="sand">Kum</option></select></label>
    <p>Zone’u oluşturduktan sonra cihaz seçip zone ataması yapabilirsiniz. Değişiklikleri sunucuda saklamak için Kaydet’i kullanın.</p>
    <button className="primary" disabled={board.zones.length >= 40}>Zone oluştur</button>
  </form></Dialog>;
}

export function AddConnection({ graph, board, onAdd, onClose }: { graph: NetworkGraph; board: TopologyBoard; onAdd: (link: ManualLink) => void; onClose: () => void }) {
  const candidates = graph.devices.filter((d) => d.ports.length);
  const [sourceId, setSourceId] = useState(candidates[0]?.id ?? ""), [targetId, setTargetId] = useState(candidates[1]?.id ?? "");
  const [error, setError] = useState("");
  const source = candidates.find((d) => d.id === sourceId), target = candidates.find((d) => d.id === targetId);
  return <Dialog title="Portlar arasında bağlantı ekle" onClose={onClose}>
    <p className="notice">Bu bir kullanıcı çizimidir. Cihaza komut göndermez; fiziksel bağlantı doğrulamaz.</p>
    {candidates.length < 2 ? <p>En az iki cihazda fiziksel port envanteri bulunmalı. Cihaz detaylarından doğrulanmış envanteri ekleyin.</p> : <form className="topology-form" onSubmit={(e) => {
      e.preventDefault(); const form = new FormData(e.currentTarget);
      const link = { id: crypto.randomUUID(), source_device_id: sourceId, target_device_id: targetId, source_port_id: String(form.get("source_port")), target_port_id: String(form.get("target_port")) };
      if (sourceId === targetId) { setError("İki farklı cihaz seçin."); return; }
      if (board.links.some((l) => l.source_device_id === sourceId && l.target_device_id === targetId && l.source_port_id === link.source_port_id && l.target_port_id === link.target_port_id || l.target_device_id === sourceId && l.source_device_id === targetId && l.target_port_id === link.source_port_id && l.source_port_id === link.target_port_id)) { setError("Bu port çifti zaten çizilmiş."); return; }
      onAdd(link);
    }}>
      <label>Kaynak cihaz<select value={sourceId} onChange={(e) => setSourceId(e.target.value)}>{candidates.map((d) => <option key={d.id} value={d.id}>{d.name} · {d.management_address}</option>)}</select></label>
      <label>Kaynak port<select key={`source:${sourceId}`} name="source_port" required>{source?.ports.map((p) => <option key={p.id} value={p.id}>{p.label} · {p.connector}{p.parent_port_id ? " · breakout" : ""}</option>)}</select></label>
      <label>Hedef cihaz<select value={targetId} onChange={(e) => setTargetId(e.target.value)}>{candidates.map((d) => <option key={d.id} value={d.id}>{d.name} · {d.management_address}</option>)}</select></label>
      <label>Hedef port<select key={`target:${targetId}`} name="target_port" required>{target?.ports.map((p) => <option key={p.id} value={p.id}>{p.label} · {p.connector}{p.parent_port_id ? " · breakout" : ""}</option>)}</select></label>
      {error && <p role="alert" className="notice error">{error}</p>}<button className="primary" disabled={!source || !target || board.links.length >= 500}>Bağlantıyı çiz</button>
    </form>}
  </Dialog>;
}
