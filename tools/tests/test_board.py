from dataclasses import dataclass

import pytest

from tegra_button import board
from tegra_button.board import PID, VID, Board, BoardError, discover


@dataclass
class FakePort:
    vid: int
    pid: int
    serial_number: str
    location: str
    device: str


def _set_ports(monkeypatch, ports):
    monkeypatch.setattr(board.list_ports, "comports", lambda: ports)


def test_discover_pairs_by_interface_order(monkeypatch):
    _set_ports(monkeypatch, [
        FakePort(VID, PID, "ABC", "7-1:1.2", "/dev/ttyACM1"),
        FakePort(VID, PID, "ABC", "7-1:1.0", "/dev/ttyACM0"),
        FakePort(0x1234, 0x5678, "X", "9-1:1.0", "/dev/ttyACM9"),
    ])
    found = discover()
    assert len(found) == 1
    assert (found[0].id, found[0].button, found[0].serial) == (
        "ABC", "/dev/ttyACM0", "/dev/ttyACM1")


def test_discover_skips_incomplete(monkeypatch):
    _set_ports(monkeypatch, [
        FakePort(VID, PID, "ABC", "7-1:1.0", "/dev/ttyACM0"),
    ])
    assert discover() == []


def test_open_multiple_requires_id(monkeypatch):
    _set_ports(monkeypatch, [
        FakePort(VID, PID, "A", "7-1:1.0", "/dev/ttyACM0"),
        FakePort(VID, PID, "A", "7-1:1.2", "/dev/ttyACM1"),
        FakePort(VID, PID, "B", "7-2:1.0", "/dev/ttyACM2"),
        FakePort(VID, PID, "B", "7-2:1.2", "/dev/ttyACM3"),
    ])
    with pytest.raises(BoardError):
        Board.open()
    assert Board.open("B").serial == "/dev/ttyACM3"


def test_open_none(monkeypatch):
    _set_ports(monkeypatch, [])
    with pytest.raises(BoardError):
        Board.open()
