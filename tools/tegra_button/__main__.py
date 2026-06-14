"""tegra-button: USB control of a Jetson Orin Nano Devkit."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .board import Board, BoardError
from .flash import ArtifactError, FlashError, TegraflashArtifact, flash

__version__ = "1.0.0"
DESCRIPTION = "Control a Jetson Orin Nano Devkit over USB: recovery, power, serial, flashing."


def _board(args: argparse.Namespace) -> Board:
    return Board.open(args.id)


def cmd_power(args: argparse.Namespace) -> None:
    _board(args).power(args.action)


def cmd_serial(args: argparse.Namespace) -> None:
    _board(args).bridge(Path(args.log) if args.log else None)


def cmd_flash(args: argparse.Namespace) -> None:
    sha = flash(
        _board(args),
        TegraflashArtifact(Path(args.artifact)),
        workdir=Path(args.workdir) if args.workdir else None,
        log=Path(args.log) if args.log else None,
        usb_instance=args.usb_instance,
    )
    print(f"flashed (sha256 {sha[:16]})")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="tegra-button", description=DESCRIPTION)
    ap.add_argument("--version", action="version", version=__version__)
    ap.add_argument("--id", metavar="ID", help="select a board by USB serial number")
    sub = ap.add_subparsers(dest="cmd", metavar="<command>", required=True)

    pwr = sub.add_parser("power", help="turn the board on or off, or power-cycle it")
    pwr.add_argument("action", choices=("on", "off", "cycle"))
    pwr.set_defaults(func=cmd_power)

    ser = sub.add_parser("serial", help="bridge the board's serial console to stdin/stdout")
    ser.add_argument("--log", metavar="FILE", help="also write console output to this file")
    ser.set_defaults(func=cmd_serial)

    fl = sub.add_parser("flash", help="recover the board and flash a tegraflash artifact")
    fl.add_argument("artifact", help="path to the .tegraflash-tar.zst bundle")
    fl.add_argument("--usb-instance", metavar="BUS:PORT",
                    help="route initrd-flash to one DUT on a multi-board host")
    fl.add_argument("--workdir", metavar="DIR", help="extract here instead of a temp directory")
    fl.add_argument("--log", metavar="FILE", help="write the flash log to this file")
    fl.set_defaults(func=cmd_flash)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except (BoardError, ArtifactError, FlashError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
