# X88 Pro 13 device trees

| Stage               | Change                                                 |
| ------------------- | ------------------------------------------------------ |
| Vendor 6.1 kernel   | March stock wiring, Lima bindings and watchdog enabled |
| Mainline 7.3 kernel | RK3528 translator, stock board compatible and watchdog |
| U-Boot              | Mainline bindings and UART0 console                    |
| MaskROM             | Factory DDR V1.04, Rockchip usbplug and SPL            |

The U-Boot control DTB is byte-identical to the H96 Max RK3528 factory blob. The UART0 choice is
backed by the X88 stock kernel's `fiq-debugger` node.

The stock front-panel driver passes `spi_cs`, `spi_clk` and `spi_data` as GPIO specifiers. The
RK3528 vendor vocabulary names their GPIO references during the round-trip and upstream view checks.

## Open

- The March vendor tree enables Seekwave and WLAN platform nodes. GPIO1_A6 is assigned to the WLAN
  node. Which stock driver powers each radio population is unverified.
- Mainline translation turns the WLAN node's GPIO1_A6 reset into the SDIO power sequence's
  `reset-gpios`, active low, and the Bluetooth node into a serdev `bluetooth` node on UART2 with its
  GPIO1_C1 reset. With no `compatible` until the radio is known, nothing binds it.
- The stock front-panel binding has no confirmed Linux driver for this board.

## Wireless in the six factory images

| Kernel DTB group                                | GPIO1_A6 assignment                              | SDIO maximum       | Vendor Bluetooth node |
| ----------------------------------------------- | ------------------------------------------------ | ------------------ | --------------------- |
| July first, September alternate                 | Seekwave enable high and MMC reset low           | 200 MHz, v2 tuning | Enabled               |
| July alternate with MMC reset                   | MMC reset low                                    | 200 MHz            | Disabled              |
| July alternate with WLAN reset, September first | WLAN reset high                                  | 150 MHz            | Enabled               |
| March Black                                     | WLAN reset high, Seekwave has no GPIO properties | 150 MHz            | Enabled               |

- All eight DTBs describe the same non-removable four-bit SDIO host at `0xffc10000` and put the 32
  kHz output on GPIO1_C3.
- All WLAN platform nodes leave `wifi_chip_type` empty and name GPIO1_A7 for host wake.
- All vendor Bluetooth nodes describe UART2 with RTS on GPIO1_B2, reset on GPIO1_C1 and host wake on
  GPIO1_C2. A described UART does not establish the fitted radio's Bluetooth transport.
- All six `dtbo` partitions contain the same reboot-mode overlay. Alternate radio trees are full
  DTBs inside the Android boot images.
- The named DTS files were decompiled with the RK3528 vendor vocabulary and each passed the
  round-trip check. They are in ignored `build/logs/x88-pro-13/stock-images/`.
