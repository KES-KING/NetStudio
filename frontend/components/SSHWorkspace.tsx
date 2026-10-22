"use client";
import { useEffect, useRef, useState } from "react";
import { api, hasSessionToken } from "../lib/api";
import type { SSHTicket } from "../lib/contracts";
import type { Terminal } from "@xterm/xterm";
import { theme } from "../lib/theme";

export type SSHWorkspaceView = "inline" | "expanded" | "fullscreen";

function ViewIcon({ view }: { view: SSHWorkspaceView }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      {view === "inline" && (
        <>
          <rect x="3" y="5" width="18" height="14" />
          <path d="M10 5v14" />
        </>
      )}
      {view === "expanded" && (
        <>
          <rect x="3" y="4" width="18" height="16" />
          <path d="M3 10h18M8 7H5m14 0h-3" />
        </>
      )}
      {view === "fullscreen" && (
        <path d="M9 4H4v5m11-5h5v5M9 20H4v-5m11 5h5v-5" />
      )}
    </svg>
  );
}

const messages: Record<string, string> = {
  connecting: "Bağlantı kuruluyor",
  connected: "Bağlandı",
  authentication_failed: "Kimlik doğrulama başarısız",
  connection_timeout: "Bağlantı zaman aşımına uğradı",
  disconnected: "Bağlantı kesildi",
  ended: "Oturum sona erdi",
  session_ended: "Oturum sona erdi",
  session_expired: "Oturum süresi doldu",
  idle_timeout: "Boşta kalma süresi doldu",
  session_revoked: "Oturum veya yetki geçersiz",
  host_key_changed: "Host anahtarı değişti; bağlantı durduruldu",
  connection_failed: "SSH bağlantısı kurulamadı",
  ssh_algorithms_incompatible: "SSH algoritmaları uyuşmuyor; cihazın uyumluluk profilini kontrol edin",
  device_connection_changed: "Cihazın bağlantı ayarları değişti; yeniden bağlanın",
  credentials_deleted: "Kimlik bilgileri silindi",
  server_shutdown: "Sunucu oturumu sonlandırdı",
  client_closed: "Oturum kapatıldı",
};

export function SSHWorkspace({
  ticket,
  name,
  onClose,
  commandHelperOpen,
  onToggleCommandHelper,
  view,
  onViewChange,
}: {
  ticket: SSHTicket;
  name: string;
  onClose: () => void;
  commandHelperOpen: boolean;
  onToggleCommandHelper: () => void;
  view: SSHWorkspaceView;
  onViewChange: (view: SSHWorkspaceView) => void;
}) {
  const element = useRef<HTMLDivElement>(null);
  const terminalRef = useRef<Terminal | null>(null);
  const [clipboardMessage, setClipboardMessage] = useState("");
  const [status, setStatus] = useState("connecting");
  async function copySelection() {
    const selection = terminalRef.current?.getSelection();
    if (!selection) {
      setClipboardMessage("Önce terminalde kopyalanacak metni seçin.");
      return;
    }
    try {
      await navigator.clipboard.writeText(selection);
      setClipboardMessage("Seçim kopyalandı.");
    } catch {
      setClipboardMessage(
        "Pano izni yok. Tarayıcının kopyalama menüsünü kullanın.",
      );
    }
  }
  async function pasteClipboard() {
    try {
      const value = await navigator.clipboard.readText();
      terminalRef.current?.paste(value);
      terminalRef.current?.focus();
      setClipboardMessage("");
    } catch {
      setClipboardMessage("Pano izni yok. Ctrl+Shift+V ile yapıştırın.");
    }
  }
  useEffect(() => {
    let disposed = false;
    let cleanup: (() => void) | undefined;
    async function start() {
      const [{ Terminal }, { FitAddon }] = await Promise.all([
        import("@xterm/xterm"),
        import("@xterm/addon-fit"),
      ]);
      if (disposed || !element.current) return;
      const terminal = new Terminal({
        cursorBlink: true,
        fontSize: 13,
        fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace",
        scrollback: 2000,
        theme: {
          background: theme.terminal,
          foreground: theme["terminal-text"],
          cursor: theme.surface,
          selectionBackground: "#465B70",
        },
        allowProposedApi: false,
      });
      const fit = new FitAddon();
      terminal.loadAddon(fit);
      terminal.open(element.current);
      terminalRef.current = terminal;
      terminal.attachCustomKeyEventHandler((event) => {
        if (
          event.type === "keydown" &&
          event.ctrlKey &&
          event.shiftKey &&
          event.code === "KeyC"
        ) {
          event.preventDefault();
          void copySelection();
          return false;
        }
        return true;
      });
      const url = new URL(ticket.websocket_path, window.location.origin);
      url.protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const socket = new WebSocket(url);
      let connected = false,
        ended = false;
      function send(value: object) {
        if (socket.readyState === WebSocket.OPEN)
          socket.send(JSON.stringify(value));
      }
      function resize() {
        if (disposed) return;
        fit.fit();
        if (connected)
          send({
            type: "resize",
            cols: Math.min(400, Math.max(20, terminal.cols)),
            rows: Math.min(200, Math.max(5, terminal.rows)),
          });
      }
      const observer = new ResizeObserver(resize);
      observer.observe(element.current);
      const input = terminal.onData((data) => {
        if (connected) {
          // Keep each frame below the server's 16 KiB limit, including JSON escapes.
          for (let offset = 0; offset < data.length; offset += 1024)
            send({ type: "input", data: data.slice(offset, offset + 1024) });
        }
      });
      socket.onmessage = (event) => {
        let value;
        try {
          value = JSON.parse(event.data);
        } catch {
          socket.close();
          return;
        }
        if (value.type === "output" && typeof value.data === "string")
          terminal.write(value.data);
        if (value.type === "status") {
          setStatus(value.status);
          connected = value.status === "connected";
          ended = !["connecting", "connected"].includes(value.status);
          if (connected) {
            resize();
            terminal.focus();
          }
        }
      };
      socket.onerror = () => {
        if (!disposed) {
          ended = true;
          setStatus("connection_failed");
        }
      };
      socket.onclose = () => {
        connected = false;
        if (!disposed && !ended) setStatus("disconnected");
      };
      resize();
      cleanup = () => {
        connected = false;
        observer.disconnect();
        input.dispose();
        socket.onmessage = socket.onclose = socket.onerror = null;
        socket.close();
        terminalRef.current = null;
        terminal.dispose();
        // Logout already revokes the server-side terminal. Do not send a
        // redundant authenticated cleanup request after the cookie is removed.
        if (hasSessionToken())
          void api(`/api/v1/ssh-sessions/${ticket.id}`, {
            method: "DELETE",
            keepalive: true,
          }).catch(() => {});
      };
    }
    void start().catch(() => {
      if (!disposed) setStatus("connection_failed");
    });
    return () => {
      disposed = true;
      cleanup?.();
    };
  }, [ticket.id, ticket.websocket_path]);
  return (
    <section className="ssh-workspace" aria-label={`${name} SSH terminali`}>
      <div className="ssh-heading">
        <div className="ssh-title">
          <span>Güvenli terminal</span>
          <h2>
            SSH <small> / {name}</small>
          </h2>
        </div>
        <div className="ssh-toolbar">
          <div className="ssh-view-switcher" role="group" aria-label="SSH görünümü">
            <button
              aria-label="Standart SSH görünümüne dön"
              title="Cihaz paneli ve terminali yan yana göster"
              aria-pressed={view === "inline"}
              onClick={() => onViewChange("inline")}
            >
              <ViewIcon view="inline" />
              <span>Standart</span>
            </button>
            <button
              aria-label="SSH görünümünü büyüt"
              title="Cihazı, terminali ve komut yardımcısını tam genişlikte göster"
              aria-pressed={view === "expanded"}
              onClick={() => onViewChange("expanded")}
            >
              <ViewIcon view="expanded" />
              <span>Büyüt</span>
            </button>
            <button
              aria-label="SSH terminalini tam ekran yap"
              title="Menüleri koruyarak terminali içerik alanına yay"
              aria-pressed={view === "fullscreen"}
              onClick={() => onViewChange("fullscreen")}
            >
              <ViewIcon view="fullscreen" />
              <span>Tam ekran</span>
            </button>
          </div>
          <div className="ssh-session-actions">
            <button
              className="ssh-command-helper-toggle"
              aria-label={
                commandHelperOpen
                  ? "Komut yardımcısını kapat"
                  : "Komut yardımcısını aç"
              }
              aria-pressed={commandHelperOpen}
              title={
                commandHelperOpen
                  ? "Komut yardımcısını kapat"
                  : "Komut yardımcısını aç"
              }
              onClick={onToggleCommandHelper}
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M3 5.5h13v13H3z" />
                <path d="m6 10 2 2-2 2m4 1h3" />
                <circle cx="18" cy="6" r="4" />
                <path d="M16.8 4.9a1.35 1.35 0 0 1 2.55.62c0 .95-1.35 1.05-1.35 1.85m0 1.4v.1" />
              </svg>
              <span>Komutlar</span>
            </button>
            <button aria-label="Seçimi kopyala" onClick={copySelection}>Kopyala</button>
            <button disabled={status !== "connected"} onClick={pasteClipboard}>
              Yapıştır
            </button>
            <button className="ssh-close-session" onClick={onClose}>Oturumu kapat</button>
          </div>
        </div>
      </div>
      <div className="terminal-status" role="status">
        <span
          className={`status ${status === "connected" ? "reachable" : "unknown"}`}
        >
          {messages[status] ?? "Oturum sona erdi"}
        </span>
        <span>Şifreli SSH · Host anahtarı doğrulaması</span>
      </div>
      <div className="terminal-container" ref={element} />
      <p className="terminal-help">
        {clipboardMessage && (
          <span role="status">
            {clipboardMessage}
            <br />
          </span>
        )}
        Kopyala: Ctrl+Shift+C / sağ tık · Yapıştır: Ctrl+Shift+V · Panel
        kapatılınca uzak oturum sonlandırılır.
      </p>
    </section>
  );
}
