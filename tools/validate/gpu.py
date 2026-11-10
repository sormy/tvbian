#!/usr/bin/env python3
"""The GPU draws right, not only fast: Mesa CI's GLES conformance.

From the host, in the repo checkout, after ./build.sh extra deqp, which makes the deqp package
this installs on the box:

    python3 tools/validate/gpu.py --box root@<box> --gpu g52 [--fraction 20]

Runs dEQP's GLES 2, 3 and 3.1 and Khronos lists through deqp-runner on 256x256 pbuffers, as
Mesa's CI does, every --fraction'th case. The baseline is Mesa's own CI expectations for --gpu
(fails, flakes, skips) at the Mesa version the box runs: a failure Mesa expects passes, any other
fails the run. glmark2's --validate is no check here: on DRM its surface is always fullscreen, and
llvmpipe fails the same scenes. Exit 0 nothing unexpected, 1 otherwise.
"""

import argparse
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "build" / "out" / "debs"
DEQP_DIR = "/usr/lib/deqp"
BOX_DIR = "/var/tmp/tvb-gpu"
MESA_CI = "https://gitlab.freedesktop.org/mesa/mesa/-/raw/mesa-{version}/src/panfrost/ci/panfrost-{gpu}-{kind}.txt"
SURFACE = [
    "--deqp-surface-width=256",
    "--deqp-surface-height=256",
    "--deqp-surface-type=pbuffer",
    "--deqp-visibility=hidden",
    "--deqp-gl-config-name=rgba8888d24s8ms0",
]
SUITE = [
    ("gles2/deqp-gles2", ["gles2-main.txt"]),
    ("gles3/deqp-gles3", ["gles3-main.txt"]),
    ("gles31/deqp-gles31", ["gles31-main.txt"]),
    ("glcts/glcts", ["gles2-khr-main.txt", "gles3-khr-main.txt", "gles31-khr-main.txt"]),
]


def ssh(box, cmd, check=True):
    return subprocess.run(
        ["ssh", "-o", "BatchMode=yes", box, cmd],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=check,
        stdin=subprocess.DEVNULL,
    ).stdout


def expectations(version, gpu, kind):
    """Mesa CI's list for the GPU at this Mesa version; empty where Mesa keeps none."""
    try:
        with urllib.request.urlopen(
            MESA_CI.format(version=version, gpu=gpu, kind=kind), timeout=30
        ) as r:
            return r.read().decode()
    except OSError:
        return ""


def suite_toml(fraction):
    entries = []
    for binary, lists in SUITE:
        caselists = ", ".join(f'"{DEQP_DIR}/mustpass/{c}"' for c in lists)
        args = ", ".join(f'"{a}"' for a in SURFACE)
        entries.append(
            f'[[deqp]]\ndeqp = "{DEQP_DIR}/{binary}"\ncaselists = [{caselists}]\n'
            f"deqp_args = [{args}]\nfraction = {fraction}\n"
        )
    return "\n".join(entries)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--box", required=True)
    ap.add_argument(
        "--gpu", required=True, help="Mesa CI's name for the nearest GPU it tests, e.g. g52"
    )
    ap.add_argument("--fraction", type=int, default=20, help="run every N'th case")
    args = ap.parse_args()
    debs = sorted(OUT.glob("deqp_*_arm64.deb"))
    if not debs:
        sys.exit("no deqp package: run ./build.sh extra deqp")
    deb = debs[-1]

    version = ssh(args.box, "dpkg-query -W -f '${Version}' libgbm1").split("-")[0]
    print(f"Mesa {version}, baseline panfrost-{args.gpu}, every {args.fraction}th case")
    want = deb.name.split("_")[1]
    if ssh(args.box, "dpkg-query -W -f '${Version}' deqp 2>/dev/null", check=False) != want:
        subprocess.run(["scp", "-q", str(deb), f"{args.box}:/var/tmp/"], check=True)
        print(
            ssh(
                args.box,
                f"apt-get install -y -qq --allow-downgrades /var/tmp/{deb.name} >/dev/null && rm /var/tmp/{deb.name} "
                f"&& echo installed {want}",
            )
        )
    ssh(args.box, f"rm -rf {BOX_DIR} && mkdir -p {BOX_DIR}")
    for kind in ("fails", "flakes", "skips"):
        subprocess.run(
            ["ssh", "-o", "BatchMode=yes", args.box, f"cat > {BOX_DIR}/{kind}.txt"],
            input=expectations(version, args.gpu, kind),
            text=True,
            check=True,
        )
    subprocess.run(
        ["ssh", "-o", "BatchMode=yes", args.box, f"cat > {BOX_DIR}/suite.toml"],
        input=suite_toml(args.fraction),
        text=True,
        check=True,
    )

    # Mesa's default EGL platform is X11; the surfaceless target needs it named, as Mesa CI does
    out = ssh(
        args.box,
        f"cd {BOX_DIR} && EGL_PLATFORM=surfaceless {DEQP_DIR}/deqp-runner suite --suite suite.toml "
        f"--output results --baseline fails.txt --flakes flakes.txt --skips skips.txt "
        f"--jobs 4 2>&1 | tail -25",
        check=False,
    )
    print(out)
    unexpected = ssh(
        args.box,
        f"grep -vE ',(Pass|Skip|ExpectedFail|Flake|KnownFlake)' "
        f"{BOX_DIR}/results/failures.csv 2>/dev/null || true",
        check=False,
    ).strip()
    failed = bool(unexpected) or "Error:" in out
    if unexpected:
        print("unexpected:\n" + unexpected)
    print("FAIL" if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
