# H96 Max M2 Plus device trees

## Factory

| Tree   | Source                                            |
| ------ | ------------------------------------------------- |
| Kernel | `boot`, byte 12066816; identical copy at 18417664 |
| U-Boot | `uboot`, byte 1458688; identical copy at 3555840  |

Kernel binary: 6.1.118, ARMv7. U-Boot binary: 2017.09-250331-dirty.

## Applied changes

| Tree   | Change                           | Reason                                       |
| ------ | -------------------------------- | -------------------------------------------- |
| Kernel | Model                            | Identify the box                             |
| Kernel | First compatible                 | Board NV selection                           |
| Kernel | Maskrom reboot flag              | Software recovery                            |
| Kernel | Lima clocks / IRQ names          | Mainline GPU driver                          |
| Kernel | Esmart0 4K buffer                | 4K scanout                                   |
| Kernel | Remove multi-area                | Unusable Esmart sub-windows                  |
| Kernel | IR PSCI wake                     | ATF wake source                              |
| Kernel | Enable watchdog                  | Recover kernel hangs                         |
| Kernel | LED names                        | Shared hooks                                 |
| Kernel | SDIO `power-off-delay-us` 200 ms | Wi-Fi chip resets between init retries       |
| Kernel | Recovery button `KEY_VENDOR`     | Mainline's code; factory `KEY_VOLUMEUP`      |
| Kernel | IR `ir_key6` table               | The bundled remote onto the canonical keymap |
| Kernel | HDMI DDC on `i2c-gpio`           | DDC/CI; dw-hdmi's I2C refuses it             |
| U-Boot | Model                            | Identify PCB in banner                       |
| U-Boot | Mainline clock/reset headers     | 2026.10 bindings                             |
| U-Boot | `bootph-*` properties            | Mainline pre-relocation probing              |
| U-Boot | UART0, stdout path               | Debug header console                         |
| U-Boot | SARADC reference                 | Mainline driver needs explicit voltage       |

U-Boot's factory eMMC driver type remains `4`; kernel eMMC remains HS200 at 100 MHz.

Installed tree matches the built artifact. eMMC boot, radio NV selection and watchdog arming
verified. Display, IR wake and LED behaviour remain untested.

## Suspend

| Candidate       | Result                                                      |
| --------------- | ----------------------------------------------------------- |
| `deep`, factory | Woken by the remote over IR, 3 of 3; past the watchdog      |
| `s2idle`        | Nothing wakes it: IR belongs to ATF (`remote_support_psci`) |
