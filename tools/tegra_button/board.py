"""Discover and drive the tegra-button appliance over its control CDC."""
from __future__ import annotations

import contextlib
import os
import select
import sys
import time
from pathlib import Path

import serial as pyserial
from serial.tools import list_ports

VID           = 0x1209
PID           = 0x0001
BAUD          = 115200
ACK_TIMEOUT_S = 2.0

# Host-side sequence timing; the firmware holds no timers, only line state.
RESET_PULSE_S   = 0.2
RECOV_SETTLE_S  = 0.05
RECOV_RELEASE_S = 1.0
POWER_ON_S      = 0.1
POWER_OFF_S     = 10.5
POWER_GAP_S     = 0.3

LINES = ("recov", "reset", "power")


class BoardError(Exception):
    pass


def _iface(port: object) -> int:
    # USB location is like "7-1:1.0"; the trailing number is the interface index.
    loc = getattr(port, "location", None) or ""
    tail = loc.rsplit(".", 1)[-1]
    return int(tail) if tail.isdigit() else 0


def discover() -> list["Board"]:
    # Pair the two CDC interfaces by USB interface order: button (control) is the
    # lower one, serial (console) the next. No reliance on descriptor strings.
    by_id: dict[str, list[tuple[int, str]]] = {}
    for p in list_ports.comports():
        if p.vid != VID or p.pid != PID or p.serial_number is None:
            continue
        by_id.setdefault(p.serial_number, []).append((_iface(p), p.device))
    boards = []
    for id, ttys in by_id.items():
        if len(ttys) < 2:
            continue
        ttys.sort()
        boards.append(Board(id, ttys[0][1], ttys[1][1]))
    return sorted(boards, key=lambda b: b.id)


class Board:
    def __init__(self, id: str, button: str, serial: str):
        self.id = id          # USB serial number
        self.button = button  # control tty (drives the J14 lines)
        self.serial = serial  # console tty (Jetson UART bridge)

    @classmethod
    def open(cls, id: str | None = None) -> "Board":
        boards = discover()
        if not boards:
            raise BoardError("no board found")
        if id is not None:
            for b in boards:
                if b.id == id:
                    return b
            raise BoardError(f"no board with id {id}")
        if len(boards) > 1:
            raise BoardError("multiple boards connected; select one with --id "
                             f"({', '.join(b.id for b in boards)})")
        return boards[0]

    def _send(self, port: pyserial.Serial, token: str) -> None:
        port.reset_input_buffer()
        port.write((token + "\n").encode())
        port.flush()
        deadline = time.monotonic() + ACK_TIMEOUT_S
        while time.monotonic() < deadline:
            resp = port.readline().decode(errors="replace").strip()
            if not resp:
                continue
            if resp != "OK":
                raise BoardError(f"{token!r} rejected: {resp}")
            return
        raise BoardError(f"no ack for {token!r}")

    def _run(self, steps: list[tuple[str, float]]) -> None:
        # Hold the button port open across the sequence; release every line in
        # finally so a fault can't strand one asserted.
        with pyserial.Serial(self.button, BAUD, timeout=1) as port:
            try:
                for token, hold in steps:
                    self._send(port, token)
                    if hold:
                        time.sleep(hold)
            finally:
                for line in LINES:
                    with contextlib.suppress(BoardError, OSError):
                        self._send(port, f"{line}=0")

    def recov(self) -> None:
        # Cold RCM entry: force the board fully off first (a long power hold ends OFF
        # from any state), then power on with recovery asserted. A warm reset alone
        # leaves NVMe/PCIe initialised, which makes a re-flash hang at
        # `export-devices nvme0n1` (LUN: no medium); a cold start clears it.
        self._run([
            ("power=1", POWER_OFF_S),
            ("power=0", POWER_GAP_S),
            ("recov=1", RECOV_SETTLE_S),
            ("power=1", POWER_ON_S),
            ("power=0", RECOV_RELEASE_S),
            ("recov=0", 0.0),
        ])

    def power(self, action: str) -> None:
        if action == "on":
            self._run([("power=1", POWER_ON_S), ("power=0", 0.0)])
        elif action == "off":
            self._run([("power=1", POWER_OFF_S), ("power=0", 0.0)])
        else:  # cycle
            self._run([("power=1", POWER_OFF_S), ("power=0", POWER_GAP_S),
                       ("power=1", POWER_ON_S), ("power=0", 0.0)])

    def bridge(self, log: Path | None = None) -> None:
        # Raw byte bridge: serial console CDC <-> stdin/stdout, no terminal cooking,
        # exits on stdin EOF. Used interactively and as oeqa serial control.
        log_ctx = open(log, "ab") if log else contextlib.nullcontext()
        with log_ctx as logf, pyserial.Serial(self.serial, BAUD, timeout=0) as port:
            try:
                while True:
                    readable, _, _ = select.select([sys.stdin, port], [], [])
                    if sys.stdin in readable:
                        data = os.read(sys.stdin.fileno(), 1024)
                        if not data:
                            break
                        port.write(data)
                    if port in readable:
                        data = port.read(4096)
                        if data:
                            os.write(sys.stdout.fileno(), data)
                            if logf:
                                logf.write(data)
                                logf.flush()
            except KeyboardInterrupt:
                pass
