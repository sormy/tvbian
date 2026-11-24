#!/usr/bin/env python3
"""A session package checked in a clean Debian before a box sees it, and on a box that runs it.

In the build container, from `./build.sh session-check <name>`: installed with what it depends on
from /out/debs (the session's, `whitesur-theme`, `tvb-va-driver`), its labwc started headless
on the CPU renderer, and its defaults, panels and switch checked.

On a box, from tools/validate/desktop.py, with `--box --clips DIR`: the same in a headless labwc of
its own, then the logged-in session as it runs: its panels, renderer, scale, idle cost and video;
with nobody logged in, the video in a headless labwc on the GPU as the box's desktop user.

Prints `session.<check> verdict` lines; exits 1 on any failure.
"""

from __future__ import annotations

import argparse
import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import tomllib
import xml.etree.ElementTree as ElementTree
from collections.abc import Callable, Iterator
from pathlib import Path
from types import ModuleType

DEBS = Path("/out/debs")
XDG_CONFIG = Path("/etc/xdg/labwc")
SHARE = Path("/usr/share/tvb-desktop")
# pipewire-alsa's: ALSA's default would go to a PipeWire that only runs in a session
ALSA_TO_PIPEWIRE = Path("/usr/share/alsa/alsa.conf.d/99-pipewire-default.conf")
FIRST_ACCOUNT = "tvb-check-first"
DESKTOP_GROUPS = {"audio", "video", "render", "input"}
RUNTIME = Path("/tmp/tvb-session-check")
HEADLESS_RUNTIME = Path("/tmp/tvb-session-check-headless")
INTERFACE = "org.gnome.desktop.interface"
DARK = {
    "gtk-theme": "'WhiteSur-Dark'",
    "icon-theme": "'WhiteSur-dark'",
    "cursor-theme": "'WhiteSur-cursors'",
    "color-scheme": "'prefer-dark'",
    "font-name": "'Inter 10'",
}
LIGHT = {
    "gtk-theme": "'WhiteSur-Light'",
    "icon-theme": "'WhiteSur-light'",
    "color-scheme": "'prefer-light'",
}
# autostart's programs, and how many of each; lxpolkit needs the system bus a container lacks
PANELS = {"waybar": 2, "swaybg": 1, "mako": 1, "swayidle": 1}
# what the check needs beyond the session's own depends
TOOLS = ["dbus-daemon", "dbus-bin", "debconf-utils"]
SETTLE_S = 10
POLL_S = 0.5
# regular accounts, as Debian numbers them
FIRST_UID, LAST_UID = 1000, 60000
# a picture of the bar, the dock and the gradient: a flat or empty screen has a handful
MIN_COLOURS = 64
CASE_TIMEOUT = 300
REPORT_PREFIX = "session."
SCALE_OUTPUTS = Path("/usr/libexec/tvb-desktop/scale-outputs")
# a compositor on the GPU maps Mesa's driver; pixman maps neither
GPU_LIBRARIES = ("libgallium", "_dri.so")
IDLE_S = 30
# the whole session at rest: labwc, the bar, the dock and the daemons
IDLE_CPU_MAX = 10.0
# /proc/<pid>/stat after the command's closing parenthesis, counted from 0
UTIME_FIELD, STIME_FIELD = 11, 12
# of a clip's length, both its position at the end and the time it took
PLAYED_SHARE = 0.95
# of the frames a clip shows once playing, the share mpv may drop
DROP_MAX = 0.01
# going full screen drops a handful: judged apart
WARMUP_S = 1.0

Line = tuple[str, str]


def run(cmd: list[str], env: dict[str, str] | None = None) -> tuple[int, str]:
    try:
        done = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, timeout=CASE_TIMEOUT
        )
    except subprocess.TimeoutExpired:
        return -1, "timed out"
    return done.returncode, done.stdout.decode(errors="replace")


def last_line(text: str) -> str:
    lines = [line for line in text.strip().splitlines() if line.strip()]
    return lines[-1][:160] if lines else "no output"


def wait_for(ready: Callable[[], bool]) -> bool:
    deadline = time.monotonic() + SETTLE_S
    while time.monotonic() < deadline:
        if ready():
            return True
        time.sleep(POLL_S)
    return ready()


def install(name: str) -> Iterator[Line]:
    debs = [
        next(iter(sorted(DEBS.glob(pattern))), None)
        for pattern in (f"tvb-{name}_*.deb", "whitesur-theme_*.deb", "tvb-va-driver_*.deb")
    ]
    missing = [p for p, deb in zip(("session", "whitesur-theme", "tvb-va-driver"), debs) if not deb]
    if missing:
        yield "install", f"failed: no {', '.join(missing)} in {DEBS}: build them first"
        return
    run(["apt-get", "update", "-qq"])
    env = dict(os.environ, DEBIAN_FRONTEND="noninteractive")
    # the session's apps, as --install-recommends gives them; not its depends' recommends
    _, recommends = run(["dpkg-deb", "-f", str(debs[0]), "Recommends"])
    apps = [name.strip() for name in recommends.split(",") if name.strip()]
    rc, log = run(
        ["apt-get", "install", "-y", "-qq", "--no-install-recommends"]
        + [str(deb) for deb in debs if deb]
        + apps
        + TOOLS,
        env,
    )
    yield "install", "pass" if rc == 0 else f"failed: {last_line(log)}"


def configs() -> Iterator[Line]:
    greeter = SHARE / "greeter"
    for path in (
        XDG_CONFIG / "rc.xml",
        XDG_CONFIG / "menu.xml",
        greeter / "rc.xml",
        greeter / "menu.xml",
    ):
        key = f"config.{'greeter.' if path.parent == greeter else ''}{path.name}"
        try:
            ElementTree.parse(path)
            yield key, "pass"
        except (OSError, ElementTree.ParseError) as error:
            yield key, f"failed: {error}"
    greeter = tomllib.loads((SHARE / "greetd.toml").read_text())["default_session"]["command"]
    absent = [path for path in re.findall(r"/[\w./-]+", greeter) if not Path(path).exists()]
    absent += [p for p in ("labwc", "gtkgreet") if not shutil.which(p)]
    yield "config.greetd", "pass" if not absent else f"failed: no {', '.join(absent)}"
    rc, log = run(
        ["mpv", "--no-config", "--include=/etc/mpv/mpv.conf", "--vo=null", "--ao=null"]
        + ["--frames=3", "av://lavfi:testsrc"]
    )
    yield "config.mpv", "pass" if rc == 0 else f"failed: {last_line(log)}"


def settings(env: dict[str, str], expected: dict[str, str], key: str) -> Line:
    wrong = []
    for name, value in expected.items():
        _, got = run(["gsettings", "get", INTERFACE, name], env)
        if got.strip() != value:
            wrong.append(f"{name} {got.strip()}")
    return key, "pass" if not wrong else f"failed: {'; '.join(wrong)}"


def counts(names: dict[str, int], user: str = "root") -> dict[str, int]:
    return {name: len(run(["pgrep", "-u", user, "-x", name])[1].split()) for name in names}


class Session:
    """labwc headless on the CPU renderer, with its own session bus and runtime directory."""

    def __init__(self) -> None:
        RUNTIME.mkdir(mode=0o700, exist_ok=True)
        rc, printed = run(["dbus-daemon", "--session", "--fork", "--print-address", "--print-pid"])
        address, bus_pid = printed.strip().splitlines()[:2]
        self.bus_pid = int(bus_pid)
        self.env = dict(
            os.environ,
            XDG_RUNTIME_DIR=str(RUNTIME),
            DBUS_SESSION_BUS_ADDRESS=address,
            WLR_BACKENDS="headless",
            WLR_RENDERER="pixman",
            WLR_LIBINPUT_NO_DEVICES="1",
        )
        self.labwc = subprocess.Popen(
            ["labwc"], env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )
        wait_for(lambda: any(RUNTIME.glob("wayland-*")))
        socket = next(iter(sorted(p.name for p in RUNTIME.glob("wayland-?"))), "wayland-0")
        self.env.update(WAYLAND_DISPLAY=socket, LABWC_PID=str(self.labwc.pid))

    def close(self) -> str:
        self.labwc.terminate()
        _, errors = self.labwc.communicate(timeout=CASE_TIMEOUT)
        # autostart's programs outlive labwc; nothing else on a box runs them as root
        for name in list(PANELS) + ["lxpolkit"]:
            run(["pkill", "-u", "root", "-x", name])
        os.kill(self.bus_pid, signal.SIGTERM)
        return errors.decode(errors="replace")


def panels() -> Line:
    wait_for(lambda: counts(PANELS) == PANELS)
    got = counts(PANELS)
    wrong = [f"{name} {got[name]} of {n}" for name, n in PANELS.items() if got[name] != n]
    return "headless.autostart", "pass" if not wrong else f"failed: {'; '.join(wrong)}"


def waybar_style() -> str:
    _, listing = run(["pgrep", "-u", "root", "-a", "-x", "waybar"])
    styles = {word for word in listing.split() if word.endswith(".css")}
    return " ".join(sorted(Path(s).name for s in styles))


def appearance(session: Session) -> Iterator[Line]:
    override = Path.home() / ".config/labwc/themerc-override"
    rc, log = run(["tvb-appearance", "light"], session.env)
    if rc != 0:
        yield "appearance.light", f"failed: {last_line(log)}"
        return
    yield settings(session.env, LIGHT, "appearance.light")
    yield "appearance.light.labwc", "pass" if override.exists() else "failed: no themerc-override"
    wait_for(lambda: waybar_style() == "light.css" and counts({"waybar": 2})["waybar"] == 2)
    style = waybar_style()
    yield "appearance.light.panels", (
        "pass" if style == "light.css" else f"failed: {style or 'none'}"
    )
    run(["tvb-appearance", "dark"], session.env)
    yield settings(session.env, DARK, "appearance.dark")
    yield "appearance.dark.labwc", "failed: themerc-override left" if override.exists() else "pass"


def scale(session: Session) -> Line:
    rc, log = run(["wlr-randr"], session.env)
    scaled = "Scale: 1.000000" in log
    return "headless.scale", "pass" if rc == 0 and scaled else f"failed: {last_line(log)}"


def colours_of_ppm(data: bytes) -> int:
    """Distinct colours in a binary P6 picture, every 16th pixel."""
    header, _, rest = data.partition(b"\n255\n")
    width, height = (int(n) for n in header.split()[1:3])
    pixels = rest[: width * height * 3]
    return len({pixels[i : i + 3] for i in range(0, len(pixels), 3 * 16)})


def screenshot(session: Session) -> Line:
    """Retaken until the panels have drawn: their processes start before their first frame."""
    shot = RUNTIME / "shot.ppm"
    log = ""
    colours = 0

    def drawn() -> bool:
        nonlocal log, colours
        rc, log = run(["grim", "-t", "ppm", str(shot)], session.env)
        colours = colours_of_ppm(shot.read_bytes()) if rc == 0 and shot.exists() else 0
        return colours >= MIN_COLOURS

    if wait_for(drawn):
        return "headless.screenshot", f"pass: {colours} colours"
    if not shot.exists():
        return "headless.screenshot", f"failed: {last_line(log)}"
    return "headless.screenshot", f"failed: {colours} colours"


class Live:
    """The session a user logged into: its labwc, and the environment its clients get."""

    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.user = Path(f"/proc/{pid}").owner()
        environ = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
        found = dict(e.decode().split("=", 1) for e in environ if b"=" in e)
        runtime = Path(found.get("XDG_RUNTIME_DIR", ""))
        socket = next(iter(sorted(p.name for p in runtime.glob("wayland-?"))), "")
        self.env = {
            "XDG_RUNTIME_DIR": str(runtime),
            "WAYLAND_DISPLAY": socket,
            "DBUS_SESSION_BUS_ADDRESS": found.get("DBUS_SESSION_BUS_ADDRESS", ""),
            "HOME": f"/home/{self.user}",
        }
        # GStreamer's decoders as the session chose them: tvb-va-driver's, or not on meson
        self.env |= {k: v for k, v in found.items() if k.startswith("GST_")}

    def run(self, cmd: list[str]) -> tuple[int, str]:
        settings = [f"{k}={v}" for k, v in self.env.items()]
        return run(["runuser", "-u", self.user, "--", "env"] + settings + cmd)


def logged_in() -> Live | None:
    _, listing = run(["pgrep", "-x", "labwc"])
    users = [int(pid) for pid in listing.split() if Path(f"/proc/{pid}").owner() != "root"]
    return Live(users[0]) if users else None


def scale_outputs() -> ModuleType:
    loader = importlib.machinery.SourceFileLoader("scale_outputs", str(SCALE_OUTPUTS))
    spec = importlib.util.spec_from_loader("scale_outputs", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def live_scale(live: Live) -> Line:
    rc, listing = live.run(["wlr-randr", "--json"])
    if rc != 0:
        return "live.scale", f"failed: {last_line(listing)}"
    rule = scale_outputs()
    heads = json.loads(listing)
    wrong = [
        f"{output.name} {head['scale']}, not {output.scale()}"
        for head in heads
        for output in rule.enabled_outputs([head])
        if head["scale"] != output.scale()
    ]
    return "live.scale", "pass" if not wrong else f"failed: {'; '.join(wrong)}"


def live_renderer(live: Live) -> Line:
    maps = Path(f"/proc/{live.pid}/maps").read_text()
    on_gpu = any(library in maps for library in GPU_LIBRARIES)
    return "live.renderer", "pass: the GPU" if on_gpu else "failed: no GPU driver mapped"


def cpu_ticks(user: str) -> int:
    total = 0
    for stat in Path("/proc").glob("[0-9]*/stat"):
        try:
            if stat.parent.owner() != user:
                continue
            fields = stat.read_text().rsplit(")", 1)[1].split()
        except (OSError, KeyError):
            continue
        total += int(fields[UTIME_FIELD]) + int(fields[STIME_FIELD])
    return total


def live_idle(live: Live) -> Line:
    before = cpu_ticks(live.user)
    time.sleep(IDLE_S)
    used = (cpu_ticks(live.user) - before) / os.sysconf("SC_CLK_TCK") / IDLE_S * 100
    meminfo = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
    in_use = (int(meminfo["MemTotal"].split()[0]) - int(meminfo["MemAvailable"].split()[0])) // 1024
    verdict = "pass" if used <= IDLE_CPU_MAX else "failed"
    return "live.idle", f"{verdict}: {used:.1f} % of a core over {IDLE_S} s, {in_use} MiB in use"


def live_playback(live: Live, clip: Path, where: str) -> Line:
    """Played to its end in real time; frames dropped once playing, judged; those dropped while
    going full screen, reported."""
    key = f"{where}.playback.{clip.stem}"
    status = "STATUS ${=time-pos} ${hwdec-current} ${estimated-frame-count} ${frame-drop-count}"
    status += " ${=duration}"
    started = time.monotonic()
    rc, log = live.run(["mpv", "--fs", "--ao=null", f"--term-status-msg={status}", str(clip)])
    wall = time.monotonic() - started
    samples = [
        line.split()[1:]
        for line in log.replace("\r", "\n").splitlines()
        if line.startswith("STATUS ") and len(line.split()) == 6
    ]
    if rc != 0 or not samples:
        return key, f"failed: {last_line(log)}"
    position, hwdec, frames, dropped, duration = samples[-1]
    if hwdec != "vaapi":
        return key, f"failed: decoded by {hwdec}, not vaapi"
    length = float(duration) * PLAYED_SHARE
    if float(position) < length or wall < length:
        return (
            key,
            f"failed: played {float(position):.1f} of {float(duration):.1f} s in {wall:.1f} s",
        )
    warm = next((int(s[3]) for s in samples if float(s[0]) >= WARMUP_S), int(dropped))
    steady = int(dropped) - warm
    verdict = "pass" if steady <= int(frames) * DROP_MAX else "failed"
    return key, f"{verdict}: {steady} of {frames} dropped, {warm} going full screen"


def desktop_user() -> str | None:
    """The box's first account with a home: who a desktop session runs as."""
    for entry in Path("/etc/passwd").read_text().splitlines():
        name, _, uid, _, _, home, _ = entry.split(":")
        if FIRST_UID <= int(uid) < LAST_UID and Path(home).is_dir():
            return name
    return None


class HeadlessLive:
    """labwc headless on the GPU as a user, with a bus of its own: a logged-in session's stand-in."""

    def __init__(self, user: str) -> None:
        HEADLESS_RUNTIME.mkdir(mode=0o700, exist_ok=True)
        shutil.chown(HEADLESS_RUNTIME, user)
        env = {
            "XDG_RUNTIME_DIR": str(HEADLESS_RUNTIME),
            "WLR_BACKENDS": "headless",
            "WLR_RENDERER": "gles2",
            "WLR_HEADLESS_OUTPUTS": "1",
            "WLR_LIBINPUT_NO_DEVICES": "1",
        }
        command = ["runuser", "-u", user, "--", "env", *[f"{k}={v}" for k, v in env.items()]]
        self.process = subprocess.Popen(
            [*command, "dbus-run-session", "--", "labwc"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        wait_for(lambda: any(HEADLESS_RUNTIME.glob("wayland-?")))
        _, listing = run(["pgrep", "-u", user, "-x", "labwc"])
        self.live = Live(int(listing.split()[0])) if listing.split() else None

    def close(self) -> None:
        os.killpg(self.process.pid, signal.SIGTERM)
        self.process.wait(timeout=CASE_TIMEOUT)
        shutil.rmtree(HEADLESS_RUNTIME, ignore_errors=True)


def headless_playback(clips: Path) -> Iterator[Line]:
    user = desktop_user()
    if user is None:
        yield "headless", "not run: nobody is logged in, and the box has no desktop user"
        return
    session = HeadlessLive(user)
    try:
        if session.live is None:
            yield "headless", f"failed: labwc did not start as {user}"
            return
        for clip in sorted(clips.glob("*.mp4")):
            yield live_playback(session.live, clip, "headless")
    finally:
        session.close()


def live_checks(clips: Path) -> Iterator[Line]:
    live = logged_in()
    if live is None:
        yield from headless_playback(clips)
        return
    want = dict(PANELS, lxpolkit=1)
    got = counts(want, live.user)
    wrong = [f"{name} {got[name]} of {n}" for name, n in want.items() if got[name] != n]
    yield "live.autostart", "pass" if not wrong else f"failed: {'; '.join(wrong)}"
    yield live_renderer(live)
    yield live_scale(live)
    yield live_idle(live)
    for clip in sorted(clips.glob("*.mp4")):
        yield live_playback(live, clip, "live")


def alsa_default() -> Line:
    present = ALSA_TO_PIPEWIRE.exists()
    return "config.alsa", "failed: ALSA's default goes to PipeWire" if present else "pass"


def first_account(name: str) -> Iterator[Line]:
    """The account the install asks for: made with the desktop's groups, its password not kept; asked
    only while the box has no regular account."""
    answers = f"tvb-{name} tvb-{name}/user-name string {FIRST_ACCOUNT}\n"
    answers += f"tvb-{name} tvb-{name}/user-password password check\n"
    run(["sh", "-c", f"printf '{answers}' | debconf-set-selections"])
    env = dict(os.environ, DEBIAN_FRONTEND="noninteractive")
    rc, log = run(["dpkg-reconfigure", f"tvb-{name}"], env)
    _, groups = run(["id", "-nG", FIRST_ACCOUNT])
    _, kept = run(["sh", "-c", f"debconf-show tvb-{name} | grep user-password"])
    missing = (DESKTOP_GROUPS & set(run(["getent", "group"])[1].replace(":", " ").split())) - set(
        groups.split()
    )
    if rc != 0 or not groups:
        yield "install.account", f"failed: {last_line(log)}"
    elif missing or "check" in kept:
        yield "install.account", f"failed: groups {groups.strip()}, password kept: {'check' in kept}"
    else:
        yield "install.account", "pass"
    run(
        [
            "sh",
            "-c",
            f"printf 'tvb-{name} tvb-{name}/user-name string tvb-check-second\\n' | debconf-set-selections",
        ]
    )
    run(["dpkg-reconfigure", f"tvb-{name}"], env)
    second = run(["id", "tvb-check-second"])[0] == 0
    yield "install.account.once", "failed: asked again with an account there" if second else "pass"
    run(["userdel", "-r", FIRST_ACCOUNT])


def check(name: str, clips: Path | None) -> Iterator[Line]:
    if clips is None:
        installed = list(install(name))
        yield from installed
        if any(verdict.startswith("failed") for _, verdict in installed):
            return
        yield from first_account(name)
    yield from configs()
    yield alsa_default()
    session = Session()
    try:
        yield settings(session.env, DARK, "settings.dark")
        yield panels()
        yield scale(session)
        yield screenshot(session)
        yield from appearance(session)
    finally:
        errors = session.close()
    theme_errors = [
        line for line in errors.splitlines() if "theme" in line.lower() and "rror" in line
    ]
    yield "headless.labwc", "pass" if not theme_errors else f"failed: {theme_errors[0][:160]}"
    if clips is not None:
        yield from live_checks(clips)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", help="the session: session/<name>/")
    parser.add_argument("--box", action="store_true", help="on a box that has it installed")
    parser.add_argument("--clips", type=Path, help="box: the clips mpv plays in the live session")
    args = parser.parse_args()
    if args.box and args.clips is None:
        parser.error("--box needs --clips")
    if args.box and not SHARE.exists():
        print(f"UNTESTED {REPORT_PREFIX}installed: tvb-{args.name} is not installed")
        return 0
    failures = 0
    for case, verdict in check(args.name, args.clips if args.box else None):
        # among other suites' lines in one report, these say they are the session's
        key = f"{REPORT_PREFIX}{case}"
        print(f"{key} {verdict}", flush=True)
        if verdict.startswith("failed"):
            print(f"FAIL {key}", flush=True)
            failures += 1
        elif verdict.startswith("not run"):
            print(f"UNTESTED {key}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
