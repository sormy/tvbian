#!/usr/bin/env python3
"""What the GPU puts on the screen, read back: on the box, as root, with nothing else on the display.

    python3 screen.py

Renders deterministic frames at the display's mode with GLES2 on GBM, each about 48,000 small
triangles over the whole screen, puts each on a plane by an atomic commit and captures the scanout
by writeback; then renders the same frames with llvmpipe the same way. Checks, frame by frame:
the GPU's capture matches llvmpipe's, each frame differs from the one before, and the kernel logs
no GPU job timeout or fault. Exit 0 all passed, 1 a failure, 77 nothing to check.
"""

import ctypes
import math
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import display  # noqa: E402

FRAMES = 3
GRID = (200, 120)  # cells across and down, two triangles each
SAME_FLOOR = 0.999  # share of pixels that must match llvmpipe exactly
OUT = Path("/var/tmp/tvb-screen")
GBM_FORMAT_XRGB8888 = display.XRGB8888
GBM_BO_USE_SCANOUT, GBM_BO_USE_RENDERING = 1, 4
EGL_PLATFORM_GBM_KHR, EGL_OPENGL_ES_API = 0x31D7, 0x30A0
EGL_NATIVE_VISUAL_ID, EGL_NONE = 0x302E, 0x3038
CONFIG = [0x3033, 4, 0x3024, 8, 0x3023, 8, 0x3022, 8, 0x3021, 0, 0x3040, 4, EGL_NONE]
CONTEXT = [0x3098, 2, EGL_NONE]
GL_VERTEX_SHADER, GL_FRAGMENT_SHADER, GL_FLOAT, GL_TRIANGLES = 0x8B31, 0x8B30, 0x1406, 0x0004
GL_COLOR_BUFFER_BIT = 0x4000

VERTEX = b"""attribute vec2 pos; attribute float id; uniform float frame; varying vec3 colour;
void main() {
    float c = id * 37.0 + frame * 11.0;
    colour = vec3(mod(c, 256.0), mod(c * 3.0, 256.0), mod(c * 7.0 + 128.0, 256.0)) / 255.0;
    gl_Position = vec4(pos, 0.0, 1.0);
}"""
FRAGMENT = b"""precision highp float; varying vec3 colour;
void main() { gl_FragColor = vec4(colour, 1.0); }"""


class Gbm:
    """The GPU's frames, rendered by GLES2 into a GBM surface the display can scan out."""

    def __init__(self, fd, width, height):
        gbm, egl = ctypes.CDLL("libgbm.so.1"), ctypes.CDLL("libEGL.so.1")
        self.gl = ctypes.CDLL("libGLESv2.so.2")
        self.gbm, self.egl = gbm, egl
        for f in ("gbm_create_device", "gbm_surface_create", "gbm_surface_lock_front_buffer"):
            getattr(gbm, f).restype = ctypes.c_void_p
        gbm.gbm_bo_get_handle.restype = ctypes.c_uint64
        egl.eglGetPlatformDisplay.restype = egl.eglCreateContext.restype = ctypes.c_void_p
        egl.eglCreateWindowSurface.restype = ctypes.c_void_p
        self.device = gbm.gbm_create_device(fd)
        self.surface = gbm.gbm_surface_create(
            ctypes.c_void_p(self.device),
            width,
            height,
            GBM_FORMAT_XRGB8888,
            GBM_BO_USE_SCANOUT | GBM_BO_USE_RENDERING,
        )
        self.dpy = ctypes.c_void_p(
            egl.eglGetPlatformDisplay(EGL_PLATFORM_GBM_KHR, ctypes.c_void_p(self.device), None)
        )
        egl.eglInitialize(self.dpy, None, None)
        egl.eglBindAPI(EGL_OPENGL_ES_API)
        configs, n = (ctypes.c_void_p * 64)(), ctypes.c_int()
        egl.eglChooseConfig(
            self.dpy, (ctypes.c_int * len(CONFIG))(*CONFIG), configs, 64, ctypes.byref(n)
        )
        visual = ctypes.c_int()
        config = next(
            c
            for c in configs[: n.value]
            if egl.eglGetConfigAttrib(
                self.dpy, ctypes.c_void_p(c), EGL_NATIVE_VISUAL_ID, ctypes.byref(visual)
            )
            and visual.value == GBM_FORMAT_XRGB8888
        )
        context = egl.eglCreateContext(
            self.dpy, ctypes.c_void_p(config), None, (ctypes.c_int * 3)(*CONTEXT)
        )
        self.window = ctypes.c_void_p(
            egl.eglCreateWindowSurface(
                self.dpy, ctypes.c_void_p(config), ctypes.c_void_p(self.surface), None
            )
        )
        egl.eglMakeCurrent(self.dpy, self.window, self.window, ctypes.c_void_p(context))
        self.program = self.link()
        self.gl.glViewport(0, 0, width, height)
        self.vertices(*GRID)

    def link(self):
        gl = self.gl
        program = gl.glCreateProgram()
        for kind, source in ((GL_VERTEX_SHADER, VERTEX), (GL_FRAGMENT_SHADER, FRAGMENT)):
            shader = gl.glCreateShader(kind)
            gl.glShaderSource(shader, 1, ctypes.byref(ctypes.c_char_p(source)), None)
            gl.glCompileShader(shader)
            gl.glAttachShader(program, shader)
        gl.glLinkProgram(program)
        gl.glUseProgram(program)
        return program

    def vertices(self, cols, rows):
        """Two triangles a cell, each cell its own id: every primitive the tiler bins is small."""
        pos, ids = [], []
        for r in range(rows):
            for c in range(cols):
                x0, x1 = c * 2 / cols - 1, (c + 1) * 2 / cols - 1
                y0, y1 = r * 2 / rows - 1, (r + 1) * 2 / rows - 1
                pos += [x0, y0, x1, y0, x1, y1, x0, y0, x1, y1, x0, y1]
                ids += [r * cols + c] * 6
        self.count = len(ids)
        self.pos, self.ids = (ctypes.c_float * len(pos))(*pos), (ctypes.c_float * len(ids))(*ids)
        for name, data, size in ((b"pos", self.pos, 2), (b"id", self.ids, 1)):
            loc = self.gl.glGetAttribLocation(self.program, name)
            self.gl.glVertexAttribPointer(loc, size, GL_FLOAT, 0, 0, data)
            self.gl.glEnableVertexAttribArray(loc)

    def frame(self, k):
        gl = self.gl
        gl.glClearColor(ctypes.c_float(0), ctypes.c_float(0), ctypes.c_float(0), ctypes.c_float(1))
        gl.glClear(GL_COLOR_BUFFER_BIT)
        gl.glUniform1f(gl.glGetUniformLocation(self.program, b"frame"), ctypes.c_float(k))
        gl.glDrawArrays(GL_TRIANGLES, 0, self.count)
        self.egl.eglSwapBuffers(self.dpy, self.window)
        return self.gbm.gbm_surface_lock_front_buffer(ctypes.c_void_p(self.surface))

    def release(self, bo):
        self.gbm.gbm_surface_release_buffer(ctypes.c_void_p(self.surface), ctypes.c_void_p(bo))


class Scanout:
    """A GBM buffer as a framebuffer the display takes, shaped as display.Buffer."""

    def __init__(self, box, gbm, bo, width, height):
        self.width, self.height, self.format = width, height, GBM_FORMAT_XRGB8888
        cmd = display.FbCmd2(width=width, height=height, pixel_format=GBM_FORMAT_XRGB8888)
        cmd.handles[0] = gbm.gbm.gbm_bo_get_handle(ctypes.c_void_p(bo)) & 0xFFFFFFFF
        cmd.pitches[0] = gbm.gbm.gbm_bo_get_stride(ctypes.c_void_p(bo))
        self.fb = box.drm.call("addfb2", cmd).fb_id


def render(tag):
    """One renderer's captures, a file a frame, under OUT."""
    box = display.Box()
    if box.crtc is None or not box.writeback:
        print("SKIP screen: no active CRTC or no writeback connector")
        return 77
    width, height = box.mode.hdisplay, box.mode.vdisplay
    capture = box.capture_buffer()
    gbm = Gbm(box.drm.fd, width, height)
    renderer = ctypes.string_at(gbm.gl.glGetString(0x1F01)).decode()
    for k in range(FRAMES):
        bo = gbm.frame(k)
        error = box.compose(
            [(box.planes[0], Scanout(box, gbm, bo, width, height), (0, 0, width, height), {})],
            capture,
        )
        (OUT / f"{tag}-{k}.raw").write_bytes(bytes(capture.map) if not error else b"")
        gbm.release(bo)
    print(f"{tag}: {renderer}, {width}x{height}, capture {capture.width}x{capture.height}")
    return 0


def compare(a, b):
    """Share of identical bytes, and the PSNR, of two captures."""
    if not a or len(a) != len(b):
        return 0.0, 0.0
    diffs = [abs(x - y) for x, y in zip(a, b)]
    mse = sum(d * d for d in diffs) / len(diffs)
    return diffs.count(0) / len(diffs), 99.0 if not mse else 10 * math.log10(255 * 255 / mse)


def main():
    if len(sys.argv) > 1:
        return render(sys.argv[1])
    OUT.mkdir(parents=True, exist_ok=True)
    before = subprocess.run(["dmesg"], capture_output=True, text=True).stdout.count("\n")
    runs = {"gpu": {}, "llvmpipe": {"MESA_LOADER_DRIVER_OVERRIDE": "kms_swrast"}}
    for tag, env in runs.items():
        rc = subprocess.run([sys.executable, __file__, tag], env={**os.environ, **env}).returncode
        if rc:
            return rc
    failures = 0
    for k in range(FRAMES):
        gpu, ref = (OUT / f"gpu-{k}.raw").read_bytes(), (OUT / f"llvmpipe-{k}.raw").read_bytes()
        same, db = compare(gpu, ref)
        ok = same >= SAME_FLOOR
        failures += not ok
        print(
            f"{'PASS' if ok else 'FAIL'} screen: frame {k} against llvmpipe, {same:.4%} identical, {db:.1f} dB"
        )
        if k:
            moved = compare(gpu, (OUT / f"gpu-{k - 1}.raw").read_bytes())[0] < SAME_FLOOR
            failures += not moved
            print(f"{'PASS' if moved else 'FAIL'} screen: frame {k} differs from frame {k - 1}")
    new = subprocess.run(["dmesg"], capture_output=True, text=True).stdout.splitlines()[before:]
    faults = [line for line in new if re.search(r"panfrost.*(timeout|fault)", line, re.I)]
    failures += bool(faults)
    print(f"{'PASS' if not faults else 'FAIL'} screen: no GPU job timeout or fault ({len(faults)})")
    for f in OUT.glob("*.raw"):
        f.unlink()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
