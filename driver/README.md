# `driver/` — patched `hp-wmi.ko` for OMEN 16-wf0

The stock `hp-wmi` module in Ubuntu's HWE 6.8 kernel does **not** expose `pwm1` / `pwm1_enable` on board ID **8BAB** (OMEN 16-wf0xxx). This directory rebuilds the upstream [omen-fan-control](https://github.com/dmidlb/omen-fan-control) variant with the compatibility patches needed to compile under kernel 6.8 (see `PATCH.md`).

After loading, the patched module exposes:

```
/sys/class/hwmon/hwmonN/name           # "hp"
/sys/class/hwmon/hwmonN/pwm1           # PWM 0..255
/sys/class/hwmon/hwmonN/pwm1_enable    # 1=manual, 2=auto
/sys/class/hwmon/hwmonN/fan1_input     # RPM
/sys/class/hwmon/hwmonN/fan2_input     # RPM
```

## Requirements

- Linux running kernel **6.8.x** with matching headers
  (Ubuntu 22.04: `linux-hwe-6.8-headers-*`)
- `build-essential` and `dkms` (or equivalent packages on your distro)
- **Secure Boot disabled in BIOS** — the module is unsigned

## Build (transient, no install)

```bash
make           # produces hp-wmi.ko in this directory
sudo rmmod hp_wmi
sudo insmod ./hp-wmi.ko
ls /sys/class/hwmon/*/pwm1 2>/dev/null   # confirm the node exists
```

This forgets itself on reboot.

## Install via DKMS (persistent, rebuilds on kernel upgrade)

Use the wrapper script from the repo root:

```bash
sudo ../scripts/install_driver.sh
```

It backs up the stock `hp-wmi.ko` to `/var/backups/`, copies `driver/` into `/usr/src/hp-wmi-omen-1.0/`, runs `dkms add/build/install`, and reloads the module.

To revert:

```bash
sudo ../scripts/uninstall_driver.sh
```

## Risk

- Each kernel upgrade triggers an automatic DKMS rebuild. If a future kernel changes the WMI notify / platform_profile / platform_driver.remove APIs again (see `PATCH.md`), the build fails — fix the patch or run `uninstall_driver.sh` to fall back to stock.
- Tested only on board 8BAB. The upstream project lists 8BAB as supported but we have no manufacturer documentation; pushing `pwm1=0` was not tested (helper rejects it).
