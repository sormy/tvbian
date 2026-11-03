# linux-sunxi — mainline kernel patches for Allwinner boards

Applied through `kernel/sunxi64.conf` (6.18) and `kernel/sunxi64-next.conf` (newest stable, 7.3),
each listing its patches one by one; each leaves on the bump that brings it from upstream. The top
level is the current kernel's series, 6.18's; `next/` holds what only `-next` does: patches written
for its API, and rewrites of top-level ones it takes in their place (`0103`, `0246`, `0257`, `0263`,
`0265`, `0276`, `0278`, for 7.3).

| Patch         | Holds                                            |
| ------------- | ------------------------------------------------ |
| `0034`        | 7.2.12's display drivers                         |
| `0035`        | `drm_gem_dma`: through the DRM DMA device        |
| `0036`        | 7.2's display drivers on 6.18's API              |
| `0037`        | 7.2's IEC958 subframe definitions                |
| `0038`        | the H616 audio hub on 6.18's ASoC API            |
| `0001`–`0033` | LibreELEC's: MMC, clocks, SCPI, wake, Bluetooth  |
| `0100`–`0903` | LibreELEC's: HDMI, display, video, audio, AC200  |
| `0041`        | the H616 display pipeline in `sun50i-h616.dtsi`  |
| `0042`        | `sunxi_wdt`: timeouts past its 16 s              |
| `0043`        | `sunxi-mmc`: the vendor's output phase in DDR    |
| `0044`        | `sunxi-mmc`: the sample delay from the tree      |
| `0045`        | Cedrus: the H616 on the H6 variant               |
| `0046`        | SRAM C1 for the H616 video engine                |
| `0047`        | `sun50i-iommu`: a master's port reset, exported  |
| `0048`        | Cedrus: reset its IOMMU port after a timeout     |
| `0052`–`0063` | Cedrus: VP9, P010 10-bit, AFBC out on the H616   |
| `0064`–`0065` | VC-1: parsed-slice uAPI and Cedrus decoding      |
| `0066`        | Cedrus: AFBC out for HEVC                        |
| `0067`        | the DI300 deinterlacer                           |
| `0068`        | `0067` on 6.18's `v4l2_m2m_buf_copy_metadata()`  |
| `0069`–`0074` | Cedrus: Bootlin's H.264 encoder, for the V3s     |
| `0075`–`0088` | Cedrus encode, P010; IR wake, the remote         |
| `0089`        | `sun4i_tv`: the H616 TV encoder                  |
| `0090`        | `tve0` kept on its assigned parent               |
| `0091`        | mixer: the H616 display engine at 696 MHz        |
| `0092`        | `sunxi_wdt`: stopped across system sleep         |
| `0093`        | `sun50i-iommu`: page sizes to 1 MiB advertised   |
| `0094`        | Cedrus: CAPTURE scaled by 2 or 4 via COMPOSE     |
| `0095`        | bridge connector: a mode set on HDR change       |
| `0096`        | planes: AFBC past the scaler alone refused       |
| `0097`        | Cedrus: 10-bit H.265 scaled as P010              |
| `0099`        | VI scaler: edge-directed only to enlarge         |
| `0276`        | DE33: the CDC 3D LUT on the VI planes            |
| `0277`        | TCON: FIFO underflows counted in debugfs         |
| `0278`        | HDMI: HDR as 10-bit YCbCr 4:2:2                  |
| `0279`        | UI layers: no scaling past the line buffer       |
| `0800`–`0804` | Cedrus: VP8 to 4096 wide, JPEG both ways         |
| `0805`–`0806` | Cedrus: MPEG-4 Part 2 and H.263 decode           |
| `0807`        | Cedrus: a coded format sized by its own engine   |
| `0808`        | Cedrus: each decoder's largest picture, measured |
| `0809`        | Cedrus: a missing HEVC reference skipped quietly |

The display stack is 7.2's on both kernels. `0034` takes 7.2.12's `drivers/gpu/drm/sun4i`,
`bridge/synopsys`, `ccu-sun8i-de2.c`, `sun50i-iommu.c` and `dw_hdmi.h` as they are; LibreELEC's
display patches then apply unchanged: `0100`–`0106`, `0200`–`0275` less `0236`, a tree change, and
`0409`, `0500`, `0901`, `0902`. `0035` backports 7.2's `drm_gem_dma` allocating through the device
`drm_dev_set_dma_dev()` names; without it the console's framebuffer gets a physical address, which
the planes read through the IOMMU, faulting each frame. `0036` is 7.2's API on 6.18:
`struct drm_atomic_state` under its old name, the color-format bits, `of_drm_find_bridge()`,
`hpd_notify()`'s arguments, `field_prep()`. `0041`, the H616's display pipeline nodes, is the
`sun4i` DRM maintainer's, from Armbian's `sunxi-6.18` at `armbian/build` `fac57a0`.

`0042` is ours: the watchdog's hardware stops at 16 s and the driver refused any longer timeout, so
systemd's 80 s left it unarmed. It now declares 16 s as its hardware heartbeat, as `meson_gxbb_wdt`
does, and the watchdog core pings in between. Not yet submitted.

`0043` and `0044` are ours, after Allwinner's own driver: command at 180°, data at 180° in DDR, and
a board's tuned sample delay as `allwinner,sample-delay`, where mainline samples at 0. On the Tanix
TX1 V2.0's eMMC in DDR52 the two together end the data errors and the hang in recovery; whether
`0044` alone does is untested. Not yet submitted: the binding needs a schema.

`0045` and `0046` are Jernej Škrabec's, as Armbian's `sunxi-6.18` carries them; upstream, v2 of
"arm64: allwinner: h616: Support Video Engine" (2026-07) and the H616 SRAM series, applied for 7.2.
A board's tree adds the `video-codec` node and its SRAM section.

`0047` and `0048` are ours: a stream the engine cannot decode makes it read outside its buffers, the
IOMMU's fault handler resets the engine's port while it still transfers, and the port stays stuck —
every later stream decodes to garbage until a reboot. After its watchdog resets the engine, Cedrus
resets the port again, with nothing in flight; the vendor BSP's `sunxi_reset_device_iommu()` is the
same reset. Not yet submitted.

Audio is LibreELEC's on both kernels: the H616 audio hub (`0520`), its HDMI path (`0500`–`0505`,
`0514`), the PLL's sigma-delta table and rate changes (`0518`, `0519`) and the codec's 1024 × fs
module clock (`0521`). 6.18 needs `0037`, 7.2's IEC958 subframe masks, and `0038`, the hub's
`pcm_new` under 6.18's name. Armbian's vendor audio hub, which held the PLL at the rate its own
dividers expected and left the analog codec at half speed, is retired.

`0052`–`0066` are Jernej Škrabec's, LibreELEC's `projects/Allwinner/patches/linux` `0410`–`0425`
(LibreELEC.tv `96d9f0f`), less `0424`, a tree change, and `0406`, which is `0045`. `0053`'s hunk
adding blank lines to the watchdog is left out against `0048`. VP9 runs in the H616 video engine's
HEVC slot; VC-1 takes Simple and Advanced profiles; Main is refused, its P pictures drifting against
the SMPTE conformance streams. Not upstream.

`0067` is Jernej Škrabec's, LibreELEC's `0426`; `0068` is ours, for 6.18's API. The tree needs
LibreELEC's node, `0435`.

`0069`–`0074` are Paul Kocialkowski's, Bootlin's `cedrus/h264-encoding` on
`github.com/bootlin/linux` at `4e9497947c56`, rebased onto `0068`: the driver split into a decoder
and an encoder device, `cedrus-dec` and `cedrus-enc`, and a QP-only H.264 encoder for the V3s.
Unmerged upstream.

`0075`–`0082` are ours. The H616 encoder takes buffer addresses in 256-byte units, the scaler size
in 8-pixel units and a macroblock row buffer at `0xb9c`, and past 2048 wide writes deblocking data
to memory. On top: the stop command ffmpeg and GStreamer drain with, escaped headers, the SPS timing
and cropping, references kept out of the picture buffers, and frame rate control. `0083` lets
`sunxi-cir` wake the system; `0085` keeps P010 the 10-bit default over `0066`'s AFBC, which a
software consumer cannot read; `0088` is the TX1's remote keymap, `rc-tanix-tx1`, on the canonical
keys. Not yet submitted.

## `next/`: `sunxi64-next`

`kernel/sunxi64-next.conf` takes the root's series, with these in place of, or beside, its patches:

| Patch                  | Holds                                             |
| ---------------------- | ------------------------------------------------- |
| `0044`                 | the sample delay, less LibreELEC's member         |
| `0069`–`0085`          | Cedrus, less `0083`, on LibreELEC's Cedrus        |
| `0087`                 | Cedrus metadata copy, 7.2's two-argument call     |
| `0103`, `0257`, `0265` | the dw-hdmi bridge on 7.3's encoder and state API |
| `0246`, `0263`         | AFBC framebuffers, the writeback check on 7.3     |
| `0276`, `0278`         | the CDC LUT and HDR 4:2:2 on 7.3's DRM API        |

## LibreELEC's series and ours

`0001`–`0033` and `0100`–`0903` are LibreELEC's `projects/Allwinner/patches/linux` at LibreELEC.tv
`96d9f0f`, all 202, written for 7.2, which 7.2 applies whole: the display stack (DE33 YUV and AFBC
planes, plane scalers, HDMI 10-bit and YUV 4:2:0, the dw-hdmi CEC fixes), the video engine and the
DI300. Eight are rebased onto 7.2.12, the rest are LibreELEC's as they are; 7.3 changed the encoder
setup, the bridge state hook and the atomic check again, so `-next` takes five rewrites from
`next/`. On top, ours LibreELEC lacks: `0042`–`0044`, `0047`, `0048`.

`kernel/sunxi64-next.fragment` keeps the hung-task panic off, NTFS3 as 6.18 builds it, and
LibreELEC's AC200 core built in, its PHY driver sharing the module name.

`0092` is ours: the watchdog's timer runs on in s2idle, where nothing pings it, so any sleep past
its 16 s hardware maximum reset the box. Stopped on suspend and restarted on resume, as
`meson_gxbb_wdt` does. Not yet submitted.

`0093` is ours: LibreELEC's `0409` writes runs of entries per call, but the domain still advertised
4 KiB alone, so the core mapped buffers a page at a time. Importing a 4K P010 frame and dropping it
took 8.7 ms, 3.7 ms with every size to 1 MiB advertised. Not yet submitted.

`0094` is ours: the video engine's secondary output writes the picture scaled by 2 or 4 each way
while the engine reconstructs and references the full one, hidden after it in the same buffer as
P010's. A client asks with `S_SELECTION`, `V4L2_SEL_TGT_COMPOSE` on CAPTURE, before CAPTURE buffers
exist; the decoder node's selection ioctls, disabled until now, answer COMPOSE. 8-bit H.264 and
H.265; `ffmpeg/0017` asks. Not yet submitted.

`0800`–`0802` are ours. Past 2048 wide VP8 keeps the deblocking and intra prediction rows in DRAM,
as H.264 does, and reads 0x5400 bytes of probabilities, the vendor library's size. A stopped picture
queue returns its buffers, and the empty last buffer a drain ends on carries no payload. `0803` is
Emmanuel Gil Peyrot's JPEG decoder from his v1 series, ported to Bootlin's rework: baseline JPEG and
Motion JPEG, as NV12, the Annex K tables standing in for missing ones; the engine parses the headers
itself, so it takes no request and drains as a stateful decoder. `0804` is ours, the H616 encoder's
JPEG mode after the vendor library: the Annex K Huffman tables fixed in the engine, the quantisation
tables loaded at `0xe0`/`0xe4`, the headers put through the engine and the end marker by the CPU.
`0800`–`0808` apply last on both kernels, in order. Not yet submitted.

`0805`–`0806` are ours. `0805` adds private stateless MPEG-4 Part 2 controls, as `0064` does VC-1's:
VOL, VOP, quantisation matrices and a slice. `0806` decodes Simple and Advanced Simple profile and
H.263 baseline in the MPEG engine after the vendor library's register map: a request per video
packet or H.263 GOB, the engine parsing no packet header; GMC from the sprite trajectory; the DivX
chroma-rounding bugs as the engine's own modes. Refused: interlaced B-VOPs, whose field direct mode
the engine gets wrong, static sprites, data partitioning, RVLC. `ffmpeg/0019` drives it. Not yet
submitted.

`0807` is ours: `S_FMT` sized a coded format by the engine it replaced, the MPEG-2 engine the
context opens with, so JPEG took MPEG-2's 4096x2304 in place of its own. Not yet submitted.

`0808` is ours: each decoder's largest picture, as measured. HEVC and VP9 to 8192x4320, 8192x8192
hanging the SoC; 10-bit to 6144x3456, 7680x4320 hanging; MPEG-4 to the 4080 its 8-bit macroblock
count holds; JPEG to 6000x4000, 6144x6144 hanging. Not yet submitted.

`0809` is ours: an HEVC reference the queue no longer holds, after a gap in the stream, is skipped
with a rate-limited debug line, not a `WARN_ON`. Not yet submitted.

`0276` is ours: DE33's VI channel 0 carries a 17-point 3D LUT, CDC, ahead of the channel's CSC, on
the channel's own signal: Y, Cb, Cr for YUV input in the red, green and blue fields; R, G, B for
RGB. Its plane carries `SUNXI_CDC_LUT3D_SIZE`, immutable, 17, and `SUNXI_CDC_LUT3D`, a blob of 17³
`drm_color_lut`, the first component fastest, reserved zero; 0 bypasses. The plane's
`COLOR_ENCODING` and `COLOR_RANGE` describe the table's output. The table goes through the RCQ in
the hardware's eight parity banks when the blob changes or the plane becomes visible; the CSC stages
around it stay at identity. The vendor driver lists a CDC on channel 1 too; the H313's keeps no
write there. Not yet submitted.

`0096` is ours: an AFBC layer skips the fetcher's coarse downscale, so a shrink the VI scaler cannot
keep up with breaks the picture up below its top. The scaler takes a source pixel a clock: an output
line's source pixels, the wider width times the shrink, must fit in 90% of the mixer clocks of its
line time, or the commit is refused for userspace to take a linear buffer. The share is
`sun8i_mixer.afbc_shrink_margin`, percent, default 90, clamped to 50–150, writable at run time
(`/sys/module/sun8i_mixer/parameters/`). Not yet submitted.

`0277`–`0279` are ours. `0277` counts the TCON's latched FIFO underflow at each vblank, clearing it,
as `dri/<n>/crtc-<i>/underruns` in debugfs. `0278` sends HDR as YCbCr 4:2:2, 12-bit container, where
`max bpc` is 10 or more, the connector's `HDR_OUTPUT_METADATA` names an EOTF other than SDR and the
sink lists 4:2:2; SDR stays RGB. 4:4:4 at 10 bits needs a TMDS clock 5/4 of the pixel clock, which
the H616's integer video PLL cannot divide from the TCON's. `0279` refuses a UI layer scaled from a
source wider than its channel's line buffer, 2048 on DE33. Not yet submitted.

`0089` adds the H616 TV encoder to `sun4i_tv`, on both kernels, its DAC load detection left off:
armed, it clicks on the AV jack, and it sensed no cable here; `0090` keeps the encoder's clock on
the parent the tree assigns.
