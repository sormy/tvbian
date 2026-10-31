# ffmpeg — V4L2 request, mem2mem and Rockchip MPP on FFmpeg 9.0.2

FFmpeg has no hwaccel for stateless V4L2 decoders such as Cedrus, and its `v4l2_m2m` wrappers for
stateful ones such as the Amlogic decoder stumble on raw streams, resolution changes and draining;
its `rkmpp` codecs for Rockchip's MPP lack 10-bit, scaling and AFBC. One set on FFmpeg 9.0.2, the
newest release, carries all three; `0001`–`0035` apply in order with `patch -p1`.

| Patch  | Adds                                                                | From      |
| ------ | ------------------------------------------------------------------- | --------- |
| `0001` | `v4l2request`: MPEG-2, H.264, HEVC, VP8, VP9 hwaccels               | LibreELEC |
| `0002` | `v4l2request` VC-1                                                  | LibreELEC |
| `0003` | raw elementary streams: unstamped packets came back all at pts 0    | ours      |
| `0004` | MPEG-1/2, MPEG-4 and VC-1 `extradata` sent ahead of the first one   | ours      |
| `0005` | `mjpeg_v4l2m2m`, which ffmpeg lacks                                 | ours      |
| `0006` | encoders fill `extradata` for Matroska and MP4                      | ours      |
| `0007` | the drain waits for a CAPTURE buffer before it reports end of file  | ours      |
| `0008` | DRM PRIME frames and a DRM hardware context                         | LibreELEC |
| `0009` | a bounded wait for a picture                                        | ours      |
| `0010` | `ftp`: the URL's path decoded                                       | ours      |
| `0011` | `-capture_max_width`, `-capture_max_height`: a scaled CAPTURE       | ours      |
| `0012` | a reinit no longer waits for the user to free its frames            | ours      |
| `0013` | the frames before a resolution change are dequeued, not dropped     | ours      |
| `0014` | `deinterlace_v4l2m2m`, a V4L2 mem2mem deinterlacer filter           | LibreELEC |
| `0015` | the deinterlacer's timestamps in its own, halved time base          | ours      |
| `0016` | encoders copy a frame into the driver's stride, not the frame's     | ours      |
| `0017` | `v4l2request` device options `capture_max_width`, `_height`         | ours      |
| `0018` | `v4l2request` device option `afbc`: AFBC frames by bit depth        | ours      |
| `0019` | `v4l2request` MPEG-4 Part 2 and H.263                               | ours      |
| `0020` | `rkmpp`: 10-bit frames as `DRM_FORMAT_NV15`                         | ours      |
| `0021` | `hwcontext_drm` refuses a frame whose planes its format lacks       | ours      |
| `0022` | `rkmpp`: timestamps to MPP in microseconds                          | ours      |
| `0023` | `mpeg2_rkmpp`, `mpeg4_rkmpp` decoders                               | ours      |
| `0024` | `rkmpp`: `capture_max_width`, `_height`, a ½ picture                | ours      |
| `0025` | `rkmpp`: option `afbc`, AFBC frames by bit depth                    | ours      |
| `0026` | `rkmpp` encoders: bitrate bounds around `-b:v`                      | ours      |
| `0027` | `mpeg4_v4l2m2m` unpacks packed B-frames: a picture per packet       | ours      |
| `0028` | `v4l2m2m` option `afbc`: Amlogic FBC frames by bit depth            | ours      |
| `0029` | `extradata` sent again after a flush, for a decoder that restarts   | ours      |
| `0030` | the capture queue restarts after a resolution change on no packet   | ours      |
| `0031` | `rkmpp`: MPEG-2, MPEG-4, VP8 past 1920x1088 refused at open         | ours      |
| `0032` | `v4l2m2m` encoders: a picture larger than the driver's refused      | ours      |
| `0033` | `mjpeg_v4l2m2m` encoder, quality from `-q:v`, full range            | ours      |
| `0034` | `mpeg1_rkmpp`, `h263_rkmpp` decoders                                | ours      |
| `0035` | `rkmpp`: the stream ends on MPP's end of stream; 8K, seeks after it | ours      |

`0001`, `0002` and `0014` are LibreELEC's `packages/multimedia/ffmpeg/patches/v4l2-request` and
`vf-deinterlace-v4l2m2m` at LibreELEC.tv `96d9f0f`: Jonas Karlman's request-API series, posted to
ffmpeg-devel (v2, 2024-08-06, unmerged), with VP9 and VC-1 on top. `0003`–`0013` came from
`research/ffmpeg-v4l2m2m/`, where their findings stay.

`0019` takes the private controls of `linux-sunxi/0805`: it finds the video packets and H.263 GOB
headers in the VOP itself and queues one request each. A stream the driver refuses at the VOL probe,
or with H.263 annexes or interlaced B-VOPs, decodes in software.

`0020`–`0026` extend FFmpeg's own `rkmppdec` and `rkmppenc`, which output DRM PRIME frames: they are
chosen with `-c:v h264_rkmpp` and the like, not `-hwaccel`. Unpatched, a 10-bit frame stopped
ffmpeg, MPEG-2 frames came out of order on MPP's microsecond parser, and `-b:v 8M` encoded at MPP's
2.5 Mbit/s default. MPP writes the ½ picture after the full one in the same buffer; AFBC is never
asked together with it, as MPP times out there. H.264 and HEVC AFBC frames are 4 lines taller,
`crop_top` 4.

`0027`–`0030` serve the Amlogic decoder through the `*_v4l2m2m` wrappers. `0028`'s `afbc` takes the
bit depths as `0018`'s and `0025`'s do, and asks DRM PRIME frames in the decoder's own compressed
format, Amlogic FBC in its scatter layout: `DRM_FORMAT_YUV420_8BIT` or `_10BIT` with
`DRM_FORMAT_MOD_AMLOGIC_FBC`, which only the display's video plane reads.

`v4l2request` registers its own device type, `AV_HWDEVICE_TYPE_V4L2REQUEST`; Kodi accepts it from
Kodi 22 (`xbmc/xbmc` PR #25467).

## Build

A static `ffmpeg` beside Debian's, replacing nothing; on Debian trixie arm64, as root, in the repo
checkout:

```bash
apt-get install -y --no-install-recommends build-essential pkg-config curl xz-utils nasm libdrm-dev libudev-dev
curl -fsSL https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz | tar -xJ
for p in patches/ffmpeg/0*.patch; do patch -d ffmpeg-9.0.2 -p1 < $p; done
cd ffmpeg-9.0.2 && ./configure --disable-autodetect --disable-doc --enable-libdrm --enable-libudev --enable-v4l2-request --enable-v4l2-m2m --enable-static --disable-shared
make -j$(nproc) ffmpeg && ./ffmpeg -hide_banner -hwaccels
```

`-hwaccels` lists `v4l2request`. ✅ built 2026-10-25 in the trixie build container.

On Rockchip, MPP first, from its `1.1.0` tag, then the same steps with `rkmpp` configured in; MPP is
Apache-2.0, so the build is LGPLv3:

```bash
apt-get install -y --no-install-recommends cmake git
git clone --depth 1 -b 1.1.0 https://github.com/rockchip-linux/mpp
cmake -S mpp -B mpp/build -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr/local
make -C mpp/build -j$(nproc) install && ldconfig
cd ffmpeg-9.0.2 && PKG_CONFIG_PATH=/usr/local/lib/pkgconfig ./configure --disable-autodetect --disable-doc --enable-libdrm --enable-libudev --enable-v4l2-request --enable-v4l2-m2m --enable-rkmpp --enable-version3 --enable-static --disable-shared
```

## Decode test

On the box:

```bash
./ffmpeg -hide_banner -hwaccel v4l2request -hwaccel_output_format drm_prime -i clip.mkv -f null -
```

Scaled by the decoder to fit 1080 lines, on a kernel with `linux-sunxi/0094`:

```bash
./ffmpeg -hide_banner -init_hw_device v4l2request=v4:,capture_max_height=1080 -hwaccel v4l2request -hwaccel_device v4 -hwaccel_output_format drm_prime -i clip.mkv -f null -
```

The hardware path logs `Using V4L2 media driver cedrus (6.18.x) for S264` (`S265` HEVC, `MG2S`
MPEG-2, `VP8F` VP8, `VP9F` VP9, `SVC1` VC-1, `MG4S` MPEG-4 and H.263); `-loglevel verbose` adds the
CAPTURE format, `P010` for 10-bit. Without the line, ffmpeg fell back to software. Correctness
against the software decode converts both, at 10 bits for a 10-bit stream:

```bash
./ffmpeg -hide_banner -hwaccel v4l2request -i clip.mkv -i clip.mkv -lavfi "[0:v]format=yuv420p10le[a];[1:v]format=yuv420p10le[b];[a][b]psnr" -f null -
```

## Encode test

On the box, `h264_v4l2m2m` on Cedrus:

```bash
./ffmpeg -hide_banner -f lavfi -i testsrc2=size=1920x1080:rate=30 -frames:v 300 -pix_fmt nv12 -c:v h264_v4l2m2m out.mp4
```

"Failed to set header mode" and "Failed to set bit rate" are expected: the encoder takes headers
with the first frame and a fixed QP only.

## Results

Tanix TX1 V2.0 (H313), 2026-10-25, the kernel with `linux-sunxi/0051`–`0066`: one video-engine
interrupt per frame, PSNR against the software decode.

| Codec                | Size       | fps | Against the software decode        |
| -------------------- | ---------- | --- | ---------------------------------- |
| VP9                  | 1920×1080  | 140 | identical                          |
| VP9                  | 3840×2160  | 28  | identical                          |
| HEVC Main10, P010    | 1920×1080  | 89  | identical at 10 bits               |
| HEVC Main10, P010    | 3840×2160  | 18  | identical at 10 bits               |
| VC-1 Advanced        | 1280×720   | 304 | identical                          |
| VC-1 Advanced, 1080i | 1920×1080  | 64  | identical                          |
| VC-1 Main (WMV3)     | 1440×1080  | 33  | software: the hwaccel refuses Main |
| MPEG-4 ASP, B-VOPs   | 1920×1080  | 143 | luma ≥ 64 dB, IDCT only            |
| H.263 baseline       | 704×576    | 304 | luma ≥ 65 dB, IDCT only            |
| Deinterlace, DI300   | 1920×1080i | 121 | moving edges solid, combing gone   |

The deinterlacer, `-vf deinterlace_v4l2m2m` after a `drm_prime` decode, gives a frame per field.

The MPEG-4 and H.263 rows are 2026-10-31's, with `linux-sunxi/0805`–`0806`: the engine's IDCT is not
FFmpeg's, so they compare by PSNR, not bit for bit.
