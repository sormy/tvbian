/* SPDX-License-Identifier: GPL-2.0 */
/*
 * The pin numbers Amlogic's 4.9 GXLX pinctrl driver gives its periphs bank, as GXLX2 factory
 * trees use them. No public tree carries this table: Amlogic's gxl.h numbers GXL's, whose
 * GPIOH has 10 pins where GXLX's has 13, so every pin from BOOT on is 3 higher here. Read off
 * the H96 Max M20 (docs/h96max-m20/worklog-wifi.md): Android's power_on_pin 88 is GPIOX_6, the
 * Bluetooth enable 99 GPIOX_17, the Wi-Fi host wake 100 GPIOX_18, the LED 76 GPIODV_24, each
 * confirmed on the box against mainline's numbering. The AO bank numbers as GXL's.
 */

#ifndef _DT_BINDINGS_GPIO_GXLX_H
#define _DT_BINDINGS_GPIO_GXLX_H

/* AO bank */
#define GPIOAO_0	0
#define GPIOAO_1	1
#define GPIOAO_2	2
#define GPIOAO_3	3
#define GPIOAO_4	4
#define GPIOAO_5	5
#define GPIOAO_6	6
#define GPIOAO_7	7
#define GPIOAO_8	8
#define GPIOAO_9	9
#define GPIO_TEST_N	10

/* periphs bank */
#define GPIOZ_0	0
#define GPIOZ_1	1
#define GPIOZ_2	2
#define GPIOZ_3	3
#define GPIOZ_4	4
#define GPIOZ_5	5
#define GPIOZ_6	6
#define GPIOZ_7	7
#define GPIOZ_8	8
#define GPIOZ_9	9
#define GPIOZ_10	10
#define GPIOZ_11	11
#define GPIOZ_12	12
#define GPIOZ_13	13
#define GPIOZ_14	14
#define GPIOZ_15	15
#define GPIOH_0	16
#define GPIOH_1	17
#define GPIOH_2	18
#define GPIOH_3	19
#define GPIOH_4	20
#define GPIOH_5	21
#define GPIOH_6	22
#define GPIOH_7	23
#define GPIOH_8	24
#define GPIOH_9	25
#define GPIOH_10	26
#define GPIOH_11	27
#define GPIOH_12	28
#define BOOT_0	29
#define BOOT_1	30
#define BOOT_2	31
#define BOOT_3	32
#define BOOT_4	33
#define BOOT_5	34
#define BOOT_6	35
#define BOOT_7	36
#define BOOT_8	37
#define BOOT_9	38
#define BOOT_10	39
#define BOOT_11	40
#define BOOT_12	41
#define BOOT_13	42
#define BOOT_14	43
#define BOOT_15	44
#define CARD_0	45
#define CARD_1	46
#define CARD_2	47
#define CARD_3	48
#define CARD_4	49
#define CARD_5	50
#define CARD_6	51
#define GPIODV_0	52
#define GPIODV_1	53
#define GPIODV_2	54
#define GPIODV_3	55
#define GPIODV_4	56
#define GPIODV_5	57
#define GPIODV_6	58
#define GPIODV_7	59
#define GPIODV_8	60
#define GPIODV_9	61
#define GPIODV_10	62
#define GPIODV_11	63
#define GPIODV_12	64
#define GPIODV_13	65
#define GPIODV_14	66
#define GPIODV_15	67
#define GPIODV_16	68
#define GPIODV_17	69
#define GPIODV_18	70
#define GPIODV_19	71
#define GPIODV_20	72
#define GPIODV_21	73
#define GPIODV_22	74
#define GPIODV_23	75
#define GPIODV_24	76
#define GPIODV_25	77
#define GPIODV_26	78
#define GPIODV_27	79
#define GPIODV_28	80
#define GPIODV_29	81
#define GPIOX_0	82
#define GPIOX_1	83
#define GPIOX_2	84
#define GPIOX_3	85
#define GPIOX_4	86
#define GPIOX_5	87
#define GPIOX_6	88
#define GPIOX_7	89
#define GPIOX_8	90
#define GPIOX_9	91
#define GPIOX_10	92
#define GPIOX_11	93
#define GPIOX_12	94
#define GPIOX_13	95
#define GPIOX_14	96
#define GPIOX_15	97
#define GPIOX_16	98
#define GPIOX_17	99
#define GPIOX_18	100
#define GPIOCLK_0	101
#define GPIOCLK_1	102

#endif
