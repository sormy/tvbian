# TVBian — Debian for TV boxes

[![Latest release](https://img.shields.io/github/v/release/sormy/tvbian?label=release&sort=date)](https://github.com/sormy/tvbian/releases/latest)
[![Released](https://img.shields.io/github/release-date/sormy/tvbian?label=released&display_date=published_at)](https://github.com/sormy/tvbian/releases/latest)
[![Weekly build](https://github.com/sormy/tvbian/actions/workflows/release.yml/badge.svg)](https://github.com/sormy/tvbian/actions/workflows/release.yml)

You bought a **cheap Android TV box**. It is silent, fanless, came with a remote, and runs an
Android its maker forgot the day after it shipped. The hardware deserves better than a landfill next
year. TVBian is the better: plain Debian, our own kernels and drivers, a signed `apt` repository,
and a robot that builds fresh images every week whether anyone asked or not.

**Images:** the [latest release](https://github.com/sormy/tvbian/releases/latest). Checksums signed,
because we have trust issues too.

## Boards

| Board                       | PCB                        | Form     | Hardware\*                                                                                                                                                | Install         |
| --------------------------- | -------------------------- | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------- |
| [R69-1][r69]                | `XR821_V1.1`               | box      | SoC RK3518 · 2 GB RAM LPDDR3 (1.5 GB usable) · 16 GB eMMC HS200 · SD HS · USB-A 3.0 (OTG) + USB-A 2.0 · LAN 100M · AIC8800D80 Wi-Fi + BT · HDMI · AV · IR | [SD or OTG][rk] |
| ↳ T8S                       | `R69MAX V1.1`              | box      | SoC RK3518 · 2 GB RAM LPDDR3 (1.5 GB usable) · 8 GB eMMC HS200 · SD HS · USB-A 3.0 (OTG) + USB-A 2.0 · LAN 100M · AIC8800D80 Wi-Fi + BT · HDMI · AV · IR  | [SD or OTG][rk] |
| [H96 Max 3518][a]           | `3518_ZX_V01`              | box      | SoC RK3518 · 2 GB RAM LPDDR3 · 16 GB eMMC HS200 · SD UHS-I · USB-A 3.0 (OTG) + USB-A 2.0 · LAN 100M · SWT6621S Wi-Fi + BT · HDMI · AV · IR                | [SD or OTG][rk] |
| ↳ Leffot H313               | `3518_ZX_V01`              | box      | SoC RK3518 · 2 GB RAM LPDDR3 · 16 GB eMMC HS200 · SD UHS-I · USB-A 3.0 (OTG) + USB-A 2.0 · LAN 100M · SWT6621S Wi-Fi + BT · HDMI · AV · IR                | [SD or OTG][rk] |
| [H96 Max 3518D][b]          | `3518_DG_ZX_V01`           | stick    | SoC RK3518 · 2 GB RAM LPDDR3 · 16 GB eMMC HS · **no SD** · USB-C 2.0 (OTG) + USB-A 2.0 · **no LAN** · SWT6621S Wi-Fi + BT · HDMI                          | [OTG][rk]       |
| [H96 Max M2 Plus][m2p]      | `M2_P_ZX_20250328`         | box      | SoC RK3528 · 4 GB RAM DDR3 · 32 GB eMMC HS200 · **no SD** · USB-A 3.0 (OTG) · LAN 100M · SWT6621S Wi-Fi + BT · HDMI · AV · IR                             | [OTG][rk]       |
| [H96 Max RK3528][rk3528] ❓ | `RK3528_DDR3_8X4_V12`      | box      | SoC RK3528 · 4 GB RAM DDR3 · 64 GB eMMC HS400 · SD UHS-I · USB-A 3.0 (OTG) + USB-A 2.0 · LAN 100M · AIC8800D80 Wi-Fi + BT · HDMI · AV · SPDIF · IR · LCD  | [SD or OTG][rk] |
| [H96 Max M20][m20]          | `905_DG_ZX01_V01`          | stick    | SoC S905L3 · 2 GB RAM LPDDR3 · 16 GB eMMC HS · **no SD** · USB-C 2.0 (OTG) + USB-A 2.0 · **no LAN** · MT7668S Wi-Fi + BT · HDMI                           | [OTG][aml]      |
| [Tanix TX1 V2.0][tx1]       | `QHZIW_H313_TX1_EMCP_V2.0` | mini box | SoC H313 · 1.5 GB RAM LPDDR3 (sold as 2 GB) · 16 GB eMMC DDR52 · **no SD** · USB-A 2.0 (OTG) · **no LAN** · ATBM6031-X Wi-Fi + BLE · HDMI · AV · IR       | [OTG][aw]       |
| [H96 Max H313][h313]        | `BA979_627_V1.0`           | box      | SoC H313 · 2 GB RAM LPDDR3 · 16 GB eMMC HS200 · SD HS · USB-A 2.0 (OTG) + USB-A 2.0 · LAN 100M · AIC8800D40L Wi-Fi + BLE · HDMI · AV · IR                 | [SD or OTG][aw] |

\*What our units carry; the same model may ship with other RAM or eMMC. Any size works.

❓ Not tested here: built from the box's stock firmware, waiting for an owner's report.

[r69]: docs/r69-1/board.md
[a]: docs/h96max-3518/board.md
[b]: docs/h96max-3518d/board.md
[m2p]: docs/h96max-m2-plus/board.md
[rk3528]: docs/h96max-rk3528/board.md
[m20]: docs/h96max-m20/board.md
[tx1]: docs/tanix-tx1-v2/board.md
[h313]: docs/h96max-h313/board.md
[rk]: README_ROCKCHIP.md
[aml]: README_AMLOGIC.md
[aw]: README_ALLWINNER.md

Click the install method for its family's guide: what works, installing, updating, and getting
Android back when regret sets in. OTG is a USB-A male-to-male cable into the box's OTG port, the one
port that turns a TV box into a patient on the operating table. **Host: macOS or Linux.** Windows
users: we believe in you, from a distance.

## Will it brick my box?

We try hard not to: the installer leaves alone what recovery needs. Still, **back up first**; each
family's guide says how.

Worst case, the box is not dead, just expensive: short the eMMC's
[CLK trace](docs/rockchip-maskrom.md#4-shorting-emmc-clk-or-d0-to-gnd) at power-on and the boot ROM
listens again, if you can find the trace. [One R69](https://github.com/sormy/tvbian/issues/6) still
hides it, after Armbian's installer gave it another board's loader. TVBian's installer writes only
the loader for the board you picked, and `apt` refuses a board package for another chip family. Pick
the right one anyway.

## Your box is not here

Box names lie. "H96 Max" is not a box, it is a lifestyle: hundreds of boards, several chips, one
case. Ours had "H313" on the label and a Rockchip inside. A box is the board, and a board is its
chips and layout, whatever its silkscreen says, so open it.

Adding one is a pull request, and an agent does most of the work. You bring a serial adapter, an OTG
cable and the patience to press a toothpick into a hole on command:
[docs/bring-up/README.md](docs/bring-up/README.md).

> **Which model, as of 2026-11-09.** Not an advert, what we saw. A new family, a new chip, or a
> vendor tree translated to mainline: Anthropic's Opus, even at low effort. OpenAI's Codex (Sol)
> copied other boards' translated trees wholesale instead of translating this one's. Grok's results
> could not be trusted.

## Contributing

All welcome, by pull request:

- a new family, or a new board of one we have;
- a fix to a kernel, a driver, or a board's device tree wiring;
- a box measured: what works, what does not, with the numbers.

One fix a patch, written as if Linus himself will review it: ask your AI to write it that way. A
separate place in heaven is kept for whoever has the patience to walk one through upstream review
until it merges.

## License

Scripts MIT, [`LICENSE`](LICENSE). Device trees are decompiled from each box's factory DTB; vendor
blobs keep their own licenses, and their own secrets.
