"""Tegraflash artifact handling and the initrd-flash run."""
from __future__ import annotations

import glob
import hashlib
import os
import select
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from .board import Board

FLASH_MARKER = "initrd-flash"
RCM_VID = "0955"
# Orin Nano/NX (+AGX Orin) RCM product IDs, per the OE4T udev rules.
RCM_PIDS = ("7523", "7623", "7323", "7423", "7023")
FLASH_TIMEOUT_S = 1800.0
RCM_WAIT_S = 30.0


class ArtifactError(Exception):
    pass


class FlashError(Exception):
    pass


@dataclass
class TegraflashArtifact:
    path: Path

    def __post_init__(self) -> None:
        self.path = Path(self.path)
        if not self.path.is_file():
            raise ArtifactError(f"artifact not found: {self.path}")

    def _names(self) -> list[str]:
        # tar auto-detects compression on read; no stdlib zstd dependency needed.
        try:
            out = subprocess.run(["tar", "-tf", str(self.path)],
                                 capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError as exc:
            raise ArtifactError(f"failed to read artifact: {exc.stderr.strip()}") from exc
        return [n for n in out.stdout.split("\n") if n]

    def validate(self) -> None:
        if FLASH_MARKER not in {Path(n).name for n in self._names()}:
            raise ArtifactError(f"no {FLASH_MARKER} in {self.path}")

    def sha256(self) -> str:
        digest = hashlib.sha256()
        with self.path.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def extract(self, dest: Path) -> None:
        dest.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(["tar", "-xf", str(self.path), "-C", str(dest)],
                           capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError as exc:
            raise ArtifactError(f"failed to extract artifact: {exc.stderr.strip()}") from exc


def _wait_for_rcm(timeout: float = RCM_WAIT_S) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for vid_file in glob.glob("/sys/bus/usb/devices/*/idVendor"):
            try:
                d = Path(vid_file).parent
                if d.joinpath("idVendor").read_text().strip() == RCM_VID and \
                   d.joinpath("idProduct").read_text().strip() in RCM_PIDS:
                    return
            except OSError:
                continue
        time.sleep(0.5)
    raise FlashError(f"no RCM device {RCM_VID}:[{'/'.join(RCM_PIDS)}] after {timeout:.0f}s")


def _run(cmd: list[str], cwd: Path, log: Path | None, timeout: float) -> int:
    logf = open(log, "wb") if log else None
    proc = None
    deadline = time.monotonic() + timeout
    try:
        proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if proc.stdout is None:
            raise FlashError("could not capture initrd-flash output")
        fd = proc.stdout.fileno()
        while True:
            if time.monotonic() > deadline:
                proc.kill()
                raise FlashError(f"initrd-flash exceeded {timeout:.0f}s; killed")
            ready, _, _ = select.select([fd], [], [], 5.0)
            if ready:
                chunk = os.read(fd, 1 << 16)
                if not chunk:
                    break
                sys.stdout.buffer.write(chunk)
                sys.stdout.buffer.flush()
                if logf:
                    logf.write(chunk)
            elif proc.poll() is not None:
                break
        return proc.wait(timeout=10)
    finally:
        if proc and proc.stdout:
            proc.stdout.close()
        if logf:
            logf.close()


def flash(board: Board, artifact: TegraflashArtifact, workdir: Path | None = None,
          log: Path | None = None, usb_instance: str | None = None,
          timeout: float = FLASH_TIMEOUT_S) -> str:
    artifact.validate()
    sha = artifact.sha256()

    owns_workdir = workdir is None
    workdir = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="tegraflash-"))
    try:
        artifact.extract(workdir)
        board.recov()
        _wait_for_rcm()
        cmd = ["sudo", "./initrd-flash"]
        if usb_instance:
            cmd += ["--usb-instance", usb_instance]
        rc = _run(cmd, workdir, log, timeout)
    finally:
        if owns_workdir:
            shutil.rmtree(workdir, ignore_errors=True)

    if rc != 0:
        raise FlashError(f"initrd-flash failed (exit {rc})")
    return sha
