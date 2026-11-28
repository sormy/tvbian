# Rockchip on mainline: what is left

What the RK3528 and RK3518 still need on mainline before it replaces the vendor kernel. Each item is
small unless marked (medium).

## Video

- [ ] VP9 profile 2 at 2160p60 measured frame to frame (65 fps linear, 83 AFBC today).
- [ ] (medium) 4K HEVC as fast as the vendor's MPP; we are 1% behind, about 110 µs idle between
      frames. The VDPU381's link mode queues jobs in hardware and would close it.
- [ ] The JPEG decoder compared with the vendor's MPP; ffmpeg9 has no MPP JPEG decoder.
- [ ] H.264 4:2:2 in MBAFF decoded correctly; its chroma is wrong today, so it is refused.
- [ ] H.264 4:2:2 field pictures (PAFF) tested; no encoder at hand writes them.
- [ ] The encoder taking grey, ARGB1555 and ARGB4444 sources; grey and RGB555 hung the SoC, so all
      three are refused.
- [ ] JPEG decode by region, as the datasheet lists; its register is unknown.
- [ ] What the GRF memory bits for VDPU2, RGA and VDPP that Android sets do; they stay unset.
- [ ] (medium) HDR Vivid, as the datasheet lists: the HDR engine's curves set from each frame's
      metadata. What is known: the HDR Vivid appendix.
- [ ] No MPP once every Rockchip board runs mainline: video through `rkvdec` and Hantro by V4L2, and
      what exists only for MPP retired: `tvb-va-driver`'s MPP backend and its `libmpp`,
      `patches/mpp`, `patches/wpewebkit` `0001`, and our FFmpeg's `*_rkmpp` decoders.

## Display

- [ ] No VP1 underflow when composite starts. Today a plain start underflows about 1 in 12 times,
      and every time with PAL and NV12 writeback. The vendor resets p2i after one.
- [ ] Esmart regions seen on a screen; so far only by writeback.
- [ ] Composite cable detection through the VDAC, which the datasheet lists.
- [ ] The H96 Max RK3528 booting with the VOP IOMMU on, which next2's `cma=16M` assumes; the box is
      away.

## Power and thermal

- [ ] DDR rate changes that never hang the SoC; today any change can, on the vendor kernel too, so
      the DDR rate stays fixed and has no cooling device.
- [ ] (medium) PVTM's floor below 10 °C (900 mV). It changes nothing where the GPU shares `vdd_cpu`;
      on a board where the GPU has its own rail, the GPU runs at 875 mV.
- [ ] PVTM matching the vendor's bin; its counts read 2.5–4% low, one bin lower, and the CPU rail
      sits about 4.4 mV under the vendor's.
- [ ] PVTM's per-chip floor (`mbist-vmin`) and OTP's voltage offset (`opp-info`) applied; both are
      no-ops on every chip read here.
- [ ] Idle temperature compared with the vendor beside an idle reference box; shelf drift hides the
      difference today.

## Wake and input

- [ ] The TV's power key over CEC waking the box, as the vendor's `hdmi_cec_key` does.
- [ ] A Bluetooth remote's key waking the box, as the vendor's `bt-powerkey` does.

## Storage, network and audio

- [ ] (medium) SDR104 working with the M2 Plus's SD card; the vendor uses `rockchip,use-v2-tuning`.
- [ ] The FE PHY's long-cable tuning, as the vendor sets it from link and CRC counts.
- [ ] The HK1's Wi-Fi download at 2.4 GHz on every run; two of four runs got nothing.
- [ ] HDMI audio's SAI clocks kept running between streams, as the vendor's are; whether a stream's
      start is clipped is untested.

## Crypto

- [ ] (medium) AES CCM and CMAC on the engine (CCM runs one job, then times out), and RSA faster
      than the CPU's (4% behind today). What was tried: the AES CCM appendix.

## Trees and patches

- [ ] The RK3528 translation's dropped properties shown safe on a box: VOP2's `rockchip,grf`, the
      xHCI quirks, eMMC `use-v2-tuning` and enhanced strobe, the boot logo, `system-monitor`'s
      floors.
- [ ] Every mainline patch sendable upstream as it stands: `patches/linux-rockchip-mainline`, the
      RK3528 dtsi changes among them, one change each, checkpatch `--strict` clean, each property in
      a binding. Not there yet: PVTM binning, vendor properties, and a cpufreq module that measures
      the GPU. Board trees stay downstream.

## Testing

- [ ] kexec from next2 into next2 working; the second kernel dies silently every time. Try next2
      into 6.1 next.
- [ ] A kernel that hangs before its initramfs booted only once, through a one-shot label in U-Boot;
      today `boot_once.py` boots it again after each reset.

## On hold

Not worked on until the owner says, like AVS: HDCP (no keys on any box here), VC-1 (no vendor code
drives it) and H.264 MVC (its second view is only for 3D).

## 👤 By hand

- [ ] Composite on a TV after VP1 underflows, on next2: run `display.py composite` with the TV on
      AV, then show a picture with fine horizontal lines. Lines in the wrong order flicker or comb.
- [ ] The 3518 on next2 wakes on its remote: `systemctl suspend`, then a key; `systemctl poweroff`,
      then the power key starts it.
- [ ] Composite cable detection: a box with an AV jack on next2, an AV cable to a TV plugged in and
      out while `VDAC_CABLE_CTRL` (`0x288`) is read: which bit follows the cable.
- [ ] Composite on a TV with next2's split `02`: the picture through Esmart2, in PAL and NTSC.
- [ ] The gamma LUT on next2 seen on a TV: `display.py`'s inversion table shows a negative. The
      RK3528's writeback is taken before gamma, so only a screen shows it.
- [ ] Esmart regions on a screen: on the M2 Plus's panel, next2's `display.py` regions show four
      strips, or black as on the vendor kernel.
- [ ] The analog codec on next2 heard on the M2 Plus's AV jack at 12, 96 and 192 kHz: a clean tone,
      192 being past the datasheet's 96.
- [ ] An Ethernet cable on the M2 Plus, on next2: Wake-on-LAN from deep sleep by a magic packet, and
      `box.py` throughput with the checksum offloads and TSO on.
- [ ] The IR remote on next2, on the M2 Plus: `ir-keytable -t` while every button is pressed, each
      key the canonical one, as on the vendor kernel.
- [ ] The M2 Plus's SD card back in its slot, for next2's SDR104 tuning: the card that failed there,
      its root on the eMMC since.
- [ ] Bluetooth on next2 with a real device: audio streamed and a keyboard on the HK1 and the R69-1,
      now that UART2 has RTS; no H4 errors in the log.

## Appendix: HDR Vivid

The HDR engine in the RK3528's VOP2 gets all its parameters from userspace, through the CRTC's
`HDR_EXT_DATA` blob (`struct hdrvivid_regs` in the vendor kernel's `rockchip_drm_vop.h`). On the
stock Android image the composer fills that blob; nothing on TVBian does.

next2 already does SDR to PQ, whose constants are known. The HDR half needs the tables: tone mapping
an HDR layer to SDR, and passing it through beneath SDR planes.

| File                      | What it is                                                         |
| ------------------------- | ------------------------------------------------------------------ |
| `libhdr_params_parser.so` | version "RKHDRPARSER_0.0.1.0.202304241501", `rkvop_pq_hdrvivid_sw` |
| `hwcomposer.rk30board.so` | the stock composer, a `drm_hwcomposer` fork, which calls it        |

Both come from the 3518D's stock `vendor` partition, `lib/` and `lib/hw/` (32-bit). They are kept
out of the repo, in `build/vendor-blobs/rk3528-hdr/`.

### Known

- **No stored tables.** No other binary on the stock image holds HDR tables: every partition in
  `super` was listed, and `vendor_dlkm` holds only Wi-Fi drivers and `rkvtunnel`. The library
  computes every curve at run time: its `.rodata` is 8 KiB of constants and strings. Its `.data` has
  step tables (runs of 2 to 7, from `0x23088`), likely how the engine splits each curve into
  segments.
- **Entry points.** `GenerateHardWareParams_Mode0` to `Mode7` build one register set each, numbered
  as the vendor kernel's modes: 6 is `HDR_BYPASS`, 7 is `HDR102SDR`. `hdr_parser()` and
  `hdr_format_parser()` fill `rk_hdr_reg_t` through 126 field setters
  (`set_hdrvivid_ctrl_path_mode`, `set_hdr_csc_coe*`, ...); `run()` builds the curves.
- **Loadable on Linux.** The library needs nothing from Android but `__system_property_get`, and its
  relocations are plain `RELA`, so glibc can load it with a one-function shim.
- **A possible refusal.** The composer logs "RK3528 TV unsupport HDR2SDR" next to its `gIsRK3528`
  check, so the stock TV image may not do HDR to SDR in the VOP at all. That branch is not yet read.
- **Its input** is MPP's per-frame metadata (`inc/rk_hdr_meta_com.h`,
  `mpp/base/mpp_dec_hdr_meta.c`). Each message is a 32-byte `RkMetaHdrHeader` and a payload. The
  header holds magic 318 (`0x13e`), the size including the header, the message count and index, a
  version, `hdr_format` (5 for HDR Vivid), the payload type (0 static, 1 dynamic) and the codec (1
  for HEVC). The first payload is `HdrStaticMeta`, 19 words: colour space, primaries, transfer,
  mastering display, MaxCLL, MaxFALL. The dynamic metadata follows as the SEI carried it.
- **Its parameters.** `hdr_parser()` reads the metadata through the pointer at offset 8, and checks
  its magic and that its size is over 31. The byte at offset 0 enables it; the byte at `0x4d` is the
  log level.

### Plan

next2 exposes HDR Vivid as DRM colorops on the HDR plane: a curve, a matrix and custom 1D LUTs. The
curves are computed in userspace from FFmpeg's `AV_FRAME_DATA_DYNAMIC_HDR_VIVID`. The library's
register images show what each engine stage does, so each colorop can be named after its stage.

### Next

1. Work out the layouts of the structs the entry points take, from the disassembly.
2. Run the library on a box with the shim, for Mode 6's and Mode 7's register images.
3. Feed those images through `HDR_EXT_DATA` on the vendor kernel, checked by writeback, before next2
   takes them.

## Appendix: AES CCM on the engine

The engine's mode 7 is CCM. Rockchip's kernel defines `CRYPTO_BC_CCM` but never uses it.
`patches/linux-rockchip-mainline/crypto-rockchip-rk2-ccm-experiment.patch`, in no kernel conf, tries
three IV layouts on the GCM path, chosen by `rk_crypto2.ccm_iv`:

| `ccm_iv` | Fed to the engine                                                   | Self-test, vector 0     |
| -------- | ------------------------------------------------------------------- | ----------------------- |
| 0        | the 16-byte IV as Linux passes it, the associated data as is        | wrong result            |
| 1        | the nonce alone, its length as `IV_LEN`                             | wrong result            |
| 2        | IV as the counter block A0; B0 and the length-prefixed data, padded | right once, then `-110` |

Layout 2 gives the right ciphertext and tag on the first request, and the next request times out. A
soft reset before each job and clearing `TAG_VALID` after each change nothing. Next: find which wait
times out, the DMA's or the tag's; the patch logs "tag never valid" when it is the tag.
