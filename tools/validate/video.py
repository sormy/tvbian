#!/usr/bin/env python3
"""Hardware video test matrix: decode, decoder scaling and encode, against FFmpeg's software path.

On the host:
  video.py clips                                   the clip corpus, made by the host's FFmpeg
  video.py run --box root@<box> --engine <engine>  copy, run on the box, save its JSON
  video.py report <run.json>                       the largest passing size per codec
  video.py compare <old.json> <new.json>           what got worse; exits 1 if anything did
On the box, started by run:
  video.py box --engine <engine> --ffmpeg <ffmpeg> --dir <dir>
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "build" / "validate" / "video" / "clips"
RESULTS = ROOT / "build" / "validate" / "video"
BOX_DIR = "/var/tmp/tvb-validate-video"
FRAMES = 3
# a hardware hang costs a minute at most; past two failing sizes a codec's ladder stops
CASE_TIMEOUT = 60
STOP_AFTER = 2
LADDER = ["1920x1080", "2560x1440", "3840x2160", "4096x2160", "4096x2304", "4080x4080", "5120x2880",
          "6144x3456", "7680x4320", "8192x4320", "8192x8192", "16384x8640"]
# luma PSNR a decode must hold where the format leaves the IDCT's rounding to the decoder
LOSSY_FLOOR_DB = 50.0
SCALE_FLOOR_DB = 30.0
ENCODE_FLOOR_DB = 30.0
SCALE_FROM = "3840x2160"
SCALE_LINES = 1080
# frame rate: a FRAMES-long run and a longer one, differenced so setup cancels out; the longer one
# grows until it outlasts the short one by FPS_SPAN seconds
FPS_FRAMES = [12, 60]
FPS_SPAN = 1.0
# film's rate: a size the engine runs slower than this is correct but cannot play
PLAYABLE_FPS = 24

# name: container, encoder arguments, sizes, whether the decode must be bit exact
X265 = ["-preset", "ultrafast", "-x265-params", "log-level=0"]
VPX = ["-deadline", "realtime", "-cpu-used", "8", "-row-mt", "1"]
CODECS = {
    "h264": ("mp4", ["-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-bf", "2"], LADDER, True),
    "h264p10": ("mp4", ["-pix_fmt", "yuv420p10le", "-c:v", "libx264", "-profile:v", "high10", "-preset", "veryfast"], LADDER, True),
    "hevc": ("mp4", ["-pix_fmt", "yuv420p", "-c:v", "libx265"] + X265, LADDER, True),
    "hevc10": ("mp4", ["-pix_fmt", "yuv420p10le", "-c:v", "libx265"] + X265, LADDER, True),
    "vp9": ("webm", ["-pix_fmt", "yuv420p", "-c:v", "libvpx-vp9"] + VPX, LADDER, True),
    "vp9p2": ("webm", ["-pix_fmt", "yuv420p10le", "-c:v", "libvpx-vp9", "-profile:v", "2"] + VPX, LADDER, True),
    "vp8": ("webm", ["-c:v", "libvpx", "-deadline", "realtime", "-cpu-used", "8"], LADDER, True),
    "mpeg1": ("mpg", ["-c:v", "mpeg1video", "-q:v", "3", "-bf", "2"], ["1280x720", "1920x1080", "2560x1440", "3840x2160"], False),
    "mpeg2": ("ts", ["-c:v", "mpeg2video", "-q:v", "3", "-bf", "2"], ["1920x1080", "2560x1440", "3840x2160", "4000x2250", "4000x3000", "4080x4080", "7680x4320"], False),
    "mpeg4": ("avi", ["-c:v", "mpeg4", "-q:v", "3", "-bf", "2"], ["1920x1080", "2048x2048", "2560x1440", "3840x2160", "4080x2160", "4080x4080"], False),
    "h263": ("3gp", ["-c:v", "h263", "-q:v", "3"], ["176x144", "352x288", "704x576", "1408x1152"], False),
    "mjpeg": ("avi", ["-pix_fmt", "yuvj420p", "-c:v", "mjpeg", "-q:v", "3"], ["1920x1080", "3840x2160", "4096x4096", "6000x4000", "6144x4096", "6144x5120", "6144x6144",
                                                                         "8192x8192"], False),
}

# engine: decoder input options per codec (None: not offered), how frames come out, encoders
ENGINES = {
    "sunxi": {
        "decode": lambda c: ["-c:v", "mjpeg_v4l2m2m"] if c == "mjpeg" else ["-hwaccel", "v4l2request"],
        "scale": lambda c: ["-init_hw_device", f"v4l2request=v:,capture_max_height={SCALE_LINES}",
                            "-hwaccel", "v4l2request", "-hwaccel_device", "v"],
        "download": "",
        "keep": ["-hwaccel_output_format", "drm_prime"],
        "fallback": r"Failed setup for format|hwaccel initialisation returned error|Failed to get a hw",
        "irq": r"cedrus",
        "encoders": {"h264": "h264_v4l2m2m", "mjpeg": "mjpeg_v4l2m2m"},
    },
    "rkmpp": {
        "decode": lambda c: ["-c:v", {"h264p10": "h264", "hevc10": "hevc", "vp9p2": "vp9"}.get(c, c) + "_rkmpp"]
        if c != "mjpeg" else None,
        "scale": lambda c: ["-capture_max_height", str(SCALE_LINES)] + ENGINES["rkmpp"]["decode"](c),
        "download": "hwdownload,format=nv12,",
        # NV15 frames cannot be downloaded: 10-bit is checked by frames decoded
        "count_only": {"h264p10", "hevc10", "vp9p2"},
        "fallback": r"larger than the hardware|unsupported by MPP|for soc \S+ unsupported|Unknown codec",
        "irq": r"vdpu|rkvdec|jpegd|avsd|rkvenc",
        "encoders": {"h264": "h264_rkmpp", "hevc": "hevc_rkmpp"},
    },
    "meson": {
        "decode": lambda c: ["-c:v", {"hevc10": "hevc", "vp9p2": "vp9", "h264p10": "h264"}.get(c, c) + "_v4l2m2m"],
        "scale": lambda c: ["-capture_max_height", str(SCALE_LINES)] + ENGINES["meson"]["decode"](c),
        "download": "",
        # 10-bit comes out as 8-bit NV12: checked by frames decoded
        "count_only": {"hevc10", "vp9p2"},
        "fallback": r"Could not find a valid device|can't configure decoder",
        "irq": r"vdec|esparser|venc|hcodec",
        "encoders": {"h264": "h264_v4l2m2m", "hevc": "hevc_v4l2m2m"},
    },
}
# the CPU's fastest encoder per codec: a hardware encoder slower than it has no use
CPU_ENCODERS = {"h264": ["-c:v", "libx264", "-preset", "ultrafast"], "hevc": ["-c:v", "libx265", "-preset", "ultrafast"],
                "mjpeg": ["-c:v", "mjpeg", "-q:v", "3"]}
ENCODE_SIZES = ["1280x720", "1920x1080", "3840x2160", "4096x2304", "4096x4096", "7680x4320", "8192x4320",
                "8192x8192", "16384x8640"]


def sh(cmd, timeout=CASE_TIMEOUT):
    """Run a command; its exit code, combined output and wall time."""
    start = time.monotonic()
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                           errors="replace", timeout=timeout)
        return p.returncode, p.stdout, time.monotonic() - start
    except subprocess.TimeoutExpired as e:
        return 124, (e.stdout or "") if isinstance(e.stdout, str) else "", time.monotonic() - start


def pixels(size):
    w, h = size.split("x")
    return int(w) * int(h)


# host: the corpus

def cmd_clips(args):
    CORPUS.mkdir(parents=True, exist_ok=True)
    manifest = {"ffmpeg": sh(["ffmpeg", "-version"])[1].splitlines()[0], "frames": FRAMES, "clips": {}}
    for codec, (ext, enc, sizes, _) in CODECS.items():
        for size in sizes:
            path = CORPUS / f"{codec}-{size}.{ext}"
            if not path.exists():
                rc, out, _ = sh(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                                 f"testsrc2=size={size}:rate=30", "-frames:v", str(FRAMES)] + enc + [str(path)])
                if rc or not path.exists() or not path.stat().st_size:
                    path.unlink(missing_ok=True)
                    print(f"{path.name}: the host's encoder refuses it", file=sys.stderr)
                    continue
            rc, out, _ = sh(["ffmpeg", "-v", "error", "-i", str(path), "-pix_fmt", "yuv420p10le",
                             "-f", "framemd5", "-"], timeout=None)
            manifest["clips"][path.name] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                            "framemd5": md5_lines(out)}
    (CORPUS / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"{len(manifest['clips'])} clips in {CORPUS}")


# box: one case at a time

# a framemd5 record; stderr, merged in, can land a log prefix on its line
FRAMEMD5_RECORD = re.compile(r"(?:\d+,\s*){5}([0-9a-f]{32})$")


def md5_lines(out):
    return [m.group(1) for line in out.splitlines() if (m := FRAMEMD5_RECORD.search(line))]


def frames_of(log):
    m = re.findall(r"frame=\s*(\d+)", log)
    return int(m[-1]) if m else 0


def framemd5(ff, opts, clip, download):
    vf = ["-vf", f"{download}format=yuv420p10le"] if download else ["-pix_fmt", "yuv420p10le"]
    rc, out, secs = sh([ff, "-hide_banner", "-nostdin", "-v", "verbose"] + opts + ["-i", clip] + vf +
                       ["-f", "framemd5", "-"])
    return md5_lines(out), out


def psnr(ff, opts, clip, download, scale=None):
    left = f"[0:v]{download}format=yuv420p10le,setpts=N[a]"
    right = f"[1:v]{'scale=' + scale.replace('x', ':') + ':flags=area,' if scale else ''}format=yuv420p10le,setpts=N[b]"
    rc, out, _ = sh([ff, "-hide_banner", "-nostdin", "-v", "info"] + opts + ["-i", clip, "-i", clip,
                    "-lavfi", f"{left};{right};[a][b]psnr=stats_file=-", "-f", "null", "-"])
    per = [dict(kv.split(":") for kv in line.split() if ":" in kv)
           for line in out.splitlines() if line.startswith("n:")]
    ys = [float(p.get("psnr_y", "inf")) for p in per]
    uvs = [min(float(p.get("psnr_u", "inf")), float(p.get("psnr_v", "inf"))) for p in per]
    return (min(ys) if ys else None), (min(uvs) if uvs else None), len(per)


def irq_count(pattern):
    """The engine's interrupts so far: a case that moves none ran on the CPU."""
    lines = Path("/proc/interrupts").read_text().splitlines()[1:]
    return sum(int(n) for l in lines if re.search(pattern, l) for n in l.split()[1:] if n.isdigit())


def dmesg_lines():
    return sh(["dmesg"])[1].splitlines()


def kernel_errors(before):
    new = dmesg_lines()[len(before):]
    return [l for l in new if re.search(r"error|fault|timed out|oops|warn", l, re.I)]


def frame_rate(run):
    """Frames a second once running; run(n) times n frames, None if they did not all come out."""
    short = run(FRAMES)
    for n in FPS_FRAMES:
        long_ = None if short is None else run(n)
        if long_ is None:
            return None
        if long_ - short >= FPS_SPAN or n == FPS_FRAMES[-1]:
            return round((n - FRAMES) / (long_ - short), 1) if long_ > short else None


def timed(cmd, frames):
    rc, log, secs = sh(cmd)
    return secs if rc == 0 and frames_of(log) == frames else None


def repeated(ff, clip, times):
    """The clip back to back in one file, probed once: no end of stream between copies."""
    listing, out = f"{BOX_DIR}/repeat.txt", f"{BOX_DIR}/repeat{os.path.splitext(clip)[1]}"
    Path(listing).write_text(f"file '{clip}'\n" * times)
    sh([ff, "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", listing, "-c", "copy", out])
    return out


def decode_rate(ff, eng, opts, clip):
    keep = eng.get("keep", []) if "-hwaccel" in opts else []
    return frame_rate(lambda n: timed([ff, "-hide_banner", "-nostdin", "-stats"] + opts + keep +
                                      ["-i", repeated(ff, clip, n // FRAMES), "-f", "null", "-"], n))


def encode_rate(ff, codec_args, size):
    src = f"testsrc2=size={size}:rate=30,format=nv12,loop=loop=-1:size={FRAMES}"
    return frame_rate(lambda n: timed([ff, "-hide_banner", "-nostdin", "-stats", "-f", "lavfi", "-i", src,
                                       "-frames:v", str(n)] + codec_args + ["-f", "null", "-"], n))


def decode_case(ff, engine, codec, size, clip, ref):
    eng = ENGINES[engine]
    opts = eng["decode"](codec)
    if opts is None:
        return {"verdict": "unoffered"}
    exact = CODECS[codec][3]
    before, irqs = dmesg_lines(), irq_count(eng["irq"])
    r = decode_verdict(ff, eng, codec, clip, opts, exact, ref, before)
    if r["verdict"] == "pass" and irq_count(eng["irq"]) == irqs:
        r["verdict"] = "software"
    if r["verdict"] == "pass":
        r["fps"] = decode_rate(ff, eng, opts, clip)
    return r


def decode_verdict(ff, eng, codec, clip, opts, exact, ref, before):
    sw = ref
    if codec in eng.get("count_only", ()):
        rc, log, _ = sh([ff, "-hide_banner", "-nostdin", "-v", "verbose"] + opts + ["-i", clip, "-f", "null", "-"])
        n = frames_of(log)
        fell_back = bool(re.search(eng["fallback"], log))
        ok = not fell_back and n == len(sw) and n > 0
        return {"frames_hw": n, "frames_sw": len(sw), "fallback": fell_back, "checked": "frames",
                "kernel": kernel_errors(before)[:3],
                "verdict": "refused" if fell_back else "pass" if ok else "broken"}
    hw, log = framemd5(ff, opts, clip, eng["download"])
    errs = kernel_errors(before)
    fell_back = bool(re.search(eng["fallback"], log))
    r = {"frames_hw": len(hw), "frames_sw": len(sw), "fallback": fell_back, "kernel": errs[:3]}
    if fell_back:
        r["verdict"] = "refused"
    elif not hw or len(hw) != len(sw):
        r["verdict"] = "broken"
    elif hw == sw or (exact and hw == framemd5(ff, [], clip, "")[0]):
        r.update(verdict="pass", identical=True)
    else:
        y, uv, n = psnr(ff, opts, clip, eng["download"])
        r.update(identical=False, psnr_y=y, psnr_uv=uv)
        r["verdict"] = "pass" if not exact and y is not None and y >= LOSSY_FLOOR_DB else "broken"
    return r


def scale_case(ff, engine, codec, clip):
    eng = ENGINES[engine]
    if eng["decode"](codec) is None:
        return {"verdict": "unoffered"}
    rc, log, _ = sh([ff, "-hide_banner", "-nostdin", "-v", "verbose"] + eng["scale"](codec) +
                    ["-i", clip, "-frames:v", "1", "-f", "null", "-"])
    if re.search(eng["fallback"], log):
        return {"verdict": "refused"}
    m = re.findall(r"Stream #0:0.*?Video: .*?(\d{3,5}x\d{3,5})", log)
    out = m[-1] if m else None
    if not out:
        return {"verdict": "broken"}
    if out == clip_size(clip):
        return {"verdict": "full", "out": out}
    if codec in eng.get("count_only", ()):
        return {"verdict": "pass", "out": out, "checked": "size"}
    y, uv, n = psnr(ff, eng["scale"](codec), clip, eng["download"], scale=out)
    ok = y is not None and y >= SCALE_FLOOR_DB
    return {"verdict": "pass" if ok else "broken", "out": out, "psnr_y": y}


def clip_size(clip):
    return re.search(r"-(\d+x\d+)\.", os.path.basename(clip)).group(1)


def encode_case(ff, engine, codec, encoder, size, time_cpu):
    out = f"{BOX_DIR}/enc.mkv"
    eng = ENGINES[engine]
    before, irqs = dmesg_lines(), irq_count(eng["irq"])
    src = ["-f", "lavfi", "-i", f"testsrc2=size={size}:rate=30", "-frames:v", str(FRAMES)]
    quality = ["-q:v", "3"] if codec == "mjpeg" else ["-b:v", "40M"]
    rc, log, secs = sh([ff, "-hide_banner", "-nostdin", "-v", "error", "-y"] + src +
                       ["-pix_fmt", "nv12", "-c:v", encoder] + quality + [out])
    errs = kernel_errors(before)
    # a v4l2m2m encoder has no CPU fallback, and may free its interrupt on close
    hardware = irq_count(eng["irq"]) != irqs or encoder.endswith("_v4l2m2m")
    if rc or not os.path.exists(out):
        verdict = ("unoffered" if "Unknown encoder" in log else "refused" if "larger than" in log else "broken")
        return {"verdict": verdict, "kernel": errs[:3],
                "log": log.strip().splitlines()[-1:] if log.strip() else []}
    got = frames_of(sh([ff, "-hide_banner", "-nostdin", "-i", out, "-f", "null", "-"])[1])
    _, info, _ = sh([ff, "-hide_banner", "-i", out])
    m = re.search(r"Video: .*?(\d{3,5}x\d{3,5})", info)
    # raw frames on both sides: compared by index, as timestamps may pair them wrong
    raw = lambda inp, name: sh([ff, "-v", "error", "-y"] + inp + ["-frames:v", str(FRAMES), "-vf",
                                "scale=out_range=tv,format=yuv420p", "-f", "rawvideo", f"{BOX_DIR}/{name}.yuv"])
    raw(["-i", out], "enc")
    raw(src[:-2], "src")
    rc, cmp_, _ = sh([ff, "-hide_banner", "-nostdin"] +
                     [a for n in ("enc", "src") for a in ("-f", "rawvideo", "-pix_fmt", "yuv420p", "-s", size,
                                                           "-i", f"{BOX_DIR}/{n}.yuv")] +
                     ["-lavfi", "psnr", "-f", "null", "-"])
    for n in ("enc", "src"):
        os.unlink(f"{BOX_DIR}/{n}.yuv")
    y = re.search(r"PSNR y:([\d.inf]+)", cmp_)
    y = float(y.group(1)) if y else None
    ok = got == FRAMES and m and m.group(1) == size and y is not None and y >= ENCODE_FLOOR_DB
    os.unlink(out)
    verdict = ("pass" if hardware else "software") if ok else "broken"
    r = {"verdict": verdict, "frames": got, "out": m.group(1) if m else None, "psnr_y": y, "kernel": errs[:3]}
    if verdict == "pass":
        r["fps"] = encode_rate(ff, ["-c:v", encoder] + quality, size)
        r["cpu_fps"] = encode_rate(ff, CPU_ENCODERS[codec], size) if time_cpu and codec in CPU_ENCODERS else None
    return r


def ladder(sizes, run, emit, start):
    """Each size once, smallest first, stopping after STOP_AFTER failing in a row; the largest pass
    and the first failure again, to catch a case that differs run to run."""
    done, misses = {}, 0
    for size in sorted(sizes, key=pixels):
        if misses >= STOP_AFTER:
            break
        start(size)
        began = time.monotonic()
        done[size] = run(size)
        done[size]["secs"] = round(time.monotonic() - began, 1)
        misses = 0 if done[size]["verdict"] == "pass" else misses + 1
    passed = [s for s in done if done[s]["verdict"] == "pass"]
    edges = passed[-1:] + [s for s in done if s not in passed][:1]
    for size in edges:
        if run(size)["verdict"] != done[size]["verdict"]:
            done[size]["verdict"] = "flaky"
    for size, rec in done.items():
        emit(dict(rec, size=size))


def cmd_box(args):
    global BOX_DIR
    BOX_DIR = args.dir
    ff, root = args.ffmpeg, Path(args.dir)
    manifest = json.loads((root / "manifest.json").read_text())["clips"]
    only = re.compile(args.only) if args.only else None
    skip = re.compile(args.skip) if args.skip else None
    emit = lambda rec: print(json.dumps(rec), flush=True)

    def runnable(suite, codec, sizes):
        """The sizes to run; a case --skip names is recorded, not run."""
        hazard = [s for s in sizes if skip and skip.search(f"{suite}:{codec}-{s}")]
        for size in hazard:
            emit({"suite": suite, "codec": codec, "size": size, "verdict": "skipped"})
        return [s for s in sizes if s not in hazard]

    emit({"kernel": os.uname().release, "engine": args.engine,
          "ffmpeg": sh([ff, "-version"])[1].splitlines()[0]})
    after = args.after.split(",") if args.after else []
    start = lambda suite, codec: lambda size: emit({"start": [suite, codec, size]})
    for codec, (ext, _, sizes, _) in CODECS.items():
        if f"decode:{codec}" in after:
            continue
        sizes = [s for s in sizes if f"{codec}-{s}.{ext}" in manifest and not (only and not only.search(f"{codec}-{s}"))]
        clip = lambda s: str(root / f"{codec}-{s}.{ext}")
        if "decode" in args.suite:
            ladder(runnable("decode", codec, sizes), lambda s: decode_case(ff, args.engine, codec, s, clip(s),
                                                manifest[f"{codec}-{s}.{ext}"]["framemd5"]),
                   lambda rec: emit(dict(rec, suite="decode", codec=codec)), start("decode", codec))
        if "scale" in args.suite and SCALE_FROM in sizes and runnable("scale", codec, [SCALE_FROM]):
            start("scale", codec)(SCALE_FROM)
            emit(dict(scale_case(ff, args.engine, codec, clip(SCALE_FROM)), suite="scale", codec=codec,
                      size=SCALE_FROM))
    if "encode" in args.suite:
        for codec, encoder in ENGINES[args.engine]["encoders"].items():
            if f"encode:{codec}" in after:
                continue
            sizes = [s for s in ENCODE_SIZES if not (only and not only.search(f"{codec}-{s}"))]
            # past the first size the hardware wins, the CPU only gets slower
            cpu = {"timed": True}

            def encode(size):
                r = encode_case(ff, args.engine, codec, encoder, size, cpu["timed"])
                if r.get("fps") and r.get("cpu_fps") and r["fps"] > r["cpu_fps"]:
                    cpu["timed"] = False
                return r

            ladder(runnable("encode", codec, sizes), encode,
                   lambda rec: emit(dict(rec, suite="encode", codec=codec)), start("encode", codec))
    emit({"done": True})


# host: run, report, compare

def cmd_run(args):
    global BOX_DIR
    ssh = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null", "-o", "LogLevel=ERROR",
           "-o", "BatchMode=yes", "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=3", args.box]
    scp = ["scp", "-q", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null", "-o", "LogLevel=ERROR"]
    BOX_DIR = subprocess.run(ssh + ["mktemp -d /var/tmp/tvb-validate-video.XXXXXX"],
                             check=True, stdout=subprocess.PIPE, text=True).stdout.strip()
    try:
        send = [str(p) for p in CORPUS.glob("*-*.*")] + [str(CORPUS / "manifest.json")]
        if send:
            subprocess.run(scp + send + [f"{args.box}:{BOX_DIR}/"], check=True)
        subprocess.run(scp + [__file__, f"{args.box}:{BOX_DIR}/video.py"], check=True)
        records, after = [], []
        RESULTS.mkdir(parents=True, exist_ok=True)
        out = Path(args.out) if args.out else None

        def save(rec):
            nonlocal out
            records.append(rec)
            out = out or RESULTS / f"{args.box.split('@')[-1]}-{records[0]['kernel']}.json"
            out.write_text(json.dumps(records, indent=1))

        while True:
            remote = (f"python3 {BOX_DIR}/video.py box --engine {args.engine} --ffmpeg {args.ffmpeg} --dir {BOX_DIR} "
                      f"--suite {args.suite}" + (f" --only '{args.only}'" if args.only else "") +
                      (f" --skip '{args.skip}'" if args.skip else "") +
                      (f" --after {','.join(after)}" if after else ""))
            p = subprocess.Popen(ssh + [remote], stdout=subprocess.PIPE, text=True)
            started, finished = None, False
            for line in p.stdout:
                rec = json.loads(line)
                if "start" in rec:
                    started = rec["start"]
                    continue
                finished = finished or rec.get("done", False)
                if "kernel" in rec and "engine" in rec and records:
                    continue
                save(rec)
                if "suite" in rec:
                    print(f"{rec['suite']:6} {rec['codec']:8} {rec['size']:10} {rec['verdict']:9} "
                          f"{rec.get('fps') or '':>6} {rec.get('cpu_fps') or '':>6} {rec.get('psnr_y') or ''}", flush=True)
            p.wait()
            if finished or not started:
                break
            # the box went away mid-case: a hang its watchdog reset, or worse; wait for it, go on
            suite, codec, size = started
            save({"suite": suite, "codec": codec, "size": size, "verdict": "hang"})
            print(f"{suite:6} {codec:8} {size:10} hang, waiting for the box", flush=True)
            after.append(f"{suite}:{codec}")
            for _ in range(60):
                time.sleep(10)
                if subprocess.run(ssh[:-1] + ["-o", "ConnectTimeout=5", args.box, "true"]).returncode == 0:
                    break
            else:
                sys.exit("the box did not come back")
        print(f"saved {out}")
    finally:
        try:
            subprocess.run(ssh + [f"rm -rf -- {BOX_DIR}"], timeout=10, check=True)
        except (subprocess.SubprocessError, OSError) as error:
            print(f"cleanup needed on box: {BOX_DIR}: {error}", file=sys.stderr)


def load(path):
    records = json.loads(Path(path).read_text())
    return records[0], [r for r in records if "suite" in r]


def cmd_report(args):
    head, cases = load(args.run)
    print(f"{head['engine']} on {head['kernel']}, {head['ffmpeg']}\n")
    for suite in ("decode", "scale", "encode"):
        rows = [c for c in cases if c["suite"] == suite]
        if not rows:
            continue
        useful = "Beats the CPU" if suite == "encode" else f"At {PLAYABLE_FPS} fps"
        print(f"## {suite}\n\n| Codec | Largest passing | fps | {useful} | Past it |\n"
              "| --- | --- | --: | --- | --- |")
        for codec in dict.fromkeys(c["codec"] for c in rows):
            mine = sorted((c for c in rows if c["codec"] == codec), key=lambda c: pixels(c["size"]))
            ok = [c for c in mine if c["verdict"] == "pass"]
            best = ok[-1] if ok else None
            past = [c for c in mine if best and pixels(c["size"]) > pixels(best["size"])] or \
                   ([] if best else mine)
            top = mine[-1]["size"] == best["size"] if best else False
            cell = (f"{best['size']} → {best['out']}" if suite == "scale" else
                    ("≥ " if top else "") + best["size"]) if best else "—"
            if best and best.get("checked"):
                cell += f" ({best['checked']} only)"
            reasons = ", ".join(f"{c['size']} {c['verdict']}" for c in past[:3])
            useful = [c["size"] for c in ok if useful_rate(c)]
            print(f"| {codec} | {cell} | {(best or {}).get('fps') or ''} | {(useful or ['—'])[-1]} | {reasons} |")
        print()


def useful_rate(c):
    """A decoder plays a film; an encoder beats the CPU."""
    if c["suite"] == "encode":
        return not c.get("cpu_fps") or (c.get("fps") or 0) > c["cpu_fps"]
    return (c.get("fps") or 0) >= PLAYABLE_FPS


MARK = {"pass": "✅", "full": "▢", "refused": "↷", "broken": "❌", "flaky": "⚠", "unoffered": "·", "hang": "💥", "software": "🖥",
        "skipped": "⏭"}


def cmd_matrix(args):
    """Every case as a grid, one table a suite, to publish in a board's board.md."""
    head, cases = load(args.run)
    print(f"{head['kernel']}, {head['ffmpeg'].split(' Copyright')[0]}\n")
    for suite in ("decode", "scale", "encode"):
        rows = [c for c in cases if c["suite"] == suite]
        if not rows:
            continue
        sizes = sorted({c["size"] for c in rows}, key=pixels)
        print(f"| {suite} | " + " | ".join(sizes) + " |")
        print("| --- |" + " :-: |" * len(sizes))
        for codec in dict.fromkeys(c["codec"] for c in rows):
            got = {c["size"]: c for c in rows if c["codec"] == codec}
            cell = lambda c: "" if not c else " ".join(
                ["🟠" if c["verdict"] == "pass" and c.get("fps") and not useful_rate(c) else MARK[c["verdict"]]] +
                [str(c[k]) for k in ("out", "fps") if c.get(k)] + ([f"/ {c['cpu_fps']}"] if c.get("cpu_fps") else []))
            print(f"| {codec} | " + " | ".join(cell(got.get(s)) for s in sizes) + " |")
        print()
    print("✅ matches software · ❌ broken · ↷ refused, plays on the CPU · ▢ not shrunk, full size · "
          "⚠ differs run to run · 💥 hung the box · ⏭ skipped, known to hang · 🖥 decoded on the CPU · · not offered · "
          f"🟠 decodes under {PLAYABLE_FPS} fps, or encodes slower than the CPU · a number: frames a second, "
          "an encoder's against the CPU's")


def key(c):
    return (c["suite"], c["codec"], c["size"])


def cmd_compare(args):
    _, old = load(args.old)
    _, new = load(args.new)
    before = {key(c): c for c in old}
    rank = {"pass": 3, "full": 2, "refused": 2, "unoffered": 1, "flaky": 1, "broken": 0, "hang": -1, "software": 1}
    worse = []
    for c in new:
        o = before.get(key(c))
        if not o or c["verdict"] == "skipped":
            continue
        if rank.get(c["verdict"], 0) < rank.get(o["verdict"], 0):
            worse.append(f"{' '.join(key(c))}: {o['verdict']} -> {c['verdict']}")
        elif o.get("psnr_y") and c.get("psnr_y") and c["psnr_y"] < o["psnr_y"] - 1:
            worse.append(f"{' '.join(key(c))}: {o['psnr_y']:.1f} -> {c['psnr_y']:.1f} dB")
    print("\n".join(worse) or "nothing worse")
    sys.exit(1 if worse else 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("clips")
    for name in ("run", "box"):
        p = sub.add_parser(name)
        p.add_argument("--engine", choices=ENGINES, required=True)
        p.add_argument("--ffmpeg", default="ffmpeg")
        p.add_argument("--suite", default="decode,scale,encode")
        p.add_argument("--only", help="a regex over <codec>-<size>")
        p.add_argument("--skip", help="a regex over <suite>:<codec>-<size>: cases known to hang, recorded, not run")
        if name == "run":
            p.add_argument("--box", required=True)
            p.add_argument("--out")
        else:
            p.add_argument("--dir", required=True)
            p.add_argument("--after", help="suite:codec pairs already run, comma-separated")
    sub.add_parser("report").add_argument("run")
    sub.add_parser("matrix").add_argument("run")
    p = sub.add_parser("compare")
    p.add_argument("old")
    p.add_argument("new")
    args = ap.parse_args()
    {"clips": cmd_clips, "run": cmd_run, "box": cmd_box, "report": cmd_report, "matrix": cmd_matrix,
     "compare": cmd_compare}[args.cmd](args)


if __name__ == "__main__":
    main()
