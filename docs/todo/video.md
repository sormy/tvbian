# Hardware video: what is left

Every open item for hardware decode, encode, decoder scaling and compressed frames, by chip; then
FFmpeg's, and what no chip has measured yet.

## Allwinner H313

- [ ] MPEG-1: the engine's MPEG-1 mode (`VE_DEC_MPEG_TRIGGER_MPEG1`) needs a flag in the MPEG-2
      controls telling an MPEG-1 stream apart, and an `mpeg1_v4l2request` hwaccel.
- [ ] VC-1 Main: chroma drifts on the SMPTE conformance streams with B pictures, luma too with
      FASTUVMC; the vendor's register writes for Main against ours.
- [ ] VC-1 Simple: a Simple profile file to decode.
- [ ] MPEG-4: interlaced B-VOPs are refused, their field direct mode wrong with every field-distance
      encoding tried at `0x120`. Quarter-sample luma sits 45–57 dB from FFmpeg's, Xvid's 3-point GMC
      38–42 dB on a large pan: a reference decoder would tell which side strays. A damaged stream
      leaves the picture past the error unwritten, where software conceals.
- [ ] The mixer's background shows green on a YUV output (4K60 HDR10, 10-bit 4:2:0) with no video
      plane, and a half-transparent ARGB shadow over it comes out solid black. `sun8i_mixer.c` picks
      RGB or YUV black from the output format at mode set: either the format changes after it, or on
      DE33 the blender works in RGB before the formatter and YUV black is the wrong one.
- [ ] VP9 profile 2 at 1920x1080 decodes to 64 dB, not exact; 2560x1440 and up are exact.
- [ ] VP9 at 3840x2160 decodes at 43 fps; the datasheet gives 60.
- [ ] H.263 at 352x288 differs between two runs.
- [ ] JPEG: 6000x4000 decodes, 6144x6144 hangs the SoC; 6144x4096 and 6144x5120 not tried.
- [ ] Sizes not probed: VP9 at 8192x8192 (HEVC there hangs), MPEG-2 and MPEG-4 to the registers'
      4096x4080, VP8 4096 wide past 2304 lines, both encoders past 4096.
- [ ] Decoder scaling for VP9, VP8, MPEG-2 and JPEG: the register map below.
- [ ] AFBC for H.264 and the other codecs; HEVC and VP9 have it.
- [ ] AFBC and the scaled picture together: AFBC is the primary output's mode.
- [ ] Root-cause the flicker of a full-screen 3840x2160 `AR24` plane over a 3840x2160 `YU10` AFBC
      video, even at 30 Hz, where either plane alone is clean.
- [ ] `linux-sunxi/0096`'s limit: AFBC shrunk by the display at growing ratios (1.7× plays clean, 2×
      for 4K to 1080p, beyond) until the picture or `RCQ sync timed out` fails; the patch's estimate
      set to that edge. Today it refuses 1.7×, which plays.
- [ ] Merge the Cedrus patches that share a responsibility: `0808` resets the largest picture `0803`
      gives JPEG and `0806` gives MPEG-4; each size belongs in its codec's patch.

## Rockchip RK3518

- [ ] HEVC encode: every width tried between 5120 and 8192 (6144, 7168, 7680, 7936) comes out at
      5–14 dB in most runs, at any height and with the memory clock pinned at its top; 5120 and 8192
      always encode clean. Until the cause is known, `hevc_rkmpp` should refuse them.
- [ ] MJPEG decode: MPP's JPEG decoder takes an output buffer with each packet, its task API.
- [ ] MJPEG encode: an `mjpeg_rkmpp` encoder.
- [ ] AVS, AVS+: a sample, then an `rkmpp` decoder for each.
- [ ] VC-1 and RealVideo: whether MPP decodes them on this chip.
- [ ] 10-bit encode input.
- [ ] AFBC and the ½ picture together: MPP stalls asked for both.
- [ ] The ½ picture against RGA2 scaling a full decode, at 4K HEVC.
- [ ] RGA in FFmpeg: `jellyfin-ffmpeg`'s `scale_rkrga`, `vpp_rkrga` and `overlay_rkrga` scale and
      convert on the RGA, not the CPU, for a player the decoder's ½ picture does not fit.
- [ ] Display: through `fbdev`, every frame a CPU copy, 4K60 HEVC decoded at 51 fps showed 27, CPU
      at 48%; frames handed to a VOP2 plane with no copy.

## Amlogic S905L3

- [ ] `meson_vdec`'s MPEG-1/2/4, VC-1 and JPEG take their size from the client's format, clamped to
      1920x1080: a bigger picture decodes broken until the client refuses the clamp, below. H.264,
      VP9 and HEVC refuse past their size, `meson-codecs/0030`.
- [ ] VP9 at 3840x2160 hangs the SoC while ~1.5 GB goes to eMMC, 5 s into the decode, nothing
      logged; either alone passes, HEVC and H.264 at 4K pass both, and the module before
      `meson-codecs/0021` hangs the same. The write's dirty pages were moving into CMA beside the
      decoder's: a VP9 DMA past its buffers is the suspect.
- [ ] The first VP9 4K decode after a boot fails every packet, `Unrecognized dec_status: 00000000`;
      later ones pass.
- [ ] H.264 decoder scaling: only through the multi-instance microcode, `MDEC_DOUBLEW_CFG0`.
      `codec_h264_g12a` with `g12a_h264_multi` or `gxl_h264_multi` from the factory
      `video_ucode.bin` takes the sequence (`CONFIG_REQUEST` twice, `CONFIG_DONE`), then raises no
      interrupt.
- [ ] JPEG decoder scaling.
- [ ] VC-1 Simple and Main, H.263, AVS, RealVideo: microcode in the factory `video_ucode.bin`, no
      codec in `meson_vdec`.
- [ ] H.264 changing resolution inside the final drain, a client that sends end of stream with the
      change still queued, gets the pictures before it only, 120 of 180, and ffmpeg's CLI trips
      `Assertion pkt failed`: the wrapper's reinit clears its drain. Fed at a player's pace it
      passes.
- [ ] One MPEG-4 ASP stream, ffmpeg's own rate-controlled encode, stalls the microcode at its 44th
      picture, `MREG_BUFFERIN` unconsumed with 425 KB in the VIFIFO. Re-encodes and real Xvid and
      DivX samples decode whole.
- [ ] VC-1: a skipped picture (a 1-byte P) yields none, the B-pictures after one at a stream's start
      come out ahead of their I and are dropped, and the last two stay in the microcode: 9 of 1451
      on a WMV clip.
- [ ] FBC for H.264 and the other codecs; HEVC and VP9 have it.
- [ ] FBC body pages live as long as the decoder's CAPTURE buffers: a plane still showing the last
      frame after the decoder closes reads freed pages.
- [ ] `meson-codecs/0029` on 7.3.1.
- [ ] Every size past 3840x2160.

## FFmpeg

- [ ] A package: `patches/ffmpeg/` on 9.0.2 is built by hand today (`research/ffmpeg-v4l2m2m/`); an
      `extras/` package built by `./build.sh` and deployed as a deb, MPP linked static for Rockchip,
      the research build retired. Then the patches sent upstream.
- [ ] `*_v4l2m2m` decoders take a coded size the driver clamped: H313 JPEG past 6000x4000 decodes
      broken, not refused. `0032` refuses it for the encoders.
- [ ] `*_v4l2m2m` decoders decode nothing after an end of stream: a seek back from the end or a
      looped input gets no frames. The restart command goes out; the capture queue stays done.
- [ ] fuseamp asks for compressed frames: `afbc` on `v4l2request` and `*_rkmpp`, `-afbc` on
      `*_v4l2m2m`, where the plane takes the modifier.

## CMA

- [ ] Every family's pool from `BOARD_CMA`, the kernel command line's `cma=`, which overrides a
      tree's `linux,cma`. Today only Rockchip boards take it, 256M by default; Allwinner keeps the
      kernel config's, Amlogic the board tree's 768 MiB.
- [ ] Each board's `board.conf` sets `BOARD_CMA` to its measured peak plus a margin, and the family
      defaults go:
  - H313: 4K Main10 AFBC to the display, Wi-Fi and USB busy.
  - RK3518: 8K HEVC, AFBC frames and the display; its IOMMUs predict a few MiB.
  - S905L3: 4K60 with a player copying frames, HDMI attached; 384 MiB failed once that way.

## Not measured yet

- [ ] Playback end to end, every chip: a real 4K60 stream per codec, at the datasheet's rate,
      decoded and shown with no dropped frames; the suite's rates are the decoder's alone.
- [ ] On a screen, Rockchip and Amlogic: 10-bit and compressed frames shown, the display shrinking
      them, decoder to display with no copy, HDR signalled. All three: 10-bit HDMI.
- [ ] Memory traffic: NV12, P010 and compressed frames at 4K60, by the memory controller's counters.
- [ ] Every chip: the ceiling past the largest size tested, where a table reads ≥.

## Decoder scaling: the interface

One for every family, so a player passes its screen size and never learns the ratios. The decoder
writes a scaled picture while its references stay full size; compressed frames go full size to the
display's scaler instead.

- **Kernel:** `VIDIOC_S_SELECTION`, `V4L2_SEL_TGT_COMPOSE` with `V4L2_SEL_FLAG_LE` on CAPTURE,
  before CAPTURE buffers exist; the driver takes the smallest power-of-two ratio whose picture fits,
  aspect kept. `G_FMT` reports the scaled size, `G_SELECTION` `CROP` the visible one.
- **FFmpeg:** `capture_max_width`, `capture_max_height` — decoder options on `*_v4l2m2m` (`0011`)
  and `*_rkmpp` (`0024`), `v4l2request` device options (`0017`).

## Cedrus scaling registers

On the H616 the HEVC ratio bits work; the `0xf00` block reads 0. ⅛ untested. From the linux-sunxi
wiki, mainline Cedrus, LibreELEC's `0412` and the Allwinner H713 port
(`github.com/well0nez/allwinner-h713-linux`, `mainline/patches/kernel/0271`–`0286`).

| Register       | Field                  | Use                                       |
| -------------- | ---------------------- | ----------------------------------------- |
| VE `0x0cc`     | `[31:16]` `[15:0]`     | secondary chroma, luma stride; chroma ½   |
| VE `0x0e8`     | `[31:30]`              | secondary format: 1, from `0x0ec`         |
| VE `0x0ec`     | `[2:0]`                | secondary format: 4, NV12                 |
| H.264 `0x220`  | bit 9                  | secondary output on                       |
| H.264 `0x240`  | `[9:8]` H, `[11:10]` V | ratio: 0 1/1, 1 ½, 2 ¼, 3 ⅛               |
| H.264 `0x244`  | address, not shifted   | secondary luma                            |
| H.264 `0x248`  | address, not shifted   | secondary chroma                          |
| HEVC `0x530`   | bit 9, bit 31          | secondary output on, DDR consistency      |
| HEVC `0x550`   | `[9:8]` H, `[11:10]` V | ratio, as H.264                           |
| HEVC `0x554`   | address >> 8           | secondary luma                            |
| HEVC `0x558`   | address >> 8           | secondary chroma; low bits `0x580[23:16]` |
| HEVC `0x58c`   | `[24:23]`              | secondary format: 0 8+2, 1 P010, 2 tiled  |
| MPEG-2 `0x1d4` | `[9:8]` H, `[11:10]` V | ratio; `0x1cc`, `0x1d0` addresses         |

VP9 shares the HEVC block, its own enable `VE_DEC_VP9_FUNC_CTRL` bit 9. Per picture, after the codec
setup has written `VE_MODE` (address writes to a stopped engine are dropped): strides, format,
addresses, the enable, the ratio, trigger. The primary output and every reference go to a hidden
full-size picture after the scaled one in the same CAPTURE buffer, as P010 does.
