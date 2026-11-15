/*
 * The surface calls players and browsers make outside a decode, against the driver:
 * Kodi's export of a fresh surface, VLC's derive and buffer handle, Chromium's import.
 *   va_probe <DRM render node | X11 display>      "key value" lines
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <fcntl.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

#include <drm_fourcc.h>
#include <linux/dma-heap.h>
#include <va/va.h>
#include <va/va_drm.h>
#include <va/va_drmcommon.h>

#define WIDTH 320
#define HEIGHT 240
#define PITCH 320
#define LUMA_SIZE (PITCH * HEIGHT)
#define BUFFER_SIZE (LUMA_SIZE * 3 / 2)
#define PATTERN_SEED 7
#define DMA_HEAP "/dev/dma_heap/system"

typedef void *(*open_x11_display)(const char *);
typedef VADisplay (*get_x11_va_display)(void *);

/* X11 only on the host, where no render node exists: loaded, not linked */
static VADisplay open_display(const char *where)
{
    if (where[0] == '/') {
        int fd = open(where, O_RDWR | O_CLOEXEC);
        return fd < 0 ? NULL : vaGetDisplayDRM(fd);
    }
    void *x11 = dlopen("libX11.so.6", RTLD_NOW);
    void *va_x11 = dlopen("libva-x11.so.2", RTLD_NOW);
    if (!x11 || !va_x11)
        return NULL;
    open_x11_display x_open = (open_x11_display)dlsym(x11, "XOpenDisplay");
    get_x11_va_display va_get = (get_x11_va_display)dlsym(va_x11, "vaGetDisplay");
    void *display = x_open ? x_open(where) : NULL;
    return display && va_get ? va_get(display) : NULL;
}

static int alloc_buffer(size_t size)
{
    int heap = open(DMA_HEAP, O_RDWR | O_CLOEXEC);
    if (heap >= 0) {
        struct dma_heap_allocation_data alloc = { .len = size, .fd_flags = O_RDWR | O_CLOEXEC };
        int ret = ioctl(heap, DMA_HEAP_IOCTL_ALLOC, &alloc);
        close(heap);
        if (!ret)
            return alloc.fd;
    }
    int fd = memfd_create("va-probe", MFD_CLOEXEC);
    return fd >= 0 && ftruncate(fd, size) == 0 ? fd : -1;
}

static void report(const char *key, bool ok, const char *detail)
{
    printf("probe.%s %s%s%s\n", key, ok ? "pass" : "fail", detail ? ": " : "", detail ? detail : "");
}

/* Kodi: a fresh surface exported, before anything is decoded into it */
static void export_fresh(VADisplay dpy, unsigned rt_format, const char *key)
{
    VASurfaceID surface;
    VADRMPRIMESurfaceDescriptor desc;
    if (vaCreateSurfaces(dpy, rt_format, WIDTH, HEIGHT, &surface, 1, NULL, 0) != VA_STATUS_SUCCESS) {
        report(key, false, "vaCreateSurfaces");
        return;
    }
    VAStatus status = vaExportSurfaceHandle(dpy, surface, VA_SURFACE_ATTRIB_MEM_TYPE_DRM_PRIME_2,
                                            VA_EXPORT_SURFACE_READ_ONLY |
                                                VA_EXPORT_SURFACE_SEPARATE_LAYERS,
                                            &desc);
    bool ok = status == VA_STATUS_SUCCESS && desc.num_objects == 1 && desc.num_layers == 2 &&
              desc.objects[0].fd >= 0 && desc.layers[0].pitch[0] >= WIDTH;
    if (status == VA_STATUS_SUCCESS)
        close(desc.objects[0].fd);
    report(key, ok, ok ? NULL : vaErrorStr(status));
    vaDestroySurfaces(dpy, &surface, 1);
}

/* VLC: derive an undecoded surface's image and take its buffer's handle */
static void derive_fresh(VADisplay dpy)
{
    VASurfaceID surface;
    VAImage image;
    VABufferInfo info = { .mem_type = VA_SURFACE_ATTRIB_MEM_TYPE_DRM_PRIME };
    vaCreateSurfaces(dpy, VA_RT_FORMAT_YUV420, WIDTH, HEIGHT, &surface, 1, NULL, 0);
    VAStatus status = vaDeriveImage(dpy, surface, &image);
    if (status == VA_STATUS_SUCCESS) {
        status = vaAcquireBufferHandle(dpy, image.buf, &info);
        if (status == VA_STATUS_SUCCESS)
            vaReleaseBufferHandle(dpy, image.buf);
        vaDestroyImage(dpy, image.image_id);
    }
    report("derive-fresh", status == VA_STATUS_SUCCESS && info.mem_size >= BUFFER_SIZE,
           vaErrorStr(status));
    vaDestroySurfaces(dpy, &surface, 1);
}

static void fill_pattern(uint8_t *data, size_t size)
{
    for (size_t i = 0; i < size; i++)
        data[i] = (uint8_t)(i * PATTERN_SEED);
}

/* an NV12 image written into the surface, then read back */
static bool put_and_get(VADisplay dpy, VASurfaceID surface)
{
    VAImageFormat nv12 = { .fourcc = VA_FOURCC_NV12, .byte_order = VA_LSB_FIRST, .bits_per_pixel = 12 };
    VAImage in, out;
    uint8_t *data;
    bool same = false;

    if (vaCreateImage(dpy, &nv12, WIDTH, HEIGHT, &in) != VA_STATUS_SUCCESS)
        return false;
    vaMapBuffer(dpy, in.buf, (void **)&data);
    for (unsigned row = 0; row < HEIGHT * 3 / 2; row++)
        fill_pattern(data + row * in.pitches[0], WIDTH);
    vaUnmapBuffer(dpy, in.buf);
    if (vaPutImage(dpy, surface, in.image_id, 0, 0, WIDTH, HEIGHT, 0, 0, WIDTH, HEIGHT) ==
            VA_STATUS_SUCCESS &&
        vaCreateImage(dpy, &nv12, WIDTH, HEIGHT, &out) == VA_STATUS_SUCCESS) {
        uint8_t *back;
        vaGetImage(dpy, surface, 0, 0, WIDTH, HEIGHT, out.image_id);
        vaMapBuffer(dpy, out.buf, (void **)&back);
        same = true;
        for (unsigned row = 0; row < HEIGHT; row++)
            same &= !memcmp(back + out.offsets[0] + row * out.pitches[0],
                            data + in.offsets[0] + row * in.pitches[0], WIDTH);
        vaUnmapBuffer(dpy, out.buf);
        vaDestroyImage(dpy, out.image_id);
    }
    vaDestroyImage(dpy, in.image_id);
    return same;
}

static void put_get(VADisplay dpy)
{
    VASurfaceID surface;
    vaCreateSurfaces(dpy, VA_RT_FORMAT_YUV420, WIDTH, HEIGHT, &surface, 1, NULL, 0);
    report("put-get", put_and_get(dpy, surface), NULL);
    vaDestroySurfaces(dpy, &surface, 1);
}

/* Chromium: its own buffer imported, and written through the driver lands in it */
static void import_prime2(VADisplay dpy)
{
    int fd = alloc_buffer(BUFFER_SIZE);
    VADRMPRIMESurfaceDescriptor desc = {
        .fourcc = VA_FOURCC_NV12,
        .width = WIDTH,
        .height = HEIGHT,
        .num_objects = 1,
        .objects = { { .fd = fd, .size = BUFFER_SIZE, .drm_format_modifier = DRM_FORMAT_MOD_LINEAR } },
        .num_layers = 1,
        .layers = { { .drm_format = DRM_FORMAT_NV12,
                      .num_planes = 2,
                      .offset = { 0, LUMA_SIZE },
                      .pitch = { PITCH, PITCH } } },
    };
    VASurfaceAttrib attribs[] = {
        { .type = VASurfaceAttribMemoryType,
          .flags = VA_SURFACE_ATTRIB_SETTABLE,
          .value = { .type = VAGenericValueTypeInteger,
                     .value.i = VA_SURFACE_ATTRIB_MEM_TYPE_DRM_PRIME_2 } },
        { .type = VASurfaceAttribExternalBufferDescriptor,
          .flags = VA_SURFACE_ATTRIB_SETTABLE,
          .value = { .type = VAGenericValueTypePointer, .value.p = &desc } },
    };
    VASurfaceID surface;
    VAStatus status = vaCreateSurfaces(dpy, VA_RT_FORMAT_YUV420, WIDTH, HEIGHT, &surface, 1,
                                       attribs, 2);
    bool ok = status == VA_STATUS_SUCCESS && put_and_get(dpy, surface);
    if (ok) {
        uint8_t *mapped = mmap(NULL, BUFFER_SIZE, PROT_READ, MAP_SHARED, fd, 0);
        uint8_t expected[WIDTH];
        fill_pattern(expected, WIDTH);
        ok = mapped != MAP_FAILED && !memcmp(mapped, expected, WIDTH);
        if (mapped != MAP_FAILED)
            munmap(mapped, BUFFER_SIZE);
    }
    if (status == VA_STATUS_SUCCESS)
        vaDestroySurfaces(dpy, &surface, 1);
    report("import-prime2", ok, vaErrorStr(status));
    close(fd);
}

static VAStatus create_with_modifier(VADisplay dpy, uint64_t modifier)
{
    VADRMFormatModifierList list = { .num_modifiers = 1, .modifiers = &modifier };
    VASurfaceAttrib attrib = { .type = VASurfaceAttribDRMFormatModifiers,
                               .flags = VA_SURFACE_ATTRIB_SETTABLE,
                               .value = { .type = VAGenericValueTypePointer, .value.p = &list } };
    VASurfaceID surface;
    VAStatus status =
        vaCreateSurfaces(dpy, VA_RT_FORMAT_YUV420, WIDTH, HEIGHT, &surface, 1, &attrib, 1);
    if (status == VA_STATUS_SUCCESS)
        vaDestroySurfaces(dpy, &surface, 1);
    return status;
}

/* Chromium's modifier list: linear taken, a layout the engine never writes refused */
static void modifiers(VADisplay dpy)
{
    VAStatus linear = create_with_modifier(dpy, DRM_FORMAT_MOD_LINEAR);
    VAStatus tiled = create_with_modifier(dpy, I915_FORMAT_MOD_X_TILED);
    report("modifiers", linear == VA_STATUS_SUCCESS && tiled == VA_STATUS_ERROR_ATTR_NOT_SUPPORTED,
           vaErrorStr(linear != VA_STATUS_SUCCESS ? linear : tiled));
}

int main(int argc, char **argv)
{
    int major, minor;
    VADisplay dpy = argc > 1 ? open_display(argv[1]) : NULL;
    if (!dpy || vaInitialize(dpy, &major, &minor) != VA_STATUS_SUCCESS) {
        printf("probe.initialize fail\n");
        return 1;
    }
    printf("probe.vendor %s\n", vaQueryVendorString(dpy));
    export_fresh(dpy, VA_RT_FORMAT_YUV420, "export-fresh");
    export_fresh(dpy, VA_RT_FORMAT_YUV420_10, "export-fresh-10bit");
    derive_fresh(dpy);
    put_get(dpy);
    import_prime2(dpy);
    modifiers(dpy);
    vaTerminate(dpy);
    return 0;
}
