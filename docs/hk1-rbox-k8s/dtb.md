# HK1 RBOX K8S device trees

| Tree   | Factory source                           | Patch               |
| ------ | ---------------------------------------- | ------------------- |
| vendor | Android boot, RSCE entry `rk-kernel.dtb` | `board.patch`       |
| next2  | the vendor tree, translated by dtcx      | `next2/board.patch` |
| U-Boot | Factory U-Boot FIT, `fdt` payload        | `uboot.patch`       |

## Changes

`both`: the vendor tree and next2; `all`: those and U-Boot's. B2 is GPIO3 B2, the module's enable.

| Tree   | Change                                     | Why                                       |
| ------ | ------------------------------------------ | ----------------------------------------- |
| all    | `model`: the box's                         | the factory names the EVB                 |
| vendor | root: `rockchip,rk3528a` last              | MPP's only RK3528 with VP9                |
| vendor | `chosen`: `bootargs` dropped               | the console's in `BOARD_CMDLINE`          |
| vendor | `gpu`: lima's interrupt names              | mainline's lima                           |
| vendor | `gpu`: `bus` and `core` on `ACLK_GPU_MALI` | SCMI's 800 MHz is unthrottled here        |
| both   | `watchdog`: `okay`                         | recovery from a hang                      |
| vendor | `adc-keys`: `recovery`, `KEY_VENDOR`       | the AV-jack recovery button               |
| vendor | `vop`: `esmart_lb_mode` `02`               | a 4K line buffer for HDMI                 |
| vendor | `vop`: `support-multi-area` dropped        | sub-windows never reach HDMI              |
| both   | `sdio-pwrseq`: B2 a reset, 2 s off         | B2 low 2 s revives a stalled card         |
| vendor | `wireless-wlan`: B2's pins dropped         | B2 is the power sequence's                |
| vendor | UART2: `dmas`, `dma-names` dropped         | interrupt mode, as Rockchip's             |
| both   | UART2: `aicsemi,aic8800-bt`, 1.5 Mbaud     | SDIO `c8a1:0082`: an AIC8800D80           |
| vendor | IR: `remote_support_psci` `1`              | the remote wakes the box from off         |
| vendor | IR `0xfe01`: OK, home, mouse canonical     | the bundled remote                        |
| next2  | `ir-receiver`: `rc-hk1-rbox-k8s`           | the bundled remote's keymap               |
| both   | `i2c-display`: the FD650B-S, GPIO4 A2, A3  | the front panel, through TM16xx           |
| vendor | `fd628-dev`: `disabled`                    | `i2c-display` drives its pins             |
| vendor | `gpu-bus`: `disabled`                      | sets `vdd_logic` for a clock the GPU left |
| next2  | the PHY's LED pins dropped                 | no jack LEDs; UART3 owns the pins         |
| U-Boot | boot phases, clock and reset IDs           | mainline U-Boot's bindings                |
| U-Boot | `serial@ff9f0000`: added                   | the factory kernel's debug console        |
| U-Boot | `saradc`: `vdd-microvolts` 1.8 V           | mainline's driver needs a reference       |

The factory's other boot arguments are Android's: `driver_async_probe` for boot time, and
`drm_kms_helper.fbdev_emulation=0`, which would take away the framebuffer console.

The factory's WLAN node names `rtl8822cs`; the module is an AIC8800D80. The panel takes hour tens to
minute units at commands `0x68`, `0x6a`, `0x6c` and `0x6e`; bit 7 of the hour units is the colon.
The other IR key tables stay as the factory wrote them, 24 codes unnamed.

## Not taken from the siblings

| Graft                         | Why not                                      |
| ----------------------------- | -------------------------------------------- |
| `reboot-mode` `mode-maskrom`  | the factory SPL's handling of it is untested |
| HDMI DDC as an `i2c-gpio` bus | HDMI fails at hot-plug detect first          |
| LED labels `power`, `standby` | the box has no LEDs                          |
