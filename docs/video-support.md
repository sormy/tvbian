# Hardware video: what each chip plays, records and shows

Which video formats each chip handles in its video hardware, rather than on the CPU. Measured
through FFmpeg 9.0.2 with `patches/ffmpeg/`, on TVBian's kernels. Each chip's columns are
`tools/validate/video.py`'s matrix from one board of it, run again after every kernel or FFmpeg
change:

| Chip            | Die    | Engine, as FFmpeg reaches it                   |
| --------------- | ------ | ---------------------------------------------- |
| Allwinner H313  | H616   | Cedrus, `-hwaccel v4l2request`                 |
| Rockchip RK3518 | RK3528 | MPP, `-c:v h264_rkmpp` and the like            |
| Amlogic S905L3  | GXLX2  | `meson_vdec`, `-c:v h264_v4l2m2m` and the like |

Sizes are the largest that worked here, from a ladder of 1920×1080, 2560×1440, 3840×2160, 4096×2160,
4096×2304, 4080×4080, 5120×2880, 6144×3456, 7680×4320, 8192×4320, 8192×8192 and 16384×8640. A file
larger than the size shown plays on the CPU where the decoder refuses it; the S905L3's, and the
H313's for JPEG, take it and decode it broken.

- ✅ works: the picture matches FFmpeg's own decoder, exactly or within the rounding the format
  allows
- 🟠 works, with issues
- 🟡 high confidence it works, not tried here
- ❓ not tried
- ❌ the hardware can, TVBian (kernel, FFmpeg) cannot yet
- ➖ the hardware cannot

A number points to the note under its table. What the hardware does not play, the player plays on
the CPU instead, on its own.

## Hardware decode

| Codec                  | Allwinner H313 | Rockchip RK3518 | Amlogic S905L3  |
| ---------------------- | -------------- | --------------- | --------------- |
| H.264 8-bit            | ✅ 4096×2304   | ✅ 8192×8192    | ✅ 3840×2160    |
| H.264 10-bit           | ➖             | ✅ 8192×8192    | ➖              |
| HEVC Main              | ✅ 8192×4320   | ✅ 8192×8192    | ✅ 4096×2304    |
| HEVC Main10            | ✅ 6144×3456   | ✅ 8192×8192    | 🟠 3840×2160 ⁷  |
| VP9 profile 0          | ✅ 8192×4320   | ✅ 8192×4320    | 🟠 3840×2160 ¹⁰ |
| VP9 profile 2 (10-bit) | ✅ 6144×3456   | ✅ 8192×4320    | 🟠 3840×2160 ⁷  |
| VP8                    | ✅ 4096×2304   | ✅ 1920×1080    | ➖              |
| AV1                    | ➖             | ➖              | ➖              |
| MPEG-1                 | ❌ ³           | ✅ 1920×1080    | ✅ 1920×1080    |
| MPEG-2                 | ✅ 4000×2250   | ✅ 1920×1080    | ✅ 1920×1080    |
| MPEG-4 (DivX, Xvid)    | 🟠 4080×2160 ¹ | ✅ 1920×1080    | 🟠 1920×1080 ⁸  |
| H.263                  | 🟠 1408×1152 ² | ✅ 1408×1152    | ❌ ⁹            |
| VC-1 Advanced          | ✅ 1920×1080   | ❓              | 🟠 1920×1080 ¹¹ |
| VC-1 Simple            | 🟡 ⁴           | ❓              | ❌ ⁹            |
| VC-1 Main (WMV9)       | ❌ ⁵           | ❓              | ❌ ⁹            |
| JPEG, MJPEG            | ✅ 24 Mpixel   | ❌ ⁶            | ✅ 1920×1080    |
| AVS, AVS+              | ❌             | ❌ ⁶            | ❌ ⁹            |
| RealVideo 8, 9         | ❓             | ❓              | ❌ ⁹            |

1. Files using quarter-pixel or global motion show slight differences from the CPU's picture;
   interlaced files with B-frames play on the CPU.
2. Plain H.263 only; files using its later extensions play on the CPU.
3. The engine has an MPEG-1 mode; our FFmpeg's hardware path takes MPEG-2 only.
4. Our driver takes it; no Simple profile file has been tried.
5. Plays on the CPU: the hardware's colours drift on it.
6. MPP decodes it; our FFmpeg's `rkmpp` decoders do not take it yet.
7. Plays as 8-bit, or at 10 bits as compressed frames for the display.
8. Files using quarter-pixel or global motion show slight differences from the CPU's picture.
9. The chip's microcode for it is on hand; our driver has no decoder for it yet.
10. At 3840×2160, decoding while a large file is written can freeze the box, and the first decode
    after a boot fails.
11. A skipped picture yields none, and a stream's last two stay in the microcode: 9 of 1451 missing
    on a WMV clip.

## Hardware decode speed at 3840×2160

Frames a second through the engine alone, on a synthetic clip, with nothing shown: a ceiling for
playback, not playback itself.

| Codec         | Allwinner H313 | Rockchip RK3518 | Amlogic S905L3 |
| ------------- | -------------- | --------------- | -------------- |
| H.264         | 31             | 61              | 30             |
| H.264 10-bit  | ➖             | 57              | ➖             |
| HEVC Main     | 61             | 117             | 47             |
| HEVC Main10   | 33             | 106             | 64 ¹           |
| VP9 profile 0 | 43             | 76              | 58             |
| VP9 profile 2 | 25             | 67              | 75 ¹           |
| VP8           | 45             | ➖              | ➖             |
| MPEG-4        | 32             | ➖              | ➖             |
| JPEG          | 28             | ❌              | ❓             |

1. Timed as 8-bit pictures, the S905L3's plain output for a 10-bit stream.

## Hardware encode

| Codec        | Allwinner H313 | Rockchip RK3518 | Amlogic S905L3 |
| ------------ | -------------- | --------------- | -------------- |
| H.264        | ✅ 4096×4096   | ✅ 8192×8192    | ✅ 1920×1088   |
| HEVC         | ➖             | 🟠 8192×8192 ²  | ✅ 4096×2304   |
| JPEG, MJPEG  | ✅ 4096×4096   | ❌ ¹            | ➖             |
| 10-bit input | ➖             | ❓              | ➖             |

1. MPP encodes it; our FFmpeg's `rkmpp` encoders do not take it yet.
2. Widths between 5120 and 8192 come out garbled in most runs; 5120 and 8192 encode clean.

## Hardware encode speed at 3840×2160

Frames a second through the engine alone, the pictures from memory.

| Codec | Allwinner H313 | Rockchip RK3518 | Amlogic S905L3 |
| ----- | -------------- | --------------- | -------------- |
| H.264 | 24             | 14              | ➖             |
| HEVC  | ➖             | 16              | 21             |
| JPEG  | 11             | ❌              | ➖             |

## Hardware shrinking while decoding

A video larger than the screen can be shrunk by the decoder itself, which saves memory bandwidth.
Where it cannot, the picture comes at full size, correct, for the display to shrink.

| Codec        | Allwinner H313 | Rockchip RK3518 | Amlogic S905L3 |
| ------------ | -------------- | --------------- | -------------- |
| H.264        | ✅ ½, ¼        | ✅ ½            | ❌             |
| HEVC, Main10 | ✅ ½, ¼        | ✅ ½            | ✅ ½, ¼        |
| VP9          | ❌             | ✅ ½            | ✅ ½, ¼        |
| VP8          | ❌             | ➖ ¹            | ➖             |
| MPEG-2       | ❌             | ➖ ¹            | ➖ ¹           |
| JPEG         | ❌             | ❌              | ❓             |

1. The chip decodes it only to 1920×1080, with nothing to shrink.

## Compressed frames

A decoder can write its pictures compressed, for less memory traffic to the display, the only reader
that can take them.

| Codec        | Allwinner H313 | Rockchip RK3518 | Amlogic S905L3 |
| ------------ | -------------- | --------------- | -------------- |
| Format       | Arm AFBC       | Arm AFBC        | Amlogic FBC    |
| H.264        | ❓             | 🟡 ¹            | ❓             |
| HEVC, Main10 | ✅             | 🟡 ¹            | 🟡 ¹           |
| VP9          | ✅             | 🟡 ¹            | 🟡 ¹           |
| Other codecs | ❓             | ➖              | ❓             |

1. The decoder writes them; nothing has been shown on a screen yet.

## Memory

Where a video engine has no IOMMU, its pictures come from CMA, a contiguous pool reserved at boot
that the rest of the system borrows back only for movable pages. The decoder's share at its peak,
with the clip already in memory:

| Case                                         | Allwinner H313 | Rockchip RK3518 | Amlogic S905L3 |
| -------------------------------------------- | -------------- | --------------- | -------------- |
| Pool, `BOARD_CMA`                            | 16 MiB         | 512 MiB         | 512 MiB        |
| Video and display IOMMU                      | yes            | yes             | no             |
| Idle use                                     | 1.5 MiB        | 1.2-2.3 MiB     | ≤ 42 MiB       |
| 4K H.264, HEVC, VP9                          | ❓             | ❓              | 291-294 MiB    |
| 4K HEVC Main10                               | ❓             | ❓              | 331 MiB        |
| 4K Main10, compressed frames                 | ❓             | ❓              | 139 MiB        |
| 4K VP9, compressed frames                    | ❓             | ❓              | 87 MiB         |
| Seek, 4K VP9                                 | ❓             | ❓              | 311 MiB        |
| Resolution change, 720p, 1080p               | ❓             | ❓              | 90-96 MiB      |
| A player's peak, the system's share included | 1.5 MiB        | 2.3 MiB         | 397 MiB        |

A player's peak is a 4K60 screen with a 4K video plane and the interface, flipped at a player's
pace, while the engine decodes: on the H313 4K Main10 with AFBC frames and Wi-Fi busy, on the RK3518
8K HEVC with AFBC frames, on the S905L3 4K60 HEVC and VP9, 8 and 10 bits, copied out. A pool is that
peak plus a margin, 29% on the S905L3 for fragmentation and a seek's reallocation. The H313's
decoder allocates through its IOMMU from ordinary memory: a large pool starves it, and on 512 MiB a
24 Mpixel JPEG exhausted the 1.5 GiB box. The S905L3's kernel has no CMA debugfs or sysfs: in use is
`CmaTotal` less `CmaFree` from `/proc/meminfo`, which counts page cache in the pool too.

## Output and display

| Feature                            | Allwinner H313 | Rockchip RK3518 | Amlogic S905L3 |
| ---------------------------------- | -------------- | --------------- | -------------- |
| 10-bit pictures to the display     | ✅             | 🟡 ³            | 🟡 ³           |
| Compressed pictures to the display | ✅             | 🟡 ³            | 🟡 ³           |
| The display shrinks them           | 🟠 ¹           | ❓              | ❓             |
| Shrunk while decoding, compressed  | ➖             | ❌ ²            | ➖             |
| HDR signalled to the TV            | ✅             | ❓              | ❓             |
| 10-bit HDMI                        | ❓             | ❓              | ❓             |
| Decoder to display with no copy    | ✅             | 🟡 ³            | 🟡 ³           |

1. Refused today, the decoder shrinking the video instead; the hardware shrinks them cleanly to
   about 1.7×.
2. MPP stalls asked for both, so it is not asked: shrunk frames come uncompressed, with a warning.
3. Decoded frames reach the display driver; nothing has been shown on a screen yet.

A video larger than the screen comes either shrunk while decoding, as plain frames, or compressed at
full size for the display to shrink. Photos with full colour detail (4:2:2, 4:4:4) come out at
video's usual 4:2:0. HDR and wide colour pass through to the display unchanged; no chip converts
them.
