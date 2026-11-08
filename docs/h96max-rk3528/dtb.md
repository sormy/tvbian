# H96 Max RK3528 device trees

## Factory

| Tree   | Source                                                            |
| ------ | ----------------------------------------------------------------- |
| Kernel | `boot.img`'s `RSCE` entry `rk-kernel.dtb`; three identical copies |
| U-Boot | `uboot.img`, a FIT: its `fdt` image at `0x1acc00`, 6,997 B        |

Both from the stock image `H96 Max RK3528 20230630.1201`. Kernel base `rk3528-evb2-ddr3-v10`; U-Boot
2017.09. The tree equals the one an owner carved from this board's boot partition.

## Applied changes

| Tree   | Change                       | Reason                                   |
| ------ | ---------------------------- | ---------------------------------------- |
| Kernel | Model, first compatible      | Identify the box                         |
| Kernel | Maskrom reboot flag          | Software recovery                        |
| Kernel | Lima clocks / IRQ names      | Mainline GPU driver                      |
| Kernel | Esmart0 4K buffer            | 4K scanout                               |
| Kernel | Remove multi-area            | Unusable Esmart sub-windows              |
| Kernel | HDMI DDC on `i2c-gpio`       | DDC/CI; dw-hdmi's I2C refuses it         |
| Kernel | IR PSCI wake                 | ATF wake source                          |
| Kernel | Enable watchdog              | Recover kernel hangs                     |
| Kernel | Recovery button `KEY_VENDOR` | Mainline's code; factory `KEY_VOLUMEUP`  |
| Kernel | `uart2`: no `dmas`           | Interrupt mode, as the R69-1             |
| Kernel | `uart2`: AIC8800 BT serdev   | Stock runs Bluetooth on `/dev/ttyS2`     |
| Kernel | `/chosen` dropped            | U-Boot rewrites `bootargs`               |
| U-Boot | Model                        | Identify the PCB in the banner           |
| U-Boot | Mainline clock/reset headers | 2026.10 bindings                         |
| U-Boot | `bootph-*` properties        | Mainline pre-relocation probing          |
| U-Boot | UART0, stdout path           | Stock's console: `fiq-debugger` serial 0 |
| U-Boot | SARADC reference 1.8 V       | Stock's `vref-supply`, `vdd_1v8_s3`      |

The U-Boot changes follow the M2 Plus's, each board value checked against this stock tree; the eMMC
driver type stays the factory's `1`. Nothing here has booted.

## Left as the factory has them

| Node            | Why                                                             |
| --------------- | --------------------------------------------------------------- |
| `pwr-wifi` LED  | The only `gpio-leds` entry; no LED seen on the board            |
| `ir_key` tables | Which of six remotes is bundled is unknown                      |
| `fd655_dev`     | The front LCD; no driver for it here                            |
| SDIO `pwrseq`   | The M2 Plus's `power-off-delay-us` is its radio's, not this one |
