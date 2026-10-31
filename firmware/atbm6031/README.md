# AltoBeam ATBM6031 firmware

`package.list` here builds `tvb-firmware-atbm6031`, for `atbm6031`, at the name its build asks for.

| File                  | Origin                                                  | Version                   |
| --------------------- | ------------------------------------------------------- | ------------------------- |
| `atbm6031_fw.bin`     | stock `/vendor/etc/firmware/ATBM_lite_fw_sdio.bin`      | 19040, 2023-12-06, no BLE |
| `atbm6031_ble_fw.bin` | stock `/vendor/etc/firmware/ATBM_lite_blecomb_sdio.bin` | 19897, 2024-03-25, BLE    |

The driver loads `atbm6031_fw.bin`, or `atbm6031_ble_fw.bin` with `wifi_bt_comb=1`, as stock's
`atbm_HwGetChipFw` picks between the two. The first offers 29 input buffers, the BLE image 6.
`ATBM_mercu_blecomb_sdio.bin` is the 6132's, and brings no `wlan0`.
