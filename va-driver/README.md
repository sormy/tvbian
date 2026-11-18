# tvb-va-driver: a VA-API driver for the TV boxes' video engines

One VA front end and one build with every backend: each backend's init declines without its
hardware, and the first that finds hardware serves. Built, packaged as `tvb-va-driver` and tested on
a box of each family known here; no image installs it yet.

| Backend        | Engine                        | Known here on                     |
| -------------- | ----------------------------- | --------------------------------- |
| `rkmpp`        | Rockchip's MPP                | RK3528, RK3518                    |
| `v4l2-request` | a stateless V4L2 decoder      | Cedrus (H616, H313)               |
| `v4l2m2m`      | a stateful V4L2 codec         | S905L3; Cedrus's JPEG and encoder |
| `lavc`         | the CPU, for the tests, named | the host                          |

- **Backends:** `src/backend_mpp.c` with libmpp; `src/backend_request.c` and `request_*.c`;
  `backend_v4l2m2m.c`; `backend_lavc.c`, libavcodec, in the host's build alone.
- **Names:** libva names a driver after the DRM driver of the render node a client opens: the
  package installs `tvb_drv_video.so` under each GPU's name in `build.sh`'s `GPU_DRIVERS`, and udev
  links that node as `/dev/dri/va`. The same rule opens `/dev/dma_heap/system` to the `video` group,
  where a desktop user's surfaces get their own memory.
- **Linking:** libmpp is linked in statically; the driver exports `__vaDriverInit_1_22` alone, so
  the library's symbols meet no other copy in a process. `patches/mpp/` makes MPP's platform probe a
  call, made only where `/dev/mpp_service` is.
- **Vendor string:** `TVBian VA-API driver: <backend>`.
- **megi's driver:** I read megi's GPL-3.0 `libva-v4l2_request` to learn how VA maps onto the
  stateless controls. None of its code is used.

## Design rules

The driver serves any SoC whose kernel drivers follow the V4L2 codec specifications, or Rockchip's
MPP, beside any GPU Mesa drives. A rule the code does not meet yet is an open todo.

- **Detect, never name.** What an engine decodes and encodes, its sizes, profiles, formats and rate
  controls are read from the kernel in `vaInitialize`. No chip, board or driver name decides a
  behaviour.
- **Offer what the engine shows; refuse what it cannot show.** A stream or picture the engine would
  get wrong fails at its context or its picture; it never comes out broken.
- **Mainline interfaces first.** Stateless controls and stateful mem2mem as the kernel documents
  them. A control not yet upstream (MPEG-4, VC-1, Cedrus's AFBC) is detected at run time, and its
  header names the kernel patch it needs.
- **One build, every backend.** Each backend's init declines without its hardware; the first that
  finds hardware serves.
- **Capabilities decide the output.** A compressed or 10-bit format goes out when the client asks
  for it or the GPU can sample it, never because of the GPU's name.
- **Zero copy by default.** Pictures decode into the surfaces' memory; a copy only where a layout
  differs, and its cost shows in the speed tests.
- **No client is special.** Behaviour follows the VA calls, never the client's name: FFmpeg,
  GStreamer and the browsers get the same driver.
- **Devices are found, not numbered.** Listed in `/sys`, numbered nodes as the fallback, and opened
  in `vaInitialize`, before a client's sandbox closes.
- **Packaging stays outside.** The file names per GPU, the `/dev/dri/va` link and the clients'
  environment are the distribution's; the driver's own settings are one conf file and environment
  variables, each with a working default.
- **Every client, against software.** FFmpeg and GStreamer decode every clip, frame by frame or by
  luma PSNR against FFmpeg's software decode; speed is held against the box's previous run; the CPU
  engine runs the suite on the host before any box.
- **Standalone.** libva, libdrm, the kernel's headers and, for Rockchip, MPP: no path or tool of the
  repo it is built in, and one exported symbol.

## What each engine offers

Offers are read from the engine in `vaInitialize`, never kept per family, so a new SoC needs no
code. The engine is the first backend built in whose probe finds something to offer: MPP, then a
stateless V4L2 decoder, then a stateful one.

| Engine | Codec and profile              | Largest picture                         |
| ------ | ------------------------------ | --------------------------------------- |
| V4L2   | `ENUM_FMT`; the profile menu   | `ENUM_FRAMESIZES`, or `TRY_FMT`'s clamp |
| MPP    | its SoC table: codings, 10-bit | the client's class: 8K, 4K or 1080p     |

An encoder takes a fixed QP, and on V4L2 the bitrate modes its `V4L2_CID_MPEG_VIDEO_BITRATE_MODE`
menu lists; MPP all three. `TRY_FMT` is asked three sizes, very wide, very tall and both: a clamp
that trims by area, as Cedrus's JPEG does, says so only in the last.

A device with no profile menu offers every profile of a format it takes; a 10-bit profile on Cedrus
needs a 10-bit CAPTURE format, and is sized by the 10-bit headers its context takes
(`VIDIOC_TRY_EXT_CTRLS` on a context of its own), as Cedrus checks a 10-bit size there alone. Sizes
are rounded up to whole macroblocks, as VA sizes a context. The table is what each family's box
reports here:

| VA profile, entrypoint   | `sunxi-h616`          | `rk35xx`                 | `meson-gxl`      |
| ------------------------ | --------------------- | ------------------------ | ---------------- |
| H.264 CB, Main, High VLD | ✓ request             | ✓                        | ✓                |
| H.264 High 10 VLD        | ➖ engine             | ✗ not offered            | ➖ engine        |
| HEVC Main VLD            | ✓ request, AFBC       | ✓                        | ✓, scaled        |
| HEVC Main 10 VLD         | ✓ request, P010, AFBC | ✓ NV15: CPU, or exported | ✓ 8-bit, widened |
| VP9 profile 0 VLD        | ✓ request, AFBC       | ✓ RK3518, per MPP        | ✓, scaled        |
| VP9 profile 2 VLD        | ✓ request, P010, AFBC | ✓ NV15: CPU, or exported | ✓ 8-bit, widened |
| VP8 VLD                  | ✓ request             | ✓                        | ➖ engine        |
| MPEG-2 Simple, Main VLD  | ✓ request             | ✓                        | ✓                |
| MPEG-4 SP, ASP VLD       | ✓ request, H616       | ✓                        | ✓                |
| H.263 Baseline VLD       | ✓ request, H616       | ✓                        | ➖ engine        |
| VC-1 Simple VLD          | ✓ request             | ➖ no decoder            | ➖ Annex G only  |
| VC-1 Main VLD            | ➖ `0065` refuses it  | ➖ no decoder            | ➖ Annex G only  |
| VC-1 Advanced VLD        | ✓ request             | ➖ no decoder            | ✓                |
| JPEG Baseline VLD        | ✓ stateful node       | ➖ engine                | ✓                |
| H.264 EncSlice           | ✓ stateful node       | ✓                        | ✓ Main streams   |
| HEVC Main EncSlice       | ➖ engine             | ✓                        | ✓                |
| JPEG EncPicture          | ✓ stateful node       | ➖ engine                | ✗ no encoder     |

Key: ✓ offered, ✗ the engine can but this driver cannot yet, ➖ the engine or VA cannot.

- **VA has no profile for these,** so no engine offers them: MPEG-1, AVS and AVS+, AVS2, RealVideo.
- **No engine encodes VP8.**
- **`rk35xx` H.264 High 10:** whether the RK3528's decoder takes it is not known here.
- **`meson-gxl` 10-bit:** the decoder writes HEVC Main 10 and VP9 profile 2 as 8-bit NV12; a P010
  surface gets each sample widened, by the CPU, when it is read.
- **MPP's 8K class** is 8192×4320: a taller stream, which the RK3528 decodes, is refused.
- **H.264 High encode** is offered where the encoder's menu lists Main: a Main stream is a High one,
  and FFmpeg asks High first.
- **`rk35xx` 10-bit, NV15:** MPP's only 10-bit output, which VA cannot name. The driver lists NV12
  for a 10-bit config, and a surface the client makes so gets each picture unpacked by the CPU. A
  client that asks for P010 surfaces gets MPP's NV15 as it is: exported as one `DRM_FORMAT_NV15`
  layer, for display planes; their separate-layer export, derive and images go through the same
  unpacking into P010. Lima cannot sample P010 either way.
- **What clients ask for (host, the CPU engine):** FFmpeg and mpv `--hwdec=vaapi-copy` take P010
  whenever a 10-bit config lists it, even second; with NV12 listed alone both decode HEVC Main 10
  and VP9 profile 2 into NV12 surfaces, FFmpeg's `hwdownload` and its automatic copy alike. Hence
  NV12 alone on `rk35xx`. GStreamer's `va` decoders take only a 10-bit format for a 10-bit stream:
  `extras/gst-plugins-bad` carries the patch that lets them narrow too.
- **`sunxi-h616` AFBC:** HEVC and VP9 decode into Cedrus's AFBC (`AS12`, `AS01`) when every render
  target listed `DRM_FORMAT_MOD_ARM_AFBC(16x16 | SPARSE | SPLIT)` in
  `VASurfaceAttribDRMFormatModifiers` and the render node is Panfrost's; linear otherwise, and never
  on Lima. Cedrus's buffer is exported as one `DRM_FORMAT_YUV420_8BIT` or `_10BIT` layer of one
  plane; separate layers, derive and images are refused, as the CPU cannot read it.
- **`meson-gxl` scaled decode:** a `VAProcPipelineParameterBuffer` on an HEVC or VP9 decode context
  (`VAConfigAttribDecProcessing`) asks the decoder's scaled CAPTURE through the COMPOSE selection
  (`meson-codecs/0017`). Only 1/2 and 1/4 in both directions, as the decoder takes; any other size
  is refused. The other codecs run on cores without the scaler. Neither FFmpeg nor the browsers ask
  for it.
- **4K through a client:** on `sunxi-h616` WebKit plays linear 8-bit 4K VP9 and HEVC at 24 fps, the
  pictures in Cedrus's buffers end to end; linear P010 at 4K about 8 fps, which AFBC, only for a
  client that lists the modifier and only on Panfrost, may carry. On Lima AFBC pays on a display
  plane alone.
- **How clients reach it:** FFmpeg picks no hardware itself: a program asks for a decoder by name
  (`h264_rkmpp`) or opens a hwaccel device (`vaapi`, `v4l2request`). Firefox opens VA-API only.
- **MPEG-4, H.263:** sprites and GMC S-VOPs are refused on the bitstream engines (`rk35xx`,
  `meson-gxl`): their trajectories would need coding back. Xvid's and DivX's encoder-bug workarounds
  rest on their user data, which VA drops: a bitstream engine sees none. H.263 takes the five
  standard sizes only; anything else needs H.263+'s PLUSPTYPE, which VA has no fields for.
- **Cedrus MPEG-4 (`0806`):** the H616 only; it refuses data partitioning, reversible VLC, static
  sprites and interlaced B-VOPs.
- **VC-1:** VA gives POSTPROC's value, not POSTPROCFLAG: a stream that sets the flag and sends 0
  throughout is rebuilt without it, which moves the rest of its picture header. `meson-gxl`'s
  decoder takes Annex G, Advanced profile with start codes, alone.

## Cedrus: VA onto the stateless controls

- **Requests:** one per slice. Each H.264 request carries the SPS, PPS, scaling matrix, decode
  parameters and slice parameters, plus the prediction weights when the slice uses them. A
  frame-based engine gets one request for the whole picture.
- **Start code:** sent as `V4L2_CID_STATELESS_H264_START_CODE` asks.
- **What VA leaves out,** recovered by reading each slice header in full with VA's parameters:
  - `nal_ref_idc`, `idr_pic_id`, the POC fields;
  - the bit sizes of the POC and `dec_ref_pic_marking()` syntax;
  - `header_bit_size`, counted from the NAL header without emulation prevention;
  - the PPS's `num_ref_idx` defaults.
- **DPB:** VA's reference frames in VA's order, each entry referenced by the timestamp of its
  surface's latest picture. The reference lists index into it.
- **MPEG-2:** one request a picture: sequence, picture and quantisation, with MPEG-2's default
  matrices where VA does not load one.
- **CAPTURE buffers are Cedrus's own, lent to the surfaces:**
  - `V4L2_MEMORY_MMAP`, exported as dma-bufs, laid out as the kernel's `G_FMT` says. One at the
    start, more by `VIDIOC_CREATE_BUFS`, up to 32.
  - Each surface decoded into gets a buffer of its own for the context's life; a destroyed surface's
    goes to the next. A surface with no memory of its own takes the buffer as its own: each picture
    decodes in place, and export, derive and images read it with no copy. A surface that already has
    memory gets each picture copied in, as does a 10-bit picture into an 8-bit surface; an AFBC
    picture binds as it is.
  - A surface exported or derived before its first picture, as GStreamer's pool does, is lent its
    buffer then, by a decode context of its size and format.
  - Each picture gets a timestamp of its own, kept by vb2 on the surface's buffer: a buffer is
    decoded into again only when its surface is, as VA references it until then.
  - Each request is waited for, so a picture is whole when `vaEndPicture` returns; one that fails or
    never completes stops and restarts both queues.
  - Surfaces' own dma-bufs cannot be CAPTURE: vb2 maps an imported CAPTURE buffer `DMA_FROM_DEVICE`,
    which `sun50i-iommu` maps write-only, and Cedrus reads back the picture it writes (deblocking)
    and its references. The same holds for `V4L2_MEMORY_FLAG_NON_COHERENT` buffers, allocated for
    that direction. So the memory is Cedrus's coherent buffers, which the CPU reads uncached: slow
    for a client that reads pictures, nothing for one that exports them.
- **Formats the GPUs sample:** Cedrus's tiled NV12 (`NV12_32L32`) is read only by the display
  engine; Panfrost samples linear NV12, P010 and AFBC, Lima linear NV12.
  - On the H616, Panfrost (Mali-G31) takes all three.
  - AFBC when the client lists its modifier at surface creation, for HEVC and VP9; see above.
- **Chromium:** a client's own buffer gets each picture copied in by the CPU; the buffer Cedrus
  decoded into stays the reference.
- **VC-1 skipped picture:** references its forward reference's buffer, and gets that picture copied
  into its own memory; once the reference's surface is decoded into again, a picture naming the
  skipped one finds no buffer.
- **HEVC:** one request per slice: SPS, PPS, scaling matrix, decode parameters, slice parameters,
  and the entry points when there are any.
  - Each slice header is read in full for what VA leaves out: the entry points,
    `no_output_of_prior_pics_flag` and the long-term set's size.
  - The current sets come from VA's reference flags, before ordered by POC descending and after
    ascending.
  - Frame-based engines are refused.
- **VP8:** the frame control, segments in absolute mode, since VA gives absolute values. The frame
  goes out with the frame tag VA strips, rebuilt.
- **VP9:** the frame control and the compressed header's control, one request a frame
  (`src/request_vp9.c`, `src/vp9_header.c`):
  - VA's slice data is the whole frame. The uncompressed header is read from it, with the loop
    filter deltas and segment features that earlier frames left; an inter frame that takes its size
    from a reference gets VA's frame size.
  - The compressed header goes through VP9's boolean decoder: tx mode, coefficient, skip, inter
    mode, filter, is-inter, reference mode, single and compound reference, y mode, partition and MV
    probability deltas, as the kernel's `v4l2_vp9_fw_update_probs` takes them. Its trailing padding
    must read zero, so a misparse is refused, not sent.
  - The references are VA's `last`, `golden` and `alt` surfaces, each by its timestamp.

- **VC-1 (`linux-sunxi/0064`, `0065`):** one request a picture, or a field, with the slice
  parameters and bitplanes controls, kept privately in `src/vc1-ctrls.h`:
  - The data from the picture header on, as VA gives it, later slices behind their start codes;
    `data_bit_offset` is VA's `macroblock_offset`.
  - PQINDEX from VA's PQUANT and quantizer kind, through SMPTE 421M's table 36.
  - A field picture's FPTYPE split into the field's own type.
  - VA's bitplanes, a nibble a macroblock, unpacked into Cedrus's planes of a bit each.
  - A skipped P picture still goes as a request, for its timestamp, then gets its forward reference
    copied in: Cedrus reconstructs nothing for it.
- **MPEG-4, H.263 (`linux-sunxi/0805`, `0806`):** the engine reads no header, so each run of
  macroblocks is a request: a VOP's video packets, found at their resync markers, or H.263's GOBs,
  at their start codes. Each run's first macroblock and quantiser come from its packet or GOB
  header; the VOP's own come from VA. VA's zigzag matrices go as they are, MPEG-4's defaults where
  not loaded. FFmpeg fills H.263's VOL fields from a context that has none, so only the short-header
  flag is taken from them.
- **10-bit:** the stream's depth is set (HEVC's SPS, VP9's frame) before CAPTURE's format, as Cedrus
  lists its 10-bit formats only once told; a format the driver did not keep is refused, not decoded
  into memory laid out otherwise.

## MPP and meson: the rebuild

MPP and the meson decoder take only bitstreams. `src/{h264,hevc,vp8,vp9,mpeg2,jpeg,mpeg4,vc1}.c`
rebuild one access unit from each picture's VA buffers:

| Codec  | Rebuilt                                                                         |
| ------ | ------------------------------------------------------------------------------- |
| H.264  | SPS, PPS; PPS defaults read from slice headers; High 10's QP offset undone      |
| HEVC   | VPS, SPS, PPS; each slice's header rewritten with its short-term set inline     |
| VP9    | nothing: VA's slice data is the whole frame                                     |
| VP8    | the frame tag and key-frame header                                              |
| MPEG-2 | sequence, picture, picture coding and quant matrix headers                      |
| JPEG   | SOI, DQT, SOF0, DHT, DRI and SOS around the scan                                |
| MPEG-4 | VOS, VO, VOL; the VOP header, the coded data shifted in behind it               |
| H.263  | the picture header, TR counted; the coded data shifted in behind it             |
| VC-1   | Advanced: sequence and entry-point headers, start codes; Simple, Main: STRUCT_C |

- **MPEG-4's slice data** starts at the byte holding the first macroblock bit, `macroblock_offset`
  the bit within it, so the rest is copied shifted behind the rebuilt VOP header, the stuffing
  rewritten at its end.
- **MPEG-4's VOP times:** VA has none. An I- or P-VOP comes TRD ticks after the last, a B-VOP TRB
  after the one before that, `modulo_time_base` counted from the same; on FFmpeg's clips every VOP
  comes out bit for bit.
- **VC-1 Advanced:** VA keeps the picture layer and drops the start codes, so the frame, field and
  slice start codes go back; a field picture is held until its second field and goes out whole.
- **VC-1 Simple and Main:** each frame goes behind STRUCT_C, the sequence layer an engine takes out
  of band (Annex J); the host engine takes it as extradata.

Each rebuilt H.264 and HEVC sequence declares a reorder depth of 0. MPEG-2's sequence and MPEG-4's
VOL do not declare low delay: VA does not say whether B-pictures come, and a decoder told there are
none manages its references otherwise. Refused:

- H.264 with `pic_order_cnt_type` 1;
- HEVC with long-term sets in its SPS;
- MPEG-4 with sprites or GMC S-VOPs.

VA carries none of these whole.

- **MPP:**
  - `MPP_DEC_SET_IMMEDIATE_OUT` and parser split mode off are set before `mpp_init`: each packet is
    one whole picture, handed out once decoded.
  - 8-bit pictures decode straight into the surface's own memory, committed to MPP's buffer group.
    The driver holds every committed buffer but the target's, so MPP can take only that one, and
    holds it again once MPP took it. A target MPP still reads gets a spare buffer and a CPU copy.
    Surfaces are sized at MPP's twice-the-luma.
  - VP9's rows are padded to an odd multiple of 256 bytes, which no surface's pitch is: a surface's
    memory no client has seen is laid out again as MPP decodes, none once any surface was exported,
    as GStreamer takes one export's layout for every surface's.
  - 10-bit pictures go to buffers MPP allocates; a picture a surface holds keeps its buffer, and the
    decoder lives until the last such picture is released.
  - A picture still held when a client syncs on it is drained by an end-of-stream packet, and MPP
    reset.
  - VP9 and VP8 are offered as `mpp_check_support_format` says.
  - Encode imports the surface's dma-buf, its strides set in MPP's preprocessing as they are.
  - MPP's own log is set to warnings.
- **meson:**
  - Every OUTPUT buffer is stamped with its surface.
  - Every keyframe carries its parameter sets.
  - A resolution change reallocates CAPTURE while surfaces keep their pictures on their own fds.
  - The decoder hands a picture out up to 6 packets late; a sync on one still held drains it with
    `V4L2_DEC_CMD_STOP` once the decoder has been quiet 20 ms a 1080p picture's worth of pixels, 80
    at 4K, counted from when CAPTURE starts streaming. Meson's session ends at a drain, so
    the stream goes on in a new one, its headers sent again; the old one stays while surfaces hold
    its pictures.
  - MPEG-1/2/4 and VC-1 hold their last pictures until more stream comes, and a new session has no
    references: after a drain mid-stream, a predicted picture is refused until the next intra one. A
    client that syncs each picture before sending the next, as FFmpeg's command line, gets missing
    pictures, never wrong ones; one that feeds ahead gets them all.
  - `VAAPI_HELD_PICTURES`, or `held-pictures =` in `/etc/tvb-va-driver.conf`, sets that: `refuse`,
    the default; `off`, not offered; `decoded`, every picture as it comes, wrong or not.
  - A format without `V4L2_FMT_FLAG_DYN_RESOLUTION`, as MPEG-1/2/4 and MJPEG, or a decoder without a
    source-change event, as Cedrus's JPEG node, gets CAPTURE after its first packet.
  - A hidden VP9 frame goes out with the next in one superframe, as the encoder wrote them: sent
    alone, it takes a CAPTURE buffer as a picture, and the decoder drops the next shown one.
  - CAPTURE holds the surfaces' pictures and 16 more, within 192 MiB. Where the kernel grants fewer,
    as MJPEG's 4 and MPEG-4's 8, each picture is copied into its surface and its buffer queued
    again.
  - MJPEG writes three planes (`YUV420M`), taken as they are and interleaved when read.
- **Late binding:** both engines choose their own CAPTURE buffer, so a picture binds to its surface
  late. It is exported in place when the surface has no memory of its own and the layout is the
  surface's, and copied by the CPU when it has, or when it is read in another layout.

## Surfaces, encode, VideoProc

- **Owned memory:** a surface gets its own dma-buf, from `/dev/dma_heap/system` or lent by Cedrus
  (see above), when a client needs it fixed:
  - Kodi's fresh export;
  - VLC's derive and buffer handle;
  - GStreamer's pool export;
  - `vaPutImage`.
- **Import:** Chromium's `DRM_PRIME` and `DRM_PRIME_2` buffers come in linear, one object.
- **Encode:**
  - One L0 reference, no B-frames, no packed headers; the rate controls the engine lists.
  - A client's IDR request becomes the engine's forced key frame.
  - The picture size is the input surface's.
  - FFmpeg 7.1 lists `h264_v4l2m2m` before `h264_vaapi`, and Firefox takes the first, so on `meson`
    it may pick the stock wrapper. A driver cannot change that.
- **VideoProc:** not supported. No engine here scales cheaply.

## Build

On the host, in the repo checkout:

```sh
./build.sh va-driver          # build/out/debs/tvb-va-driver_<version>_arm64.deb
./build.sh va-driver check    # the driver and the CPU test engine, then the host's tests
```

The driver lands in `build/out/va-driver/driver/`, beside the probe the tests use. `check` also
makes the clips, in `build/out/va-driver/clips/`. libmpp is built at the commit `build.sh` pins.

The host's test engine links FFmpeg 9.0.2, patched with `patches/ffmpeg/`'s `0039` so its H.264
decoder hands pictures out in decode order. The host build carries the Cedrus backend too, which
there writes its controls to a file for the mapping test.

## Test on a box

On the host, after `./build.sh va-driver check`, with the box's SSH key in place:

```sh
python3 tools/validate/va_driver.py --box root@<box>.local --family <family>
```

It copies the driver, the suite and the clips to a private directory under the box's `/var/tmp`,
runs the suite as root, and removes the directory. The suite drives Debian's own clients: install
`vainfo ffmpeg mpv gstreamer1.0-tools gstreamer1.0-plugins-bad` on the box first. A box running a
local Mesa build needs that build's `libglx-mesa0` installed beside them. Exit status 1 on any FAIL.

## Tests

`tests/vaapi_test.py` prints `va.<check> value` lines, with `FAIL va.<check>` or
`UNTESTED va.<check>` after any that failed or could not run.

| Check            | What it compares                                                   |
| ---------------- | ------------------------------------------------------------------ |
| `unit.*`         | bit writer and VP9 header, under ASan and UBSan                    |
| `unit.rebuild.*` | each rebuilt header element against the clip's own                 |
| `decode.*`       | ffmpeg through VA against its software decode, frame by frame      |
| `mapping.*`      | host: the Cedrus controls against FFmpeg's or `headers.py`'s parse |
| `encode.*`       | `*_vaapi`, decoded back: every frame, Y PSNR ≥ 30 dB, its size     |
| `mpv.*`          | `--hwdec=vaapi-copy`; `--hwdec=vaapi` on a display                 |
| `gstreamer.*`    | Debian's `va` elements on every `decode.*` clip and encode         |
| `probe.*`        | `tests/va_probe.c`: Kodi's, VLC's and Chromium's surface calls     |
| `node.*`         | box: `/dev/dri/va` is the GPU's render node, and `renderD128`      |

- **Decode** passes on identical frames, or on Y PSNR ≥ 50 dB where the engine's IDCT or a 10-bit
  picture narrowed to 8 bits differs. On a box the engine's interrupts must move. A 10-bit clip
  downloads as P010, or NV12 where the engine narrows. GStreamer's frames are judged against the
  same software decode; it has no MPEG-4, H.263 or VC-1 decoder.
- **Rebuilds** are replayed from each clip's captured VA buffers (`VAAPI_CAPTURE`) and compared by
  FFmpeg's `trace_headers`; MPEG-4, H.263 and VC-1, which it cannot trace, by `tests/headers.py`.
  The coded data is compared byte for byte.
- **Rebuilt otherwise, by design,** and so not compared: `tests/vaapi_test.py`'s `REBUILT_OTHERWISE`
  and `PARSED_OTHERWISE` give each element and its reason.

## Results

✅ the host, 2026-11-15, `./build.sh va-driver check`: exit 0. 40 rebuilds bit-exact against their
clips; 39 clips decode identical to software; every Cedrus mapping and probe passes. UNTESTED:
GStreamer, which needs a render node, and the mapping of interlaced VC-1 pictures, which
`headers.py` does not read.

On a box of each family, 2026-11-15, `tools/validate/va_driver.py`:

| Family       | Box            | Fails                             |
| ------------ | -------------- | --------------------------------- |
| `rk35xx`     | `r69-1`        | none                              |
| `sunxi-h616` | `tanix-tx1-v2` | none                              |
| `meson-gxl`  | `h96max-m20`   | interlaced MPEG-4; VC-1 AP slices |

Interlaced MPEG-4 on `meson-gxl` is the decoder's, as through `ffmpeg9`; `vc1-ap-slices` there lets
one wrong picture through after a drain, open. Every other offer passes, decode and encode.

- **Bit-exact on a box:** H.264 (all 9 clips) everywhere; HEVC Main and VP9 profile 0 everywhere,
  odd sizes included; HEVC Main 10 and VP9 profile 2 on `sunxi-h616`; VP8; VC-1 Advanced on
  `sunxi-h616` and interlaced on `meson-gxl`. HEVC Main 10 and VP9 profile 2 narrow to 8 bits on
  `rk35xx` (56, 61 dB) and `meson-gxl` (61, 65 dB).
- **Within 50 dB:** MPEG-2, MPEG-4 and H.263 at 50–74 dB, the engines' IDCT; JPEG 71–77 dB.
- **`meson-gxl` held pictures:** FFmpeg's command line syncs each picture before the next packet;
  with `meson-codecs` `0037` every MPEG-2 and MPEG-4 clip but the interlaced one comes out whole.
- **Clients:** `mpv --hwdec=vaapi-copy` and GStreamer's `va` decoders and encoders on `rk35xx` and
  `sunxi-h616`; `mpv --hwdec=vaapi` fails on `meson-gxl` and is untested on the others, which had no
  display connected.
