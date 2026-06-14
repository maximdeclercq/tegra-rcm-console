# tegra-rcm-console

Drive a Jetson Orin Nano Devkit's J14 button header and serial console over USB:
recovery, power on/off/cycle, a console bridge, and `initrd-flash`, as one
scriptable command for unattended Yocto/oeqa bring-up. An MCU (e.g. RP2040) runs
the firmware; a host CLI drives it. The Devkit carrier also takes Orin
NX modules, so the same harness works for both.
