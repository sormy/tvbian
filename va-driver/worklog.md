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

- The M2 Plus on `rk35xx-next2`: the stateless backend handled single-planar nodes alone, and
  `rkvdec` is multi-planar; it now takes either, the node with the largest size. H.264 P frames
  still broke. An ioctl trace beside `ffmpeg9`'s own request path found it: `rkvdec` lays its
  pictures out from the device's current SPS, and refuses a new one with `EBUSY` while it has
  buffers, streaming or not. The SPS is now set before a picture's buffer is chosen, the session
  rebuilt once if refused. H.264 and VP9, 1080p and 4K, decode bit-exact at 91 to 98% of `ffmpeg9`'s
  rate; Cedrus decodes as before.
- The desktop check on the M2 Plus dropped frames at 4K60 in mpv: H.264 270 of 600, HEVC 54, VP9
  363, and as many on the real 2256x1504 screen. Not the driver: MPP decodes the 25 Mbit/s H.264
  clip at 43 fps natively, VA at 42; HEVC and VP9 reach 88 and 71 fps through VA, mpv 46 untimed
  with the Mali-450 at 95% load and its top clock, whatever mpv's pool or output.
- The M20's CAPTURE budget is 288 MiB, two dozen 4K pictures, as the kernel now grants what CMA
  holds; 192 MiB left 4K at the decoder's minimum, copying every picture.
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
- On the H313 as a desktop user, mpv showed no 4K clip: `/dev/dma_heap/system` is root's, so a
  surface's own memory fell back to a memfd, which is no dma-buf, and the compositor refused it. The
  suite runs as root. The package's udev rule opens the heap to `video`; both 4K clips now play to
  their end.
- `rk35xx` VP9 1080p ran at 185 fps against MPP's 349: MPP pads a VP9 row to an odd multiple of 256
  bytes, so no picture landed in a surface's memory and each was copied. Memory laid out again as
  MPP decodes reached 336, but broke GStreamer's odd-size H.264, then its VP9 at 9 dB: GStreamer
  exports one surface at the start and takes its layout for every surface's, so a surface derived
  and let go was not enough to keep. Re-laid now for VP9 alone, and never once a surface was
  exported; FFmpeg only derives one to test. VP9 1080p 326 fps, the suite as before.
- `vp9-switch` lost the last picture before each size change through FFmpeg on `rk35xx`: FFmpeg
  closes the context at a change, and the MPP decoder went with that picture still in it, so its
  sync failed. A context now drains every picture its surfaces wait for before it closes. The suite
  gained `h264-switch` and `hevc-switch`, as a site's player switches on every codec; all three
  decode 90 of 90 identical on `rk35xx` and `sunxi-h616`.
- A browser switches size on every codec, so the suite gained `h264-switch` and `hevc-switch`, and
  every switch clip went to 360p, 720p, 360p: at 854 wide GStreamer pads its rows, and its checksums
  could not meet FFmpeg's. FFmpeg scales every picture to the first one's size unless told
  `-noautoscale`, so 30 frames read as wrong on every codec. Through GStreamer on `sunxi-h616`, VP9
  back down to 360p came out as garbage or stopped: GStreamer keeps one context through a VP9 size
  change, and the session set up again in place broke on the way down. It is now closed and opened
  anew, as a new context's is: all three switch clips 90 of 90 identical through FFmpeg and
  GStreamer, three runs each.
- GStreamer's JPEG on `sunxi-h616` read 28.7 dB, and FFmpeg's pictures through the driver were the
  same bytes: the suite read GStreamer's raw frames as limited range against a full-range JPEG. Read
  as full range, 77 dB, as FFmpeg's.
- FFmpeg through the driver on `sunxi-h616` fell to 55% of the engine's rate, 1080p and 4K alike,
  with twice the CPU; GStreamer kept its rate. Not heat and not the kernel: 6.18.63 and 6.18.64 both
  read 16.3 s, cool. FFmpeg derives one surface's image at start, to see whether it can, and a
  surface derived once had become seen for good, so that one kept its own memory and each picture
  decoded into it was copied. A surface is seen again while its derived images are open; GStreamer
  keeps the layout of an export, which the driver-wide flag covers. HEVC 1080p 127 to 173 fps,
  `rk35xx` VP9 1080p still 335.
- On `rk35xx`, GStreamer's VP9 switch gave 65 of 90 pictures: it keeps one context through a size
  change, and MPP's own resize lost some on the way. A VP9 key frame of another size now gets a
  decoder anew, as the stateless backend's does: all three switch clips 90 of 90 identical through
  FFmpeg and GStreamer.

- GStreamer through the driver on `meson-gxl` stalled after 9 to 131 of 600 pictures: GStreamer
  syncs a picture before sending the next packet, and meson's decoder hands one out only after later
  packets, so the driver drains, and a drain ends meson's session and its references. The microcode
  has no low-latency mode. GStreamer's own `v4l2h264dec`, `v4l2h265dec` and `v4l2vp9dec` decode all
  600, so the package's generator no longer tells GStreamer to load the driver where the meson
  decoder is.
- `sunxi-h616` VP9 ran at 71% of the engine's rate at 1080p and 81% at 4K, a fixed cost a picture,
  with 1.9 ms more kernel time a frame than `ffmpeg9`'s own path. Counting the syscalls through an
  `LD_PRELOAD` shim found it: fewer ioctls than FFmpeg's own, but an `mmap` and `munmap` a frame,
  each surface's memory mapped whole as an engine buffer was lent to it, which no client read. A
  surface's memory is now mapped on first use: VP9 1080p 98%, 4K 100%, HEVC 1080p 100% of
  `ffmpeg9`'s rate.
- `rk35xx` offered no JPEG. MPP's JPEG decoder runs only through its task API: an output buffer
  handed with each packet, and the packet itself in an MPP buffer; plain memory failed every picture
  with "check buffer found NULL pointer". The suite's engine count missed `jpegd`'s interrupt. JPEG
  now decodes through VA at 76 dB, FFmpeg and GStreamer, and 1080p MJPEG at 145 fps against
  software's 61 on four threads.
- `rk35xx` JPEG encode through MPP's JPEG encoder, offered on `VAEntrypointEncPicture` beside the
  slice encoders: 40 dB at the default quality, H.264 and HEVC encodes unchanged. GStreamer's
  `vajpegenc` does not preroll here either, as on `sunxi-h616`.
- GStreamer's `vajpegenc` never prerolled, on `sunxi-h616` and `rk35xx` alike: it reads
  `VAConfigAttribEncJPEG` for how many Huffman tables it may send, and the driver answered nothing.
  It now reports baseline JPEG as its writer makes it, three components in one scan, two of each
  table: GStreamer's JPEG encode 36 dB on `rk35xx`, 39 dB on `sunxi-h616`.

- HEVC on `rk35xx-next2`: `rkvdec` decodes a frame at a time and parses each slice header itself,
  reading the SPS's short-term sets from controls VA has nothing to fill. The stateful path's
  rebuild already writes each set inline against an SPS that names none, so `rkvdec` takes those
  slices, parameter sets left out, as FFmpeg's own path sends them. Every picture failed until the
  SPS was set as the device's own value before buffers, as with H.264. The suite's engine count
  missed mainline's `video-codec` interrupts. HEVC 1080p 97%, 4K 99 to 100% of `ffmpeg9`'s rate;
  every HEVC, H.264 and VP9 clip identical.
- JPEG on `rk35xx-next2`: `rockchip-jpegd` lists its coded format as `JPEG`, Cedrus's as `MJPG`, and
  the driver looked for `MJPG` alone. Either is taken now, and a profile two candidates match is
  offered once: 76 dB, 1080p MJPEG at 280 fps; the H313's and M20's offers unchanged.
- HEVC Main 10 on `rk35xx-next2`: `rkvdec` writes NV15, and lists it only once the device's SPS says
  10 bits, so the probe tells it first, and CAPTURE takes NV15 where P010 is not listed; the picture
  is unpacked by the CPU when read. Main 10 identical; Cedrus's P010 as before. Every decoder the
  RK3528 has now runs through the driver on mainline.
- GStreamer into system memory on `sunxi-h616` ran 1080p60 at 28 fps, `va` and GStreamer's own
  `v4l2sl` decoders alike, 33 ms of CPU a frame: Cedrus's pictures were uncached, and each was read
  out by the CPU. Its CAPTURE queue takes cache hints, so its buffers are now asked for
  non-coherent, with V4L2's own cache upkeep skipped as a CPU read syncs the dma-buf: H.264 130 fps,
  VP9 112; FFmpeg on the GPU path as before, the suite unchanged.
- WebKit's WebRTC encodes through `vah264enc` alone. Its settings, CBR, `target-usage=1`, a GOP, no
  B frames, AVC out of `h264parse`, hold on every family: key frames exactly at `key-int-max` 15 and
  60, no B frames. CBR holds within 10% a second on `rk35xx`; `sunxi-h616` overshoots its first
  second 2.7 times; `meson-gxl` offers no CBR. A key frame asked for mid-stream, as on a peer's PLI,
  came at once, but Cedrus-enc kept its own GOP count beside the client's, giving extra key frames
  on the old cadence: the V4L2 encoders now take the longest GOP the device allows, and every IDR
  the client marks is forced.
- GStreamer finds the `va` encoders on `meson-gxl` too: the generator loads the driver everywhere
  and ranks only the `va` decoders out there.
- GStreamer into system memory through MPP runs at 45% of its rate in `VAMemory`: GStreamer's own
  copy of each frame, for a sink taking no `GstVideoMeta`; WebKit takes it.
- GStreamer's VP9 through MPP ran 1080p at 138 fps, 60% of it in the driver's copy: GStreamer
  exports its surfaces before the first picture, so they kept the plain layout and MPP's padded rows
  could not land in them. A surface made after a VP9 decode config, as FFmpeg and GStreamer make
  theirs, is now laid out as MPP writes VP9 from the start, the rule read from MPP at five sizes:
  GStreamer 264 fps, FFmpeg 283; 4K, whose rows MPP does not pad, as before. Every VP9 clip
  identical through both, switch clips included.
- A call in the browsers, on `sunxi-h616`: GStreamer ranks its `va` encoders out, so WebKit picked
  `openh264enc`; the generator ranks them first now, and WebKit builds `vah264enc`. Chromium 156
  takes the encoder with `AcceleratedVideoEncoder`: its VA encoder initializes and encodes at 360p
  and 540p, but the call's canvas gives it 3.5 fps, WebRTC drops below 360p, and Chromium encodes
  that in software. Firefox ESR 153 has no VA encoder: its FFmpeg encoder opens `libx264`, so its
  encode prefs are not shipped.
- WebKit's call on `sunxi-h616` failed `not-negotiated`: it asks for Constrained Baseline, and
  Cedrus-enc wrote Main, its default, as the V4L2 encoders never set the profile control. The
  client's profile is set now: the stream says Constrained Baseline, Main or Main for High, as
  asked; the suite's encodes unchanged. `meson-gxl`'s encoder lists no Constrained Baseline.
- MJPEG through MPP spent half its time copying each picture out of MPP's buffer into the surface. A
  surface made after a JPEG config is now laid out as `jpegd` writes NV12, and decoded into in
  place: FFmpeg 1080p from 154 to 189 fps, a third of the CPU; GStreamer as before, at 134; JPEG
  still 76 dB through both.
- 10-bit through MPP ran at half its native rate, every picture narrowed from NV15 to NV12 by the
  CPU a sample at a time, staged at 16 bits: MPP's HEVC decoder takes its pixel format from the
  stream alone, so the engine cannot narrow it. Four 8-bit samples now come straight from each
  five-byte group: HEVC Main 10 1080p from 152 to 225 fps, 4K from 36 to 69 against MPP's 79; the
  10-bit clips as before, through FFmpeg and GStreamer. `tests/unit/test_pixels.c` checks the
  narrowing against the packed samples.
- The narrowing split across two cores, the luma's top half on a helper thread: HEVC Main 10 1080p
  from 228 to 258 fps, 86% of MPP's rate; 4K 70 fps, as before, bound elsewhere.

- `meson-gxl`'s suite with the cached-capture, GOP and profile changes: 52 pass as before. Two
  checks flip run to run on either build, `mpeg4-sp` and GStreamer's `hevc-odd`.
- `rk35xx` against `ffmpeg9`'s MPP decoders, the current build: H.264 98%, VP9 96 to 97%, HEVC 92 to
  94%, HEVC Main 10 86 to 88%. HEVC's remainder is the stream parsed twice, by FFmpeg for VA and by
  MPP again; no copy of the driver's stands out.
- `meson-gxl` against `ffmpeg9`'s V4L2 decoders, frames left on the GPU: H.264 1080p 100%, HEVC
  1080p 134%, VP9 1080p 92%, 4K 99%. Read back, 4K H.264 and HEVC stop after 1 and 9 pictures, on
  today's builds and the installed one alike: FFmpeg syncs a picture meson's DPB still holds, and
  the drain ends the session.
- The V4L2 encoders copied each input picture into their own buffer. Where the device takes dma-bufs
  on a single-plane OUTPUT, as Cedrus-enc behind the IOMMU does, a surface laid out as it reads now
  goes in as it is, and one laid out otherwise is copied into memory of ours. Cedrus-enc asks a row
  past the picture, which the heap's whole pages hold, so a surface's memory is now counted as those
  pages. 720p `vah264enc` on `sunxi-h616`: 8% less CPU, 52 to 55 fps; the encodes byte for byte as
  before, the suite unchanged.
- The narrowing on four cores, a band each: HEVC Main 10 1080p 253 fps against two cores' 246, 4K 69
  as before. Bound by memory, not the cores: two kept.
- `rk35xx-next2`'s candidate with the VOP IOMMU on: H.264 98 to 99%, HEVC 97 to 99%, VP9 98 to 100%,
  HEVC Main 10 93% at 1080p and 100% at 4K, of `ffmpeg9`'s `v4l2request` rate. The kernel adds
  `rockchip,rk3528-vpu-dec`, so VP8, MPEG-2, MPEG-4 and H.263 are offered; MPEG-4 and H.263 give no
  picture through the driver and leave the VPU stalled
  (`rk_iommu ... Enable stall request timed out`), VP8 and MPEG-2 dead after them through
  `ffmpeg9`'s own path too, which decodes MPEG-4 on a fresh boot. No `/dev/dma_heap/system`.
  GStreamer's `vp9-switch` differs from the first size change on.
- MPEG-4 on `rk3528-vpu-dec` hung the VPU: `linux-sunxi` `0805`'s VOP control gained the VOL's
  `vop_time_increment_resolution` and the latest reference's coding type in its reserved bytes, and
  the driver's copy of the header still sent zeros. VDPU2 parses video packet headers by that
  resolution; Cedrus ignores both. The driver fills them now; the host's checks pass.
- On a clean boot of the next build, MPEG-4 through the driver with the resolution filled still
  stalls `rk3528-vpu-dec` at its first picture (`rk_iommu ... Disable paging request timed out`),
  and the VPU stays dead after; interlaced MPEG-2 alone is refused. VP8 and progressive MPEG-2
  decode identical before it, through FFmpeg and GStreamer. Something else in the request differs
  from `ffmpeg9`'s own.
- The RGA for the 10-bit narrowing, dropped untried: RGA2-enhance reads NV15, but librga upstream
  ships binaries alone, and nothing shows RGA2 beats two cores where memory already bounds 4K. The
  narrowing in NEON instead, 16 samples a step from four groups by one table lookup and two per-lane
  shifts; `tests/unit/test_pixels.c` covers rows long enough for several steps.
- The MPEG-4 stall on `rk3528-vpu-dec` was the zero resolution alone: on a clean boot every MPEG-4
  and H.263 clip decodes at 68 to 73 dB, VP8 and MPEG-2 after them. Hantro holds CAPTURE across
  requests, so it gets the per-packet requests Cedrus does; a queue that does not advertise
  `V4L2_BUF_CAP_SUPPORTS_M2M_HOLD_CAPTURE_BUF` gets the whole VOP in one request, and no request is
  marked to hold where the queue cannot.
- A 10-bit readback on `rk35xx-next2` ran at 3 fps: the CAPTURE memory is uncached, and the
  narrowing's overlapping loads read it several times over. Each row is copied whole into cached
  memory first: 1080p 38 fps, 4K 10.5, an 8-bit readback 42 fps for the same uncached reason.
- `rk35xx-next2` with Hantro beside `rkvdec`: GStreamer names a second node's stateless decoders for
  the node, `v4l2slvideo6h264dec`, which the generator did not rank out, so WebKit took it over
  `vah264dec`. The generator now ranks out every node's. HEVC through `vah265dec` outside WebKit:
  1080p 298 fps, the suite exact; FFmpeg 97% of `ffmpeg9`'s own.
- H.264 and HEVC in WebKit on `rk35xx-next2` decoded at 3 to 9 a second, VP9 at full rate.
  GStreamer's DMABuf path names no render targets and exports every surface first, each lent a
  CAPTURE buffer; at the first picture `rkvdec` refused the SPS with buffers allocated, the session
  was set up again, and the exported surfaces kept the freed buffers' memory, so each picture was
  copied, uncached. The stream's size and depth are now the device's SPS before its buffers, for
  H.264 and HEVC at any depth: GStreamer into DMABuf H.264 1080p 47 to 342 fps, HEVC 46 to 344, 4K
  93; every H.264 and HEVC clip identical.
- Falkon on `rk35xx-next2` with the SPS set before buffers: H.264 files at the clip's rate at
  1080p60, 4K30 and 4K60, HEVC at 4K30 and 4K60, from 0.9 times at best. One HEVC 1080p60 run
  decoded nothing.
- GStreamer's `vp9-switch` on `rk35xx-next2`: luma is identical in every picture, chroma wrong from
  the first size change on. In GStreamer's 720p NV12 the right chroma sits at row 768, `rkvdec`'s
  64-aligned height, where 720 is read; the buffer is the size of a surface's own memory at the
  plain layout. CAPTURE reports 1280x768 on a reopen as on a fresh open, so the stale offset is the
  surface's, not the session's.
- GStreamer's `vp9-switch` on `rk35xx-next2`: GStreamer reads one fresh surface's layout at each new
  size and takes it for all, before the decoder reopens there, and `rkvdec` writes 720p at 768 rows.
  A new surface is now laid out as the decoder writes its size, asked of the device on a handle of
  its own with OUTPUT at that size (`TRY_FMT`), once a profile and size: all three switch clips 90
  of 90 identical through FFmpeg and GStreamer, DMABuf decode at full rate.
- The NEON narrowing on `rk35xx`'s vendor kernel, on the R69-1: HEVC Main 10 1080p 274 fps against
  MPP's 312 (88%), 4K 72 against 81 (89%), two points over the C loop's on the M2 Plus: memory
  bounds it there; it earns its place on `next2`'s readback. GStreamer's HEVC 1080p60 into DMABuf on
  `next2`, 20 runs: every one whole in 3.5 s, no kernel line.

## 2026-11-19 — the GPU's alignment, and mpv on Wayland

- YouTube in Falkon on `sunxi-h616` failed at its small sizes: Panfrost logged "rejecting image due
  to unsupported offset or stride alignment" for each picture. Cedrus pads an NV12 row to 32 bytes,
  854 wide to 864, and Panfrost imports a linear plane only at whole 64 bytes; the decoder's buffer
  was lent, planned and exported at its own pitch. It now is only where pitch and plane offsets are
  64-byte aligned; elsewhere the surface keeps its own aligned memory and gets each picture copied
  in. mpv on a headless `labwc`, VP9 854x480, 426x240 and 642x362, H.264 854x480: 61 pictures
  refused before, none now.
- `mpv --hwdec=vaapi` failed in every suite run: its DRM output finds "no primary DRM device" where
  the display and the GPU are two devices, as on the H313; the driver was never reached. Through
  Wayland, as on the desktop, H.264, VP9 and HEVC decode through VA and import with no copy. The
  suite's `mpv.vaapi` now plays the odd-size clip on a headless `labwc` and fails on a refused
  picture.
- An FFmpeg on an RK3518 had sat two days in a futex decoding VP9 through MPP, every thread asleep.
  Three waits on MPP had no bound: the loops taking whatever MPP hands out in decode and sync, which
  a size change MPP announced again and again would keep in MPP's own waits, and both polls of the
  JPEG task API. Each is bounded now, 64 takes a call and 2 s a JPEG, and fails rather than waits.
  The hang's own cause is not known. The R69-1's suite passes as before but for GStreamer's 10-bit
  clips, which need `gst-plugins-bad`'s `0001`, not installed there.
- `rk35xx-next2` with cache hints on `rkvdec`'s and Hantro's CAPTURE and `vb2-dma-contig` syncing a
  non-coherent buffer, on the 3518D: the driver's non-coherent CAPTURE takes effect unchanged.
  Readback: HEVC 1080p 42 to 91 fps, 4K 25, HEVC Main 10 1080p 38 to 73, 4K 10.5 to 22; every clip
  right through FFmpeg and GStreamer. H.264 MBAFF was wrong first, the kernel compressing collocated
  motion vectors on a stream with field macroblocks, and identical once fixed. Interlaced MPEG-2
  decodes on Hantro, 73 dB, where the suite expected every `rk35xx` to refuse it as MPP does: a clip
  `REFUSED` lists now passes refused or right.
- Firefox ESR 153 on the H313, `browser.py`, 1080p60: with its decoder sandbox on, the engine's
  interrupts never move and every clip decodes on the CPU; with `MOZ_DISABLE_RDD_SANDBOX=1` FFmpeg
  asks for `VAAPI_VLD` and decodes about 60 a second, H.264, HEVC and VP9. Shown, 3 to 8 a second
  either way: Firefox's drawing, not decode. The generator now sets the variable where the engine is
  MPP or `cedrus`, `rkvdec` or `hantro-vpu`; on the M20 it stays unset. `MOZ_ENABLE_WAYLAND` is not
  needed: ESR 153 takes Wayland by itself. Only the H313's GPU runs Firefox here; `lima` lacks
  GLES 3.
- mpv on the M2 Plus's own screen, `rk35xx-next2`, in labwc on HDMI, flips counted by
  `drm_vblank_event_delivered` over 10 s, 1080p60 clips. `--vo=dmabuf-wayland` with the output at
  1920x1080: H.264, HEVC and VP9 600 flips, 0 dropped, the decoded NV12 on the primary plane, no GPU
  and no copy. At the panel's 2256x1504 the picture is scaled, labwc draws it on the Mali-450 and
  flips 30 a second. `--vo=gpu`: `lima` refuses the import (`EGL_BAD_ALLOC`), mpv decodes on the CPU
  and drops 654 of 958. HEVC Main 10 does not play: the P010 surface goes to `scale_vaapi` for NV12,
  and the driver has no `VideoProc`.
- `VideoProc`, `src/vpp.c`: NV12 or P010 into the output surface's format at its size, on the CPU; a
  source region at the top left is taken, as FFmpeg's HEVC surfaces are taller than the picture. The
  suite's `vpp.*` turns HEVC Main 10 and VP9 profile 2 to NV12 by `scale_vaapi`: 53.7 and 58.8 dB on
  the host, HEVC Main 10 53.7 on the M2 Plus. mpv `--vo=dmabuf-wayland` on the M2 Plus, output
  1920x1080, HEVC Main 10 at 30 fps: 301 flips in 10 s, VA decode, mpv at 39% of a core. A first try
  narrowed rkvdec's 10-bit to NV12 surfaces instead; its box runs used an old package, so they
  showed nothing, and the conversion serves every client that asks, so it went.
- MPP no longer narrows 10-bit on its own (`narrows_ten_bit` gone): every 10-bit config lists P010
  first and NV12 second, a P010 surface exports MPP's NV15 as it is, and a client that shows 8-bit
  only asks `VideoProc`. The R69-1, vendor 6.12: 83 pass, 76 before. HEVC Main 10 and VP9 profile 2
  30 of 30 identical, 56 and 61 dB narrowed; `vpp.*` 53.7 and 58.8 dB; GStreamer's own
  `gst-plugins-bad`, without `0001`, decodes both at 63 dB, where it failed with NV12 alone. WebKit
  taking P010 from MPP is not tested: no WebKit browser on the R69-1.
- `pixels.c` narrows P010 by NEON (`vld2q_u8`, the high bytes) on two cores, as it does NV15, and
  unpacks NV15 to P010 by NEON, two groups a step through one table lookup. 1080p HEVC Main 10, 300
  pictures, on the R69-1 by `ffmpeg -benchmark`: decode alone 2.7 ms of CPU a picture; `VideoProc`
  to NV12 9 ms more, about 3 of them the kernel's cache upkeep; a P010 download 47 ms a picture in
  C, which since MPP lists P010 every reading client paid, and 17 ms by NEON, identical to software.
  mpv on HEVC Main 10 on the M2 Plus stayed at 39 to 40% of a core, its source there not read back.
- `VideoProc` crashed GStreamer's `va` plugin on the request backend: registering `vapostproc`, it
  exports a surface with only a `VideoProc` context open, and `request_lend_backing` took that
  context for a decoder and read its codec. A crashed plugin is blacklisted, so every `va` element
  went: the suite said only "lists a driver only on a DRM render node". Lending now looks at decode
  contexts alone, a `VideoProc` context takes its pipeline buffer alone, and the suite's
  `gstreamer.va-plugin` fails on a crash or a blacklist. GStreamer gets a registry of its own. The
  H313 then 90 pass, none failing; the M20 as the driver before this change on every check.
- NV15 narrowing read each row into a buffer of its own first, against uncached decoder memory;
  MPP's buffers are allocated cacheable and `rkvdec`'s CAPTURE takes cache hints since this week, so
  the copy only cost. The R69-1 on next2, 1080p HEVC Main 10, 300 pictures to NV12 by `VideoProc`:
  2.7 s of user time with the copy, 1.9 s without, every picture identical between the two.
- 2026-11-20: next2 on the RK3528 and RK3518 runs the GPU at 800 MHz on 22 mV less than vendor, and
  is suspected of the M2 Plus's power-on resets; every next2 result on them is void until that is
  fixed, the entries above included. Measured again on the R69-1 under vendor 6.1: NV15 narrowed to
  NV12 by `VideoProc` without the row copy, 300 pictures identical to the build with it, 2.5 s of
  user time against 3.2; the suite 89 pass, none failing, 10-bit 30 of 30 identical, `vpp.*` 53.7
  and 58.8 dB, GStreamer 10-bit 63 dB.
- `extras/gst-plugins-bad` and its `0001` dropped: `0001` let GStreamer narrow where a driver listed
  no 10-bit format, and every 10-bit config lists P010 since MPP's narrowing went. Debian's own
  `gst-plugins-bad`, unpatched, decodes 10-bit through the driver at 63 dB on the R69-1.
- `vaEndPicture` on MPP's surfaces waited for MPP to take the target before it returned: one picture
  in flight, MPP's start passed to the client's decode thread. Chromium's trace on the M2 Plus,
  YouTube 4K60 VP9, showed decode calls at a median 6.8 ms and a p99 66 ms, 81% of the slow ones
  that wait. The wait moved to the next call's start, and the hold is taken again as soon as the
  picture comes out; one buffer is still free at a time, which MPP takes first in, first out. With
  AFBC on: median 2.8 ms, p99 23 ms, 56.8 of 60 pictures a second shown. The R69-1 under vendor 6.1:
  the suite 89 pass, every picture identical, VP9 with alt-refs and the size switches included.
