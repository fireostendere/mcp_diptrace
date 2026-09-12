"""Host-side MCP server for the DUT Controller Rev.A (Python 3 stdlib only).
 *
 * JSON-RPC 2.0 over stdio. Tools expose hardware primitives; a DUT profile
 maps semantic names (power.main, button.reset, uart.console, rail_3v3) to
 physical channels so the agent never sees GPIO numbers.

 Transport to device: serial (pyserial if available) or TCP, selected by
 --device. Without a device the server runs in MOCK mode so tools can be
 introspected and profiles validated offline.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


class Device:
    def __init__(self, spec: str):
        self.spec = spec
        self.sock = None
        self.ser = None
        if spec.startswith("tcp://"):
            host, port = spec[6:].rsplit(":", 1)
            self.sock = socket.create_connection((host, int(port)), timeout=5)
        elif spec == "mock":
            pass
        else:
            try:
                import serial  # type: ignore
                self.ser = serial.Serial(spec, 115200, timeout=5)
            except ImportError:
                print("pyserial not installed; falling back to mock", file=sys.stderr)
                self.spec = "mock"

    def rpc(self, cmd: str, **args) -> dict:
        rid = int(time.time() * 1000) & 0x7FFFFFFF
        req = {"id": rid, "cmd": cmd, **args}
        line = json.dumps(req) + "\n"
        if self.sock:
            self.sock.sendall(line.encode())
            buf = b""
            while b"\n" not in buf:
                chunk = self.sock.recv(4096)
                if not chunk:
                    raise ConnectionError("device closed")
                buf += chunk
            return json.loads(buf.split(b"\n")[0])
        if self.ser:
            self.ser.write(line.encode())
            resp = self.ser.readline().decode(errors="replace")
            return json.loads(resp or "{}")
        return {"id": rid, "ok": True, "mock": True, "echo": req}


def load_profile(path: str | None) -> dict:
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        prof = json.load(fh)

    def resolve(node):
        if isinstance(node, dict):
            if set(node) == {"ch"}:
                return node["ch"]
            return {k: resolve(v) for k, v in node.items()}
        if isinstance(node, list):
            return [resolve(v) for v in node]
        return node

    return resolve(prof)


TOOLS = [
    ("controller.get_info", {}, "firmware/protocol version, uptime, transports"),
    ("power.on", {"name": "str"}, "switch profiled power channel on"),
    ("power.off", {"name": "str"}, "switch profiled power channel off"),
    ("power.cycle", {"name": "str", "delay_ms": "int"}, "off->delay->on"),
    ("power.measure", {"name": "str"}, "voltage/current via INA226"),
    ("usb.set_power", {"port": "int", "state": "bool"}, "VBUS on/off for USB port"),
    ("usb.set_data", {"port": "int", "state": "bool"}, "data path connect/disconnect (interlocked)"),
    ("usb.replug", {"port": "int", "delay_ms": "int"}, "data off->delay->on"),
    ("button.press", {"name": "str", "duration_ms": "int"}, "PhotoMOS press"),
    ("button.hold", {"name": "str"}, "close and keep"),
    ("button.release", {"name": "str"}, "open"),
    ("uart.configure", {"name": "str", "baud": "int"}, "set baud on UART port"),
    ("uart.set_route", {"name": "str", "route": "normal|swapped|rx_only|off"}, ""),
    ("uart.read", {"name": "str", "max": "int"}, "drain capture buffer"),
    ("uart.write", {"name": "str", "data_b64": "str"}, ""),
    ("uart.wait", {"name": "str", "pattern": "str", "timeout_ms": "int"}, ""),
    ("gpio.configure", {"name": "str", "mode": "in|out|od|pwm"}, ""),
    ("gpio.read", {"name": "str"}, ""), ("gpio.write", {"name": "str", "value": "int"}, ""),
    ("adc.read", {"name": "str"}, "millivolts via ADS7830 divider map"),
    ("events.get", {"since_us": "int"}, "timestamped event batch"),
    ("sequence.run", {"ops": "list"}, "deterministic local sequence"),
    ("sequence.cancel", {"seq_id": "int"}, ""),
]


def tool_manifest(profile: dict) -> list[dict]:
    out = []
    for name, args, desc in TOOLS:
        out.append({"name": name.replace(".", "_"), "description": f"{name}: {desc}",
                    "inputSchema": {"type": "object", "properties": {
                        k: {"type": v} for k, v in args.items()}}})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="mock", help="serial port or tcp://host:port or mock")
    ap.add_argument("--profile", default=os.path.join(HERE, "profiles", "test_router.json"))
    args = ap.parse_args()

    dev = Device(args.device)
    profile = load_profile(args.profile)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("method") == "initialize":
            resp = {"jsonrpc": "2.0", "id": msg.get("id"), "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "dut-controller-mcp", "version": "0.1.0"}}}
        elif msg.get("method") == "tools/list":
            resp = {"jsonrpc": "2.0", "id": msg.get("id"), "result": {"tools": tool_manifest(profile)}}
        elif msg.get("method") == "tools/call":
            params = msg.get("params", {})
            name = params.get("name", "").replace("_", ".")
            targs = params.get("arguments", {})
            # semantic-name resolution happens against the loaded profile
            result = dev.rpc(name, **targs, profile=profile.get("map", {}))
            resp = {"jsonrpc": "2.0", "id": msg.get("id"), "result":
                    {"content": [{"type": "text", "text": json.dumps(result)}]}}
        else:
            resp = {"jsonrpc": "2.0", "id": msg.get("id"),
                    "error": {"code": -32601, "message": "method not found"}}
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
