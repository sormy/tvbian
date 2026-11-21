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
| Kernel | `rockchip,rk3528a` last          | MPP's VP9; the kernel keeps `rk3528`         |
| Kernel | Maskrom reboot flag              | Software recovery                            |
| Kernel | Lima clocks / IRQ names          | Mainline GPU driver                          |
| Kernel | Esmart0 4K buffer                | 4K scanout                                   |
| Kernel | Remove multi-area                | Unusable Esmart sub-windows                  |
| Kernel | IR PSCI wake                     | ATF wake source                              |
| Kernel | Enable watchdog                  | Recover kernel hangs                         |
| Kernel | Disable `gpu-bus`                | No pvtm-supply; siblings disable it          |
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

## Mainline tree

`next2/` holds the tree for the mainline kernel, `kernel/rk35xx-next2.conf`, beside the vendor tree
until it replaces it. Its `board.patch` applies to the factory tree translated against mainline
7.3.4; `./build.sh board-dtb h96max-m2-plus/next2` builds it.

| Block                  | Change                                           |
| ---------------------- | ------------------------------------------------ |
| CPU OPPs               | 408–2016 MHz, every bin's voltages; PVTM picks   |
| `vdd_logic`, `vdd_gpu` | Scaled by the DDR's and the GPU's OPPs           |
| GPU OPPs               | Factory's 300–800 MHz; suspended at 300          |
| GPU cooling            | The factory's map, at the CPU's trip             |
| GPU power              | The factory model's coefficient, 724             |
| Media                  | Decoders, JPEG, encoder and their IOMMUs enabled |
| Composite              | TVE enabled                                      |
| HDMI DDC               | `i2c2`; the HDMI pin group keeps CEC only        |
| Audio                  | acodec and HDMI cards                            |
| IR                     | `gpio-ir-receiver` on `GPIO4_C6`, `pwm3` off     |
| Radio power            | PCM pins unpulled at enable; 200 ms power-off    |
| Radio reset            | Active low, as `mmc-pwrseq` drives it            |
| USB 3                  | `usb_host0_xhci` as host                         |
| Watchdog, UART0        | Enabled                                          |

Each CPU and GPU OPP runs at the chip's bin's voltage, every bin with its own column, a bin the
factory leaves to the default given that. Each PWM regulator, CPU, GPU and logic, takes its vendor
`active` pins as its default: without them the rail stays at its power-on voltage. The logic rail
follows the DMC's vote. The radio's PCM pins are SAI0's, which mainline lacks: without the pins the
card fails to initialise. The factory DDC pins sit under dw-hdmi, which refuses address 0x37: DDC/CI
needs the plain I2C controller.
