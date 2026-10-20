import type { Metadata } from "next";
import "./globals.css";
import "@xterm/xterm/css/xterm.css";
import { ConsoleShell } from "../components/ConsoleShell";
import { cssTokens } from "../lib/theme";

export const metadata: Metadata = {
  title: "NetStudio",
  description:
    "Ağ cihazı envanteri, gerçek gözlemler ve güvenli SSH yönetim konsolu.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="tr" style={cssTokens as React.CSSProperties}>
      <body>
        <ConsoleShell>{children}</ConsoleShell>
      </body>
    </html>
  );
}
