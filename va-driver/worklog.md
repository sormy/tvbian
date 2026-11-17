# tvb-va-driver worklog

## 2026-11-15: from `research/vaapi` to a package, first runs on boxes

Moved to `va-driver/`, one conf per `BOARD_FAMILY`, built by `./build.sh va-driver <family>` into
`tvb-va-driver-<family>` and planned by the release like the other groups. librga and MPP pinned by
commit. Host check passes throughout. Then the first runs on a box of each family, through
`tools/validate/va_driver.py`.

**All families:**

- Engines were probed by `/sys/module/<driver>`, absent where the driver is built in: Cedrus on
  sunxi64 was. Probed now by `/sys/bus/platform/drivers/<driver>`.
- Sync found its engine through one global, the last decoder opened: two contexts broke it. A
  surface now names the context its picture is due from, cleared when that context closes.
- Suite fixes: mpv takes `--vaapi-device=<node>` as one argument; GStreamer's `va` plugin loads only
  drivers it knows unless `GST_VA_ALL_DRIVERS=1`; `decode.export` dropped, FFmpeg 7.1's CLI cannot
  map VA to DRM for download (`hwmap` stays `vaapi -> vaapi`); no display connected leaves
  `mpv.vaapi` untested, not failed.

**`sunxi-h616` (`tanix-tx1-v2`; `h96max-h313` first):**

- Surfaces' own dma-bufs from the system heap, imported as `V4L2_MEMORY_DMABUF` CAPTURE: the first
  picture decoded, every later one timed out on a `sun50i-iommu` read fault as Cedrus read its
  references. vb2 on 6.18 does not unmap on DQBUF, so not that; `ffmpeg9`'s `v4l2request`, MMAP
  buffers, decoded the same clips bit-exact. Rewritten to MMAP buffers exported, bound late.
- A request that timed out was reused while still queued: `MEDIA_REQUEST_IOC_REINIT` failed `EBUSY`
  and every later one failed with it. Any failed request now restarts both queues.
- VP9: inter frames sent bit depth 0 and no subsampling, which the kernel's frame validation
  refuses; the 10-bit announcement lacked subsampling too.
- JPEG's stateful node has no source-change event; CAPTURE comes up after the first packet.

**`rk35xx` (`r69-1`):**

- The external buffer group held client surfaces + 4 buffers; FFmpeg passes no render targets, so 4.
  Surfaces held all four and MPP refused every packet, the put loop spinning forever. MPP now
  allocates its own; the loop is capped.
- Encode: the RK3528's encoder faulted reading past the input, MPP's preprocessing strides not the
  surface's. Set from the surface on the first frame.
- VP9 profile 2 came out at 8 dB: its NV15 stride, a whole number of pixels, went to the RGA, which
  produced garbage; HEVC Main 10's did not and went to the CPU. NV15 goes to the CPU always.
- `renderD128` is `rockchip-drm`'s on the vendor kernel: the driver is installed as
  `rockchip_drv_video.so`, Lima's name linked to it.
- MPEG-2 and MPEG-4 with matrices decode at 27 and 45 dB through the rebuild, 73 and 68 through
  `ffmpeg9`'s `mpeg2_rkmpp` and `mpeg4_rkmpp` on the original stream. Matched frame by frame, the
  output is both permuted and imperfect. MPP's parser split mode off and MPEG-2 not low delay did
  not fix it. Open.

**`meson-gxl` (`h96max-m20`):**

- The decoder holds pictures 4–6 packets deep, whatever the SPS's reorder depth, and no padding
  changes that. A client's sync on a held picture waited forever: a sync now drains with
  `V4L2_DEC_CMD_STOP`.
- After a drain, `DEC_CMD_START` left CAPTURE returning `EPIPE`: meson's `vdec_decoder_cmd` never
  calls `vb2_clear_last_buffer_dequeued()`. One line fixes it, tested as a swapped module only.
- With that, a drain at the end of a stream works; one mid-stream leaves the decoder unable to go
  on. Decoding H.264, HEVC and MPEG through VA needs a decoder that hands pictures out once decoded.
- A full suite run hung the box off the network, the module still swapped; no log survived.

## 2026-11-15: the ffmpeg9 trace, and meson's held pictures again

Each of ffmpeg9's 42 patches checked against the driver. Taken over: per-engine size refusals (0001,
0031, 0032), headers sent again after a drain or reset (0029), pictures of the old size before a
source change (0013), a VC-1 skipped picture repeating its reference with no request (0002), a
packed B-VOP not sent twice (0023, 0027), H.263 GOB checks and interlaced MPEG-4 refused on Cedrus
(0019), CQP alone on Cedrus's H.264 encoder.

**`meson-gxl`:** a kernel patch taking `V4L2_CID_MPEG_VIDEO_DEC_DISPLAY_DELAY` in place of the
reorder depth, in G12A's H.264 path and HEVC's, set to 0 by the driver: H.264 and HEVC still stopped
at about 21 of 30, a drain at a sync still breaking the decoder. GXLX's H.264 is `codec_h264_ops`,
the microcode's own DPB, not the G12A path; HEVC's hold is not that reorder depth. An access unit
delimiter after each packet, the next start code at once, did not help either. Patch dropped.

## 2026-11-15: meson decodes every codec it has, VC-1 on Cedrus, offers read from the engine

**`meson-gxl` (`h96max-m20`):**

- MJPEG's CAPTURE is three planes (`YUV420M`) whatever is asked: a picture now carries up to three
  planes, interleaved when read. Frames 1–4 of the JPEG clip came out at 71 dB, the 5th not.
- MPEG-1/2/4 and MJPEG lack `V4L2_FMT_FLAG_DYN_RESOLUTION`: the driver subscribed to source changes,
  which succeeds, and waited for one that never comes; the decoder starts only once CAPTURE streams.
  MPEG-2: 0 frames, then 30 of 30 at 69 dB.
- The kernel grants MJPEG 4 CAPTURE buffers and MPEG-4 8, asked for 20 and 24: surfaces held them
  all. Where it grants fewer, each picture is now copied into its surface at once.
- Short 1080p MPEG-4 and MJPEG streams lost their last pictures: `STOP` gave an empty LAST in 1 ms.
  The kernel's `vdec_wait_inactive` takes 50 ms without an interrupt for done, so a drain begun
  after the sync's 1.2 s of waiting ends before the end-of-stream sequence is decoded. A build
  draining at once got MJPEG whole; the driver now drains after 20 ms of quiet. MPEG-4 1080p 3 of 3
  at 72.5 dB, though one cold run still gave 1 of 3. The kernel should start that wait at the
  sequence: todo.
- HEVC Main 10 and VP9 profile 2 come out as 8-bit NV12, as through `ffmpeg9`: now offered, widened
  into P010. Widened at bind time they ran at 7–42 fps; widened only when read, VP9 profile 2 at 185
  fps at 1080p.
- Wrong turn: `cmp.sh` downloaded P010 for any clip named with "10", so SA10143 and SA10091 read as
  0 frames.

**`sunxi-h616` (`h96max-h313`):** a VC-1 slice repeating the picture header (PIC_HEADER_FLAG) goes
to Cedrus without the repeat, its macroblocks from VA's `macroblock_offset`, escaped again, as
`patches/ffmpeg/` `0043`: SA20021 60 of 60 identical to `ffmpeg9`. VA numbers MV modes 1MV,
half-pel, half-pel bilinear; Cedrus takes the bitstream's order, half-pel bilinear first: interlaced
`ilaced_twomv` went from 50 dB luma to identical.

**Offers:** read from the engine, not a table per family. V4L2: `ENUM_FMT`, the profile menu,
`ENUM_FRAMESIZES` (meson) or `TRY_FMT`'s clamp (Cedrus). MPP: its SoC table, linked statically. What
changed against the old tables: meson encodes H.264 Main alone, its menu's last item; Cedrus's clamp
gives HEVC Main 10 and VP9 profile 2 8192×4320 (table 6144×3456), VC-1 4096×2304 (1920×1088); MPP's
RK3528 encoder is 1080p (table up to 8192), its 8K class 8192×4320 (table 8192×8192).

**Cedrus's limits, measured by `tvbian`:** 8-bit HEVC and VP9 decode at 8192×4320, the clamp; 10-bit
stops at 6144×3456, checked when the SPS or VP9 frame control is validated, which `TRY_FMT` cannot
see. The driver now searches each side with `VIDIOC_TRY_EXT_CTRLS` on a context it opens for it, the
codec's format set first: a context set to another codec takes any header, and VP9's needs its
subsampling flags or the core refuses every size. HEVC Main 10 and VP9 profile 2: 6144×3456, a
640×360 clip of each still identical. After `linux-sunxi` `0814` all six FATE VC-1 clips decode
identical through VA-API on `h96max-h313`.

**`meson-gxl`, from `tvbian` on a built 6.18.63:** `meson-codecs` `0033` ends the `EPIPE`, but the
microcode's session is over after a drain's end code: pictures sent after `V4L2_DEC_CMD_START` come
out missing or late. A sync's drain now closes the session and opens another, its headers sent
again, so the driver needs neither `0033` nor `START`. Untested on the box yet.

**`meson-gxl` on 6.18.63 with `0033` and `0034`, the session reopened after each drain:** H.264,
HEVC and VP9 bit-exact, MPEG-2 and MPEG-4 SP by hand 30 of 30 at 69.2 and 68.6 dB, repeatable. In
the suite, back to back, MPEG-2's second decode gave no frames, MPEG-4 SP once 30 dB, VC-1 timed
out: open. H.264 encode had gone with detection, the encoder's menu ending at Main and FFmpeg asking
High first; High is offered on Main again, 30 frames out.

**`sunxi-h616` (`tanix-tx1-v2`, 6.18.63 with `linux-sunxi` `0814`):** the suite exits 0, every VC-1
Advanced clip identical; offers as detected. mpv and GStreamer not installed this run.

**`meson-gxl` on 6.18.63 with `0033`–`0036`:** HEVC and VP9 at 642×362 bit-exact, VC-1 AP interlaced
13 of 13, H.264 and HEVC encode pass. A skipped VC-1 picture still goes to the decoder, for the B
pictures predicting from it, and the surface gets its reference's picture copied at sync, on meson
alone: copied on the host's libavcodec too it gave 22 dB, unexplained.

The suite's MPEG-2 "flakes" are one fault: its PSNR pass decodes beside a software input, which
throttles the VA decode, so FFmpeg syncs a picture before sending the next packet. The MPEG
microcode holds a picture until the next start code; the drain that frees it ends the session, and a
session opened after has no references: 15.8 dB in 4 of 5 runs. The sync's patience counted its own
sleeps only, so each drain's 1 s wait stretched it to about 200 s; it is on the clock now. The fix
is a picture handed out without the next packet, in the kernel.

**`meson-gxl`, the held pictures settled:** `tvbian` found no start code that frees a held MPEG or
VC-1 picture without ending the session; MPEG-4 holds two. FFmpeg's command line syncs each picture
before sending the next, so with MPEG-4 every picture drained, and each new session lacked
references: 1 of 30 once the driver refused predicted pictures; the earlier 30 of 30 runs were
FFmpeg queueing ahead by chance. The owner chose: keep offering them, refuse predicted pictures
after a mid-stream drain until an intra one. The suite checks those cases by timestamp, every
picture out against software's at the same pts.

The owner asked for a switch: `VAAPI_HELD_PICTURES` or `held-pictures` in `/etc/tvb-va-driver.conf`,
`refuse` (default), `off` or `decoded`, read by the stateful backend. Not a kernel parameter: the
kernel serves `ffmpeg9`'s decoders too, which feed ahead and decode these codecs right.

**`meson-gxl`, the suite with the held-pictures check:** MPEG-2 30 of 30 out in all three clips,
every one right; MPEG-4 1 of 30, the rest refused after a drain per picture, as FFmpeg's command
line syncs each; H.264 encode with CBR passes. The skipped-picture copy put a wrong picture out in
`vc1-ap`, as it had on the host: removed, and `vc1-ap` came out 6 of 60, every one right.
`vc1-ap-slices` still lets one wrong picture through after a drain (17 dB): open.

**`meson-gxl` H.264's hold, from `tvbian`:** 3 of 12 pictures held for Baseline, 6 of 12 for High,
500 ms after the last packet. The microcode's reorder depth (`AV_SCRATCH_0` bits 8–15) at 0 frees at
most one more and breaks High and multi-reference clips; even at 0 two stay. VA does not give the
stream's reorder depth, so the driver cannot set it either: the hold is the microcode's design.

**`ffmpeg9` with VA-API and `patches/ffmpeg/` `0044` on `h96max-m20`:** `-hwaccel_output_delay N`
holds N frames back before they are downloaded. H.264 High 4 of 30 and wrong at 0, 30 of 30
bit-exact from 1; HEVC Main 6 dB at 0, bit-exact from 1; 1080p MPEG-4 3 of 3 from 1; MPEG-4 with
matrices 30 of 30 at 63 dB at 4. The 640×360 MPEG-2 and MPEG-4 clips lose their last 2 pictures at
every N, a sync failing at the end of the stream, where Debian's FFmpeg 7.1 gave MPEG-2 30 of 30:
open.

The display nodes' names, `meson` and `sun4i-drm`, are dropped from the packages: `vainfo` opened
the driver through `meson` on `h96max-m20`, mpv's DRM output still did not, so they served nothing.
The render nodes' names stay: `panfrost`, `lima`, and `rockchip` where the display holds
`renderD128`.

**Nothing per engine without a reason:** the backend is the first whose probe finds offers, not the
one whose kernel driver name exists; Cedrus's 24 Mpixel JPEG cap is read from `TRY_FMT`, which
`linux-sunxi` `0803` makes trim by area (6000×4000 and 4000×6000 decode, 6000×6000 refused, on
`h96max-h313`); encode rate controls are the bitrate menu's. Meson's encoders list VBR alone: the
CBR that passed there was the kernel encoding VBR. Kept, each for a reason the engine cannot be
asked: MPP's interlaced MPEG refusal, Cedrus's interlaced MPEG-4, meson's scaled codecs, MPP's size
classes, the 20 ms a sync waits before taking a picture for held.

**Every box on its current kernel** (`h96max-m20` and `tanix-tx1-v2` on 6.18.63 from `main`, `r69-1`
on 6.12.69): `rk35xx` and `sunxi-h616` pass the suite whole, Cedrus's H.264 encoder taking the
bitrate menu's VBR and CBR, GStreamer's `va` elements passing. `meson-gxl` with `meson-codecs`
`0037`: every MPEG-4 clip but the interlaced one 30 of 30 through FFmpeg's command line, 1 of 30
before; HEVC and VP9 at 642×362 identical. Interlaced MPEG-4 at 38.7 dB and one wrong picture in
`vc1-ap-slices` remain.

## 2026-11-16: Cedrus decodes into the surfaces' memory

`h96max-h313` (H616, 6.18.63): GStreamer's `vah264dec` decoded 1080p at 18–22 fps with one thread
near 85%, 79–89% of the samples `__memcpy_generic` in `surface_bind_picture`'s copy. GStreamer
exports every surface at pool setup, or derives it for a crop copy, so every surface had memory of
its own and every picture was copied in, read from Cedrus's write-combined buffer.

**Surfaces' dma-bufs as `V4L2_MEMORY_DMABUF` CAPTURE, again:** the first picture already faulted,
`sun50i-iommu` read fault at row 13 of the picture (640×368 at 0x2080): Cedrus's deblocking reads
back what it wrote. vb2 maps an imported CAPTURE buffer `DMA_FROM_DEVICE` unless the driver sets
`vb2_queue.bidirectional`, Cedrus does not, and the IOMMU maps it write-only. The CMA heap faulted
the same. `V4L2_MEMORY_FLAG_NON_COHERENT` MMAP buffers are allocated for the same direction, so not
those either. The worklog's reference faults of 2026-11-15 were this, not the references.

**Done instead:** the other way round. Each surface decoded into gets a CAPTURE buffer of its own
for the context's life, and a surface with no memory of its own takes that buffer's export as its
memory: at its first picture, or at the export or derive GStreamer does first, from a decode context
of its size and format. Pictures decode in place; references are vb2's timestamps on the surface's
buffer, which is queued again only when its surface is decoded into. A surface with memory of its
own (Chromium's import) or another layout (an 8-bit surface of a 10-bit stream), and AFBC, keep the
bound picture and copy.

Throughput, 288 frames each, `sync=false`, old → new:

| Clip            | DMABuf export (WebKit's) | VAMemory  | system memory |
| --------------- | ------------------------ | --------- | ------------- |
| H.264 1080p     | 22.7 → 95.5 fps          | 96 → 95   | 21.4 → 23.8   |
| H.264 4K        | 5.9 → 24.8               | 25 → 25   | 25 → 25       |
| VP9 4K          | 6.2 → 34.5               | 34 → 34   | 35 → 35       |
| HEVC 1080p      | 25.2 → 140               | 142 → 140 | 23.5 → 26.0   |
| HEVC 4K         | 6.6 → 48.9               | 49 → 49   | 49 → 50       |
| HEVC Main 10 4K | 3.3 → 28.0               | 28 → 28   | 28 → 28       |

CPU on the export path from 78–91% to 12–56%. System memory at 1080p stays CPU-bound: GStreamer
crops 1088 to 1080 for a sink without crop meta, `gst_video_frame_copy` reading Cedrus's uncached
memory; no copy is the driver's.

**WebKit, sandbox on:** the earlier attempt played nothing because the old driver's surface memory
for GStreamer's export came from `/dev/dma_heap/system`, which is root's alone and absent from
WebKit's bubblewrap sandbox: a memfd, which is no dma-buf, and the web process died at the pool's
setup. The lent buffers need no heap: 1080p H.264 and 4K VP9 play at 24 fps. 4K H.264 cannot keep
real time on Cedrus whatever the driver: about 25 fps flat out, 180 of 288 frames late through
`gst-launch` with the old driver as with the new.

## 2026-11-16 — one build, GStreamer as a client, speed

- GStreamer's `va` elements as a second client on every clip: VP8 failed `vaRenderPicture` with
  invalid parameter, GStreamer sizing the slice as the whole frame and offsetting it past the frame
  header; the slice is now what the buffer holds past its offset. 10-bit failed negotiation:
  GStreamer takes only a 10-bit format for a 10-bit stream, `rk35xx` lists NV12;
  `patches/gst-plugins-bad` `0001` lets it narrow. Wrong turn: MPEG-2 read 23 dB until `psnr` paired
  pictures by one timebase; MBAFF read 1 frame until raw frames replaced `y4menc`'s, which tags each
  interlaced frame.
- Refusals judged by pictures out, not the engine's interrupts: other work on a shared box moved
  them, and `mpeg4-interlaced` read "not refused" twice.
- Speed: 4K clips of 600 frames, the best of three, start-up taken off by a one-picture run. 120
  frames and one run gave FFmpeg HEVC 160 fps, then 48, on the same driver.
- One build: every backend, libmpp linked in, the driver under `lima`, `panfrost`, `panthor`,
  `etnaviv`, `v3d` and `msm`. Devices listed from `/sys`, the numbered nodes the fallback. Cedrus's
  AFBC kept where CAPTURE lists it and the client listed the modifier, in place of
  `gpu_is_panfrost()` and HEVC and VP9 by name; the stateless backend is `v4l2-request`.

## 2026-11-17 — `meson-gxl` on the single driver

- The single driver offered no H.264, HEVC or VP9 on the M20: `v4l2-request` went first and took the
  box on meson's stateful nodes alone, its MJPEG decoder and H.264 encoder. It now takes a box only
  with a stateless decoder; the M20 gets `v4l2m2m` and its 13 decode profiles, the H313 and the M2
  Plus their backends as before.
- `meson-gxl` HEVC ran at a quarter of `ffmpeg9`'s own `v4l2m2m`: tracing the decoder's interrupts
  showed it idle 200 ms at a time, 12 s of a 16 s run, with every input slot queued and its CAPTURE
  buffers free. `vaEndPicture`, waiting for a free OUTPUT buffer, polled on after one freed until a
  picture came or the 200 ms ran out, and the decoder makes none without the next packet. It now
  returns once one frees: HEVC 1080p 38 to 149 fps, HEVC 4K 19 to 34, against `ffmpeg9`'s 156 and
  32; the suite fails nothing it did not before.

## 2026-11-17 — mainline `rkvdec`, and what the desktop shows

- The M20 checked at 4K on 7.3.5 gave VA pictures unlike software's, every codec, and as many on
  6.18.64 and on the committed backend; `ffmpeg9`'s own decoders were exact, and the suite's short
  clips passed. Two faults. A sync drained the decoder 40 ms into a session, as the 20 ms quiet was
  counted from before the 80 ms CAPTURE setup, and the pictures after the drain lost their
  references: the quiet now starts with CAPTURE, and scales with the picture, as a 4K one takes
  longer than 20 ms; without the scaling 4K failed again. And a hidden VP9 frame, its own packet
  once FFmpeg splits the superframe, took a CAPTURE buffer as a picture: the decoder dropped the
  next shown one, every 12 frames. It now goes out with the next in one superframe; a show-existing
  header after it instead stopped the decode. Six clips, H.264, HEVC and VP9 at 1080p and 4K, four
  runs each: every picture exact.
