# Yocto / oeqa testing

`testimage` validates an already-running image over SSH; it does not flash. So
flashing is a separate bring-up step. The pipeline:

    tegra-button flash <image>.tegraflash-tar.zst   # recover + initrd-flash
    bitbake <image> -c testimage                          # power-cycle + validate

`flash` brings the board up on the new image (recovery is internal to it), then
`testimage` power-cycles and validates over SSH. To do it in one `bitbake`, have
the controller below shell out to `tegra-button flash` in `start()` (artifact
under `DEPLOY_DIR_IMAGE`) before waiting for SSH. OE4T ships no Jetson controller,
so you supply the small oeqa target plus the `local.conf` below.

## Network

Testbench and DUT share a direct ethernet cable (no DHCP), so both ends are
static. Configure the image to bring up its address and match it in `local.conf`:
testbench `192.168.10.1`, DUT `192.168.10.2`. Root SSH must be key-based.

## local.conf

    IMAGE_CLASSES += "testimage"
    TEST_TARGET = "JetsonOrinTarget"
    TEST_SERVER_IP = "192.168.10.1"
    TEST_TARGET_IP = "192.168.10.2"
    TEST_POWERCONTROL_CMD = "tegra-button power"
    TEST_SERIALCONTROL_CMD = "tegra-button serial"
    TEST_SUITES = "ping ssh df date parselogs"

`testimage` appends `cycle`/`off`/`on` to `TEST_POWERCONTROL_CMD`, which matches
the `power` subcommand; `serial` is the transparent pipe `pexpect.spawn` needs for
`TEST_SERIALCONTROL_CMD`. For several DUTs, put `--id ID` before the subcommand so
the appended argument still lands last.

## The oeqa target

Drop this into a layer on `BBPATH` at `lib/oeqa/controllers/jetsonorintarget.py`.
The board is already flashed, so it power-cycles, waits for SSH, and parks the
board afterward. A starting point; verify on your bench.

    import socket
    import subprocess
    import time

    from oeqa.core.target.ssh import OESSHTarget


    class JetsonOrinTarget(OESSHTarget):
        def __init__(self, logger, ip, server_ip, timeout=300, **kwargs):
            self.powercontrol_cmd = kwargs.get("powercontrol_cmd")
            super().__init__(logger, ip, server_ip, timeout=timeout, **kwargs)
            self.boot_timeout = timeout

        def _power(self, action):
            if self.powercontrol_cmd:
                subprocess.check_call(self.powercontrol_cmd.split() + [action])

        def start(self, **kwargs):
            self._power("cycle")
            deadline = time.monotonic() + self.boot_timeout
            while time.monotonic() < deadline:
                with socket.socket() as s:
                    s.settimeout(5)
                    if s.connect_ex((self.ip, 22)) == 0:
                        return
                time.sleep(2)
            raise RuntimeError(f"DUT did not reach SSH within {self.boot_timeout}s")

        def stop(self, **kwargs):
            self._power("off")

## Running

    bitbake <image> -c testimage

With no power control wired, set `TEST_POWERCONTROL_CMD` to OE's
`${COREBASE}/scripts/contrib/dialog-power-control` for a manual operator prompt.
