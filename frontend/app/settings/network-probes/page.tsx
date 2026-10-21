"use client";
import NetworkProbesPage from "../../../components/NetworkProbesPage";
import { useSession } from "../../../components/ConsoleShell";
export default function Page() {
  const session = useSession();
  return session.permissions.includes("network_probe.manage") ? <NetworkProbesPage />
    : <p role="alert" className="notice">Ağ keşfi yönetimi için superadmin yetkisi gerekir.</p>;
}
