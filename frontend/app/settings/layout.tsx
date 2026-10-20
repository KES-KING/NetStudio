import type { ReactNode } from "react";
import { SettingsLayout } from "../../components/SettingsLayout";
export default function Layout({ children }: { children: ReactNode }) { return <SettingsLayout>{children}</SettingsLayout>; }
