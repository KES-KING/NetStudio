"use client";
import { useEffect, useRef, useState } from "react";
import { api, hasSessionToken } from "../lib/api";
import type { SSHTicket } from "../lib/contracts";
import type { Terminal } from "@xterm/xterm";
import { theme } from "../lib/theme";

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
  credentials_deleted: "Kimlik bilgileri silindi",
  server_shutdown: "Sunucu oturumu sonlandırdı",
  client_closed: "Oturum kapatıldı",
};

export function SSHWorkspace({
  ticket,
  name,
  onClose,
}: {
  ticket: SSHTicket;
  name: string;
  onClose: () => void;
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
        <h2>
          SSH <span> / {name}</span>
        </h2>
        <div className="toolbar-actions">
          <button onClick={copySelection}>Seçimi kopyala</button>
          <button disabled={status !== "connected"} onClick={pasteClipboard}>
            Yapıştır
          </button>
          <button onClick={onClose}>Oturumu kapat</button>
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
