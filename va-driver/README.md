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
  where a desktop user's surfaces get their own memory. A user-environment generator has GStreamer's
  `va` plugin load the driver (`GST_VA_ALL_DRIVERS`), ranks GStreamer's own stateless decoders out,
  every node's, and on meson ranks the `va` decoders out: meson's holds each picture until later
  packets, which GStreamer, syncing each first, never sends; GStreamer's own V4L2 decoders feed
  ahead there, and the `va` encoders stay, ranked first, as GStreamer ranks them out. Where the
  engine is MPP or a stateless decoder, it turns Firefox's decoder sandbox off
  (`MOZ_DISABLE_RDD_SANDBOX`), which opens `/dev/video*` alone. It ships the browsers' VA defaults
  too, each leaving VA off unless told: Firefox's decode, Chromium's decode and encode.
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
  and VP9 profile 2 into NV12 surfaces, FFmpeg's `hwdownload` and its automatic copy alike. Every
  10-bit config lists P010 first, so the target decides: one that shows 10-bit takes the picture as
  it is, one that shows 8-bit asks `VideoProc` to narrow it. GStreamer's `va` decoders take only a
  10-bit format for a 10-bit stream, which every config lists.
- **AFBC:** the request backend asks its HEVC decoder which AFBC CAPTURE lists: Cedrus's
  `AS12`/`AS01` (`DRM_FORMAT_MOD_ARM_AFBC(16x16 | SPARSE | SPLIT)`) or `rkvdec`'s `AN68`/`AN6a`
  (`16x16 | SPARSE`). A context whose render targets all listed that modifier in
  `VASurfaceAttribDRMFormatModifiers` decodes into it where CAPTURE lists it for the stream; linear
  otherwise. The buffer exports as one `DRM_FORMAT_YUV420_8BIT` or `_10BIT` layer of one plane, or
  with separate layers as the surface's NV12 or P010 layers on that one plane, the second a copy the
  display does not read; derive and images are refused, as the CPU cannot read it.
- **AFBC for every client, a testing switch:** `TVB_VA_AFBC=1`, or `afbc=1` in
  `/etc/tvb-va-driver.conf`, makes every 8-bit H.264, HEVC and VP9 decode AFBC whatever the client
  listed: the request backend's CAPTURE, and MPP's `MPP_FRAME_FBC_AFBC_V2` decoded into the surfaces
  in place, laid out from MPP's own sizing when the surface is made. A client that reads pictures on
  the CPU is refused under it.
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
    decodes in place, and export, derive and images read it with no copy. Memory of its own that the
    client no longer sees, as from a `vaDeriveImage` before the context, is given up for the buffer.
    A surface whose memory the client sees gets each picture copied in, as does a 10-bit picture
    into an 8-bit surface; an AFBC picture binds as it is.
  - A surface exported or derived before its first picture, as GStreamer's pool does, is lent its
    buffer then, by a decode context of its size and format.
  - Each picture gets a timestamp of its own, kept by vb2 on the surface's buffer: a buffer is
    decoded into again only when its surface is, as VA references it until then.
  - Up to four requests are in flight, each with an OUTPUT buffer of its own: `vaEndPicture` queues
    and returns, and the engine decodes while the client readies the next picture. Requests finish
    in order, when their slot is wanted again, when a buffer they write is decoded into again, and
    in `vaSyncSurface` up to the surface asked for; a picture's last one delivers it. One that fails
    or never completes stops and restarts both queues, and the pictures in flight are lost.
  - Surfaces' own dma-bufs cannot be CAPTURE: vb2 maps an imported CAPTURE buffer `DMA_FROM_DEVICE`,
    which `sun50i-iommu` maps write-only, and Cedrus reads back the picture it writes (deblocking)
    and its references. So the memory is Cedrus's own buffers, asked for non-coherent where the
    queue takes cache hints: the CPU reads them cached, each read syncing the dma-buf, and the suite
    decodes as with coherent ones. `rkvdec` and Hantro take them too on `rk35xx-next2`.
  - A new surface is laid out as the decoder writes its size, asked on a handle of its own with
    OUTPUT at that size (`TRY_FMT` on CAPTURE): a client reads one surface's layout and takes it for
    all, `rkvdec`'s 720p VP9 is 768 rows high, and a size change would otherwise leave it reading
    chroma 48 rows early.
  - The stream's size and depth are the device's H.264 or HEVC SPS before its buffers, from the
    context: `rkvdec` refuses a new SPS while it has buffers, and setting it later would free those
    a client was lent.
  - A request carries one slice where the queue advertises
    `V4L2_BUF_CAP_SUPPORTS_M2M_HOLD_CAPTURE_BUF` (Cedrus, Hantro); elsewhere MPEG-4 and H.263 go a
    VOP a request, from the 64-bit word holding the first macroblock. The VOP carries the VOL's
    `vop_time_increment_resolution`, which VDPU2 parses packet headers by.
  - 10-bit comes as P010 on Cedrus and NV15 on `rkvdec`, which lists NV15 only once its SPS says 10
    bits; an NV15 picture read back is narrowed or widened by NEON, straight from the decoder's
    cached memory.
- **Formats the GPUs sample:** Cedrus's tiled NV12 (`NV12_32L32`) is read only by the display
  engine; Panfrost samples linear NV12, P010 and AFBC, Lima linear NV12.
  - On the H616, Panfrost (Mali-G31) takes all three.
  - Panfrost imports a plane only at a pitch and offset of whole 64 bytes; Cedrus pads a row to 32,
    so a decoder's buffer is lent or exported only where it is so aligned, and a surface laid out
    otherwise gets each picture copied in: YouTube's 854 and 426 wide among them.
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
    holds it again once MPP took it: when the picture comes out, or at the next call, before the
    next target is released, so MPP starts a picture while the client works and a call does not wait
    for it. A target MPP still reads gets a spare buffer and a CPU copy. Surfaces are sized at MPP's
    twice-the-luma.
  - VP9's rows are padded to an odd multiple of 256 bytes: a surface made after a VP9 decode config
    is laid out so from the start, and one made before is laid out again while no client has seen
    it, none once any surface was exported, as GStreamer takes one export's layout for every
    surface's.
  - 10-bit pictures go to buffers MPP allocates; a picture a surface holds keeps its buffer, and the
    decoder lives until the last such picture is released.
  - A picture still held when a client syncs on it is drained by an end-of-stream packet, and MPP
    reset.
  - A VP9 key frame of another size in one context, as GStreamer keeps it, gets a decoder anew, the
    pictures still in MPP taken first.
  - JPEG goes through MPP's task API: the coded picture in an MPP buffer, an output buffer handed
    with it, NV12 asked of the engine whatever the JPEG's sampling.
  - JPEG encode at a fixed quantiser, MPP's quality factor the client's quality.
  - No wait on MPP is unbounded: a call takes at most 64 pictures or size changes out, a JPEG waits
    2 s, and a decode that would wait longer fails instead.
  - VP9 and VP8 are offered as `mpp_check_support_format` says.
  - Encode imports the surface's dma-buf, its strides set in MPP's preprocessing as they are.
  - MPP's own log is set to warnings.
- **meson:**
  - Every OUTPUT buffer is stamped with its surface.
  - Every keyframe carries its parameter sets.
  - A resolution change reallocates CAPTURE while surfaces keep their pictures on their own fds.
  - The decoder hands a picture out up to 6 packets late; a sync on one still held drains it with
    `V4L2_DEC_CMD_STOP` once the decoder has been quiet 20 ms a 1080p picture's worth of pixels, 80
    at 4K, counted from when CAPTURE starts streaming. Meson's session ends at a drain, so the
    stream goes on in a new one, its headers sent again; the old one stays while surfaces hold its
    pictures.
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
  - CAPTURE holds the surfaces' pictures and 16 more, within 288 MiB. Where the kernel grants fewer,
    as MJPEG's 4 and MPEG-4's 8, each picture is copied into its surface and its buffer queued
    again.
  - MJPEG writes three planes (`YUV420M`), taken as they are and interleaved when read.
- **Late binding:** both engines choose their own CAPTURE buffer, so a picture binds to its surface
  late. It is exported in place when the surface has no memory of its own and the layout is the
  surface's, and copied by the CPU when it has, or when it is read in another layout.
- **A context closed** first drains the pictures its surfaces still wait for: FFmpeg closes one at a
  size change, and a site's player switches size mid-stream.

## Surfaces, encode, VideoProc

- **Mapped on first use:** a surface's memory is mmapped only when the CPU reads or writes it; a
  picture the engine decodes into and a client never reads costs no mapping.
- **Owned memory:** a surface gets its own dma-buf, from `/dev/dma_heap/system` or lent by Cedrus
  (see above), when a client needs it fixed:
  - Kodi's fresh export;
  - VLC's derive and buffer handle;
  - GStreamer's pool export;
  - `vaPutImage`.
- **Import:** Chromium's `DRM_PRIME` and `DRM_PRIME_2` buffers come in linear, one object.
- **Encode:**
  - One L0 reference, no B-frames, no packed headers; the rate controls the engine lists.
  - A client's IDR request becomes the engine's forced key frame; the GOP is the client's alone.
  - The client's H.264 profile is the stream's.
  - The picture size is the input surface's.
  - A V4L2 encoder taking dma-bufs reads a surface laid out as it reads in place; others get a copy.
  - FFmpeg 7.1 lists `h264_v4l2m2m` before `h264_vaapi`, and Firefox takes the first, so on `meson`
    it may pick the stock wrapper. A driver cannot change that.
- **VideoProc:** a picture converted to NV12 or P010 on the CPU, at the output's size from the
  source's top left, for a client that shows 8-bit only (mpv's `dmabuf-wayland`, `scale_vaapi`).
  Filters, scaling and rotation are refused: no engine here scales cheaply.

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
| `mpv.*`          | `--hwdec=vaapi-copy`; `--hwdec=vaapi` on a headless `labwc`        |
| `gstreamer.*`    | Debian's `va` elements on every `decode.*` clip and encode         |
| `probe.*`        | `tests/va_probe.c`: Kodi's, VLC's and Chromium's surface calls     |
| `node.*`         | box: `/dev/dri/va` is the GPU's render node, and `renderD128`      |
| `package.*`      | box: the heap open to `video`; the browsers' VA defaults           |

- **Decode** passes on identical frames, or on Y PSNR ≥ 50 dB where the engine's IDCT or a 10-bit
  picture narrowed to 8 bits differs. On a box the engine's interrupts must move. A 10-bit clip
  downloads as P010. GStreamer's frames are judged against the same software decode; it has no
  MPEG-4, H.263 or VC-1 decoder.
- **A size change mid-stream** (`vp9-switch`, `h264-switch`, `hevc-switch`): 360p, 720p, 360p, a key
  frame each, at widths GStreamer writes unpadded. FFmpeg's pictures and GStreamer's, which change
  size as they come, against FFmpeg's software decode, each picture at its own size. A switch is a
  context each in FFmpeg, so its rebuilt headers and mapped controls are not compared.
- **Frame-based HEVC**, as `rkvdec` takes it: one request a picture, its slices as the stateful path
  rebuilds them, each short-term set inline, and an SPS that names none, set as the device's own
  value before buffers, as `rkvdec` sets its pictures up from it.
- **A VP9 key frame of another size in one context**, as GStreamer keeps it: the stateless session
  is closed and opened anew at it, as a new context's is.
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
  odd sizes included; HEVC Main 10 and VP9 profile 2 on `sunxi-h616` and `rk35xx`; VP8; VC-1
  Advanced on `sunxi-h616` and interlaced on `meson-gxl`. HEVC Main 10 and VP9 profile 2 come out of
  `meson-gxl`'s decoder as 8 bits (61, 65 dB).
- **Within 50 dB:** MPEG-2, MPEG-4 and H.263 at 50–74 dB, the engines' IDCT; JPEG 71–77 dB.
- **`meson-gxl` held pictures:** FFmpeg's command line syncs each picture before the next packet;
  with `meson-codecs` `0037` every MPEG-2 and MPEG-4 clip but the interlaced one comes out whole.
- **Clients:** `mpv --hwdec=vaapi-copy` and GStreamer's `va` decoders and encoders on `rk35xx` and
  `sunxi-h616`; `mpv --hwdec=vaapi` through Wayland on `sunxi-h616`, the picture imported by the GPU
  with no copy.
