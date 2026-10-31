# meson-codecs — the video decoder and both encoders on the GXLX2 (S905L3)

Patches over `meson-sm1-codecs` at `eb7a444`: its out-of-tree decoder (the mainline staging
meson-vdec with SM1 work) and its two encoders, ported to the S905L3. On TVBian the decoder is
in-tree: `patches/linux-meson/` `0002` puts meson-sm1-codecs's decoder under
`drivers/staging/media/meson/vdec/`, and the `vdec` patches here apply there. The encoders, `0004`,
`0005`, `0016` and `0019`, build out of tree from the same pin, `modules/meson-venc.conf`.

| Patch  | Holds                                                             |
| ------ | ----------------------------------------------------------------- |
| `0001` | the decoder runs GXLX2 as G12A-class, minus two G12A settings     |
| `0002` | no `EPOLLERR` before CAPTURE streams                              |
| `0004` | the H.264 encoder (HCodec) on GXLX2                               |
| `0005` | the HEVC encoder (WAVE420L) on GXLX2                              |
| `0006` | MPEG-1/2 canvases mapped once every CAPTURE buffer is queued      |
| `0007` | CAPTURE formats other than NV12M                                  |
| `0008` | helpers to reboot a microcode and end a drain with LAST           |
| `0009` | MPEG-4 Part 2                                                     |
| `0010` | MJPEG                                                             |
| `0011` | `wrap_input`: a codec frames its input before the parser          |
| `0012` | VC-1, Advanced profile                                            |
| `0013` | the VIFIFO level read while the VLD is reset                      |
| `0014` | at most 16 CAPTURE buffers above 1080p, for CMA                   |
| `0015` | the drain on `STOP` runs from a worker, not the ioctl             |
| `0016` | the HEVC encoder logs errors only, unless `print_level` asks      |
| `0017` | HEVC and VP9 CAPTURE scaled by 2 or 4, per stream through COMPOSE |
| `0018` | HEVC coded up to 4096x2304 on GXLX2                               |
| `0019` | the H.264 encoder finds its canvas run past held canvases         |
| `0020` | one drain at a time: end of stream against a stop's               |
| `0021` | the end-of-stream sequence ends with the parser's search pattern  |
| `0022` | the end-of-stream drain waits while the VIFIFO drains             |
| `0023` | a CAPTURE plane holds the canvas the decoder writes               |
| `0024` | an offset in a packet's padding belongs to the next packet        |
| `0025` | HEVC and VP9 CAPTURE as Amlogic FBC, scatter layout, 8 or 10 bits |
| `0026` | a seek's drained pictures end nothing with LAST                   |
| `0027` | resume on the client's answer to a source change                  |
| `0028` | a canvas for every CAPTURE buffer, kept across a seek             |
| `0029` | HEVC: an IDR or BLA picture releases every earlier reference      |

| Overlay package     | Module        | Device                |
| ------------------- | ------------- | --------------------- |
| `meson-vdec-gxlx2`  | `meson-vdec`  | `meson-video-decoder` |
| `amvenc-avc-gxlx2`  | `amvenc_avc`  | `meson-venc-h264`     |
| `amvenc-hevc-gxlx2` | `amvenc_hevc` | `meson-venc-hevc`     |

## 0001

Amlogic's `media_modules` place GXLX2 (`0x2a`) after G12B, give it G12A's capability entry, and load
G12A's HEVC and VP9 microcode on it. Mainline calls it GXLX and runs it as GXL: HEVC stops after one
frame, VP9 never starts.

Two G12A settings do not hold:

- no HEVC front clock — the factory clock tree has no `clk_hevcb_mux`;
- `HEVC_SAO_CTRL1[15:14]`, `axi_linealign`, at its reset value: 0 or 2 writes the linear output at
  twice the pitch, and Amlogic's driver never writes the field.

HEVC's multi-instance microcode reports on mailbox 0, so the decoder node names SPI 43 `mbox0`.

## 0002

The parser can take a short stream into its FIFO before the first source change; the m2m core then
reports an empty OUTPUT queue with CAPTURE off as `EPOLLERR`, and GStreamer gives up.

## 0004, 0005

The vendor tree already carries `amvenc_avc` and `hevc_enc` nodes, which make platform devices of
those names; the encoders adopt them, with their interrupts and, for WAVE420L, its register window.
The factory kernel probed the WAVE420L on this chip, so GXLX2 joins its chip list. Below 6.19,
`v4l2_m2m_buf_copy_metadata` still takes its `copy_frame_flags` argument.

The H.264 encoder addresses twelve canvases as one run; `0019` takes the first run free, so a canvas
another driver holds no longer fails its load with `ENODEV`.

## 0008-0010

Maxime Jourdan's 5.3-era `codec_mpeg4` and `codec_mjpeg`. Their microcode latches its canvases at
boot, and this decoder boots it before any CAPTURE buffer exists: start raises a source change, and
resume maps the canvases and boots the microcode again. MJPEG writes three planes whatever
`MDEC_PIC_DC_CTRL` says, so it offers YUV420M only, which `0007` lets GStreamer negotiate.

## 0017

The HEVC core's second write, the uncompressed one CAPTURE gets, can be scaled by 2 or 4 each way
while the references stay full size, compressed. A client asks per stream, the stateful decoder's
way: `VIDIOC_S_SELECTION` with `V4L2_SEL_TGT_COMPOSE` on CAPTURE after the source change, before
CAPTURE buffers exist. The driver keeps the rectangle and takes the smallest ratio whose picture
fits it, worked out again from the stream's own visible size once its headers are parsed; `G_FMT`
reports the scaled size, and `G_SELECTION` the visible picture as `CROP` and `COMPOSE_BOUNDS`.

A client that never asks gets `capture_max_width` and `capture_max_height`, 0 for off: the smallest
ratio that fits both. Sizes round down. HEVC and VP9 only: the other codecs run on cores without the
scaler, at 1080p or less here. On the box, as root:

    echo 1920 > /sys/module/meson_vdec/parameters/capture_max_width
    echo 1080 > /sys/module/meson_vdec/parameters/capture_max_height

`patches/ffmpeg/` `0011` makes FFmpeg ask: its decoders' `-capture_max_width` and
`-capture_max_height`.

## 0021-0024

A client queues a stream into the 16 MiB VIFIFO long before the decoder gets through it, at the pace
CAPTURE buffers come back. `0022` lets the end-of-stream drain wait while the VIFIFO level falls,
until only the queued sequence is left, and gives up after 1 s without progress; `0021` ends that
sequence with the parser's search pattern, so the write no longer waits out its 200 ms timeout.

`0023` sizes a plane as the canvas the decoder writes, 64-byte lines down 64-aligned rows; a 544x352
or 720x540 picture overran the old size, which rounded width times height to 64 KiB.

The VDEC_1 microcode reports each picture's VIFIFO offset, and the timestamp is the one of the
packet written there; MPEG-4 and VC-1 at times report an offset in the zero padding behind the
previous packet. `0024` records where a packet's payload ends, and an offset past it takes the next
packet's timestamp.

## 0025

The CAPTURE formats `AMF8` and `AMFA` hand the client the decoder's compressed reference itself: the
header of Amlogic FBC's scatter layout, 288 KiB, whose body pages the decoder keeps per buffer while
the buffer lives. The display's video plane reads it as `DRM_FORMAT_YUV420_8BIT` or `_10BIT` with
`DRM_FORMAT_MOD_AMLOGIC_FBC`, scatter, memory saving at 8 bits; nothing else can. A 10-bit stream
stays 10-bit, and there is no second, uncompressed write.

A request for either answers with the stream's bit depth once the headers are parsed, and a queue of
the other depth is not ready for the stream, so the client learns it from the source change.
`bytesperline` is 0: the layout has no pitch. `patches/ffmpeg/` `0028` asks for it with `-afbc`.

GXLX2 hangs the SoC when its references are written compressed but contiguous, the basic layout: the
watchdog resets the box.

## 0026-0028

A seek streams OUTPUT off and on, and the decoder restarts in between. `0026` keeps the pictures it
completes then from carrying LAST, which made every later DQBUF return EPIPE. `0028` maps a canvas
to every allocated CAPTURE buffer in vb2 order, queued or not, and keeps them across the restart:
the microcode numbers its buffers so, and recycles by that number. `patches/ffmpeg/` `0029` sends
the stream headers again after the flush, which MPEG-4 and VC-1 carry only in `extradata`.

A client that streams CAPTURE on early raced its own source change: STREAMON resumed the decoder,
the event still queued made the client reallocate, and STREAMOFF of a running decoder powers it off.
With the event unread, `0027` leaves the decoder waiting for the client's answer, STREAMOFF and
STREAMON, or `V4L2_DEC_CMD_START` to keep its buffers.

## 0029

HEVC marks references by POC, and every IDR has POC 0: pictures after an IDR kept every earlier IDR
referenced with it, one CAPTURE buffer each, until a reference set no longer named POC 0. Short GOPs
ran out of buffers and stalled, an end of stream never answered. An IDR or BLA picture now releases
every earlier one.

## Upstream

Not submitted.
