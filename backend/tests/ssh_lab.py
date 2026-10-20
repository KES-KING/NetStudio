"""Disposable SSH fixture for browser tests. Never included in the API image."""
import asyncio
import json
import time
import asyncssh

key = asyncssh.generate_private_key("ssh-ed25519")
started = time.monotonic()
class Server(asyncssh.SSHServer):
    def begin_auth(self, username): return True
    def password_auth_supported(self): return True
    def validate_password(self, username, password): return username == "lab" and password == "lab-secret"

async def terminal(process):
    if process.command:
        # Fixed synthetic exec responses for the independent collector worker.
        ticks = int((time.monotonic() - started) * 1000)
        outputs = {
            "ip -j -s link show": json.dumps([{"ifindex": 1, "ifname": "eth1", "link_type": "ether",
                "flags": ["UP"], "operstate": "UP", "stats64": {
                    "rx": {"bytes": ticks}, "tx": {"bytes": ticks * 2}}}]),
            "ip -j address show": json.dumps([{"ifindex": 1, "addr_info": [
                {"local": "192.0.2.1", "prefixlen": 24}]}]),
            "cat /proc/uptime": f"{time.monotonic() - started:.2f} 0\n",
            "cat /proc/sys/kernel/random/boot_id": "isolated-qa-boot\n",
            "ip -j neigh show": "[]",
        }
        process.stdout.write(outputs.get(process.command, ""))
        process.exit(0 if process.command in outputs else 1)
        return
    process.stdout.write("NetStudio isolated SSH test device\r\nlab> ")
    try:
        while True:
            try:
                line = await process.stdin.readline()
                if not line: break
                process.stdout.write(f"TEST ECHO: {line.strip()}\r\nlab> ")
            except asyncssh.TerminalSizeChanged as change:
                process.stdout.write(f"\r\nPTY {change.width}x{change.height}\r\nlab> ")
    finally:
        process.exit(0)

async def public_key(reader, writer):
    await reader.read(4096)
    value = json.dumps({"public_key": key.export_public_key().decode(), "fingerprint": key.get_fingerprint()}).encode()
    writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: " + str(len(value)).encode() + b"\r\nConnection: close\r\n\r\n" + value)
    await writer.drain(); writer.close()

async def main():
    await asyncssh.create_server(Server, "0.0.0.0", 2222, server_host_keys=[key], process_factory=terminal)
    await asyncio.start_server(public_key, "0.0.0.0", 2223)
    print("Isolated SSH fixture ready", flush=True)
    await asyncio.Future()

if __name__ == "__main__": asyncio.run(main())
