# Steering

## 2026-11-15

- Derive the mainline tree with the DT translation toolkit; sibling board wiring is not evidence.
- Aliases can precede their targets. Resolve them after visiting the tree.
- Match a macro unit address as the number preprocessing gives it.

## 2026-11-16 — Mainline boot procedure audit

| Kind    | Found by        | Finding                                                | Cost                                 | Fix requested                                             |
| ------- | --------------- | ------------------------------------------------------ | ------------------------------------ | --------------------------------------------------------- |
| agent   | Serial boot     | First swap lacked the required live second way in      | Blind failure; SD recovery           | Enforce the existing preflight before selection           |
| wrong   | Failed fallback | Userspace guard cannot cover failure before root mount | Power cycle repeated the bad default | State rollback boundary; keep vendor default              |
| missing | Agent audit     | Existing board with a new kernel stack has no run kind | Baseline treated as inherited        | Add kernel-stack migration route                          |
| escape  | Serial boot     | Duplicate SRAM passed proof and schemas                | Extra test boot                      | Check duplicate physical devices and provider transitions |
| wrong   | Agent audit     | Stock policy treated like board wiring                 | Decoder domain re-enabled            | Review policy against the target driver                   |
| agent   | Log review      | Multiple boots share one serial file                   | Harder attempt attribution           | Fresh timestamped log per boot                            |

- Damage: no observed eMMC or vendor-DTB damage; SD recovery checks were clean.
- Reversed: the initramfs hook and systemd guard did not provide early-boot fallback.
- Elapsed cost was not measured. The owner supplied power cycles, SD recovery and serial setup.
- Proposed guide changes are recorded; they have not been applied or committed.

## 2026-11-16 — Mainline SDIO

| Kind    | Found by       | Finding                                                | Cost                    | Fix requested                                     |
| ------- | -------------- | ------------------------------------------------------ | ----------------------- | ------------------------------------------------- |
| escape  | IOMUX readback | Translation drops a node with no base, and its pin mux | A day of SDIO bisection | Report dropped factory nodes that carry pinctrl   |
| missing | Agent audit    | `pinmux-pins` shows claims, not the hardware's mux     | Mux assumed equal       | Compare raw IOMUX registers before deeper probing |

## 2026-11-16 — next2 one-shot boot

| Kind  | Found by      | Finding                                                                      | Cost                      | Fix requested                                  |
| ----- | ------------- | ---------------------------------------------------------------------------- | ------------------------- | ---------------------------------------------- |
| wrong | Menu readback | Rollback hook used klibc `mount` with one argument, and `cp`                 | Two SD-recovery risks     | Test a rollback hook once before relying on it |
| agent | Self          | A wedged serial capture read as a boot that never happened                   | One wasted reboot         | Check the capture grows before waiting on it   |
| wrong | Owner         | glmark2 forced HDMI on with no EDID; a no-scanout score read as a faster GPU | A false next2 speed claim | Present a synthetic 1080p screen               |
