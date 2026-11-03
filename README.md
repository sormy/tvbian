# TVBian — Debian for TV boxes

[![Latest release](https://img.shields.io/github/v/release/sormy/tvbian?label=release&sort=date)](https://github.com/sormy/tvbian/releases/latest)
[![Released](https://img.shields.io/github/release-date/sormy/tvbian?label=released&display_date=published_at)](https://github.com/sormy/tvbian/releases/latest)
[![Weekly build](https://github.com/sormy/tvbian/actions/workflows/release.yml/badge.svg)](https://github.com/sormy/tvbian/actions/workflows/release.yml)

You bought a **$15–35 Android TV box**. It is silent, fanless, came with a remote, and runs an
Android its maker forgot the day after it shipped. The hardware deserved better. TVBian is the
better: plain Debian, our own kernels and drivers, a signed `apt` repository, and a robot that
builds fresh images every week whether anyone asked or not.

**Images:** the [latest release](https://github.com/sormy/tvbian/releases/latest). Checksums signed,
because we have trust issues too.

## Boxes

| Box                   | Board                      | Form     | Ports                               | SoC           | RAM · eMMC                 | Wi-Fi/BT   | Install            |
| --------------------- | -------------------------- | -------- | ----------------------------------- | ------------- | -------------------------- | ---------- | ------------------ |
| [R69-1][r69]          | `XR821_V1.1`               | box      | HDMI, USB 3+2, LAN 100M, SD, AV, IR | [RK3518][rk]  | 2 GB (1.5 usable) · 16 GB  | AIC8800D80 | SD card or OTG     |
| [H96 Max 3518][a]     | `3518_ZX_V01`              | box      | HDMI, USB 3+2, LAN 100M, SD, AV, IR | [RK3518][rk]  | 2 GB · 16 GB               | SWT6621S   | SD card or OTG     |
| [H96 Max 3518D][b]    | `3518_DG_ZX_V01`           | stick    | HDMI, USB-C + USB-A                 | [RK3518][rk]  | 2 GB · 16 GB               | SWT6621S   | OTG                |
| [H96 Max M20][m20]    | `905_DG_ZX01_V01`          | stick    | HDMI, USB-C + USB-A                 | [S905L3][aml] | 2 GB · 16 GB               | MT7668S    | OTG, then USB disk |
| [Tanix TX1 V2.0][tx1] | `QHZIW_H313_TX1_EMCP_V2.0` | mini box | HDMI, USB-A, AV, IR                 | [H313][aw]    | 1.5 GB (sold as 2) · 16 GB | ATBM6031-X | OTG                |

[r69]: docs/r69-1/board.md
[a]: docs/h96max-3518/board.md
[b]: docs/h96max-3518d/board.md
[m20]: docs/h96max-m20/board.md
[tx1]: docs/tanix-tx1-v2/board.md
[rk]: README_ROCKCHIP.md
[aml]: README_AMLOGIC.md
[aw]: README_ALLWINNER.md

Click the SoC for its family's guide: what works, installing, updating, and getting Android back
when regret sets in. OTG is a USB-A male-to-male cable into the box's OTG port, the one port that
turns a TV box into a patient on the operating table. **Host: macOS or Linux.** Windows users: we
believe in you, from a distance.

## Your box is not here

Box names lie. "H96 Max" is not a box, it is a lifestyle: hundreds of boards, several chips, one
case. Ours had "H313" on the label and a Rockchip inside. A box is the board, and a board is its
silkscreen, so open it.

Adding one is a pull request, and an agent does most of the work. You bring a serial adapter, an OTG
cable and the patience to press a toothpick into a hole on command:
[docs/bring-up/README.md](docs/bring-up/README.md).

## Contributing

All welcome, by pull request:

- a new family, or a new board of one we have;
- a fix to a kernel, a driver, or a board's device tree wiring;
- a box measured: what works, what does not, with the numbers.

One fix a patch, written as if Linus himself will review it: ask your AI to write it that way. A
separate place in heaven is kept for whoever has the patience to walk one through upstream review
until it merges.

## License

Scripts MIT. Device trees are decompiled from each box's factory DTB; vendor blobs keep their own
licenses, and their own secrets.
