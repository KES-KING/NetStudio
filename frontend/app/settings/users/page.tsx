"use client";
import { UserDirectory } from "../../../components/UserDirectory";
import { useSession } from "../../../components/ConsoleShell";
export default function Page() {
  const session = useSession();
  return session.permissions.includes("user.manage") ? <UserDirectory /> : <p role="alert" className="notice">Kullanıcı yönetimi için superadmin yetkisi gerekir.</p>;
}
