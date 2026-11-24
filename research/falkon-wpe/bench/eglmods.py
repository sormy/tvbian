"""Print the DRM modifiers EGL imports for a few YUV formats, on the render node's GPU."""
import ctypes, ctypes.util, struct

egl = ctypes.CDLL(ctypes.util.find_library("EGL"))
egl.eglGetProcAddress.restype = ctypes.c_void_p
egl.eglGetProcAddress.argtypes = [ctypes.c_char_p]
proc = lambda name, *args: ctypes.CFUNCTYPE(ctypes.c_uint, *args)(egl.eglGetProcAddress(name))
get_display = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p)(
    egl.eglGetProcAddress(b"eglGetPlatformDisplayEXT"))
EGL_PLATFORM_SURFACELESS_MESA = 0x31DD
display = get_display(EGL_PLATFORM_SURFACELESS_MESA, None, None)
egl.eglInitialize.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
assert egl.eglInitialize(display, None, None), "eglInitialize"
query = ctypes.CFUNCTYPE(ctypes.c_uint, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                         ctypes.POINTER(ctypes.c_uint64), ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_int))(
    egl.eglGetProcAddress(b"eglQueryDmaBufModifiersEXT"))
fourcc = lambda s: struct.unpack("<I", s.encode())[0]
for name in ("NV12", "YU08", "Y210", "YU10"):
    count = ctypes.c_int()
    query(display, fourcc(name), 0, None, None, ctypes.byref(count))
    mods = (ctypes.c_uint64 * max(count.value, 1))()
    external = (ctypes.c_uint * max(count.value, 1))()
    query(display, fourcc(name), count.value, mods, external, ctypes.byref(count))
    print(name, [f"{m:#x}{' (external)' if e else ''}" for m, e in zip(mods[:count.value], external[:count.value])])
