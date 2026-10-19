import { Suspense } from "react";
import TopologyWorkspace from "../../components/topology/TopologyWorkspace";
import "./topology.css";

export default function Page() {
  return <Suspense fallback={<p role="status">Topoloji yükleniyor…</p>}><TopologyWorkspace /></Suspense>;
}
