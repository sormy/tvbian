/* Surfaces and images: memory owned from creation, imported, or a decoded picture bound late. */
#define _GNU_SOURCE
#include <errno.h>
#include <stdlib.h>
#include <fcntl.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#include <drm_fourcc.h>
#include <linux/dma-buf.h>
#include <linux/dma-heap.h>
#include <va/va_drmcommon.h>

#include "driver.h"
#include "pixels.h"

#define DMA_HEAP "/dev/dma_heap/system"
/* how long a sync waits for a held picture, looking every SYNC_POLL_MS */
#define SYNC_PATIENCE_MS 1000
#define SYNC_POLL_MS 5
#define USEC_PER_MSEC 1000
#define MS_PER_SECOND 1000
#define NS_PER_MS 1000000

uint64_t monotonic_ms(void)
{
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    return (uint64_t)now.tv_sec * MS_PER_SECOND + (uint64_t)now.tv_nsec / NS_PER_MS;
}
#define HEIGHT_ALIGN 16
#define SURFACE_SIZE_MIN 16
#define SURFACE_SIZE_MAX 8192
#define NUM_SURFACE_ATTRIBS 8
#define ALIGN(value, to) (((value) + (to) - 1) / (to) * (to))

#ifndef DRM_FORMAT_NV15
#define DRM_FORMAT_NV15 fourcc_code('N', 'V', '1', '5')
#endif

static const VAImageFormat image_formats[] = {
    { .fourcc = VA_FOURCC_NV12, .byte_order = VA_LSB_FIRST, .bits_per_pixel = 12 },
    { .fourcc = VA_FOURCC_P010, .byte_order = VA_LSB_FIRST, .bits_per_pixel = 24 },
};
#define NUM_IMAGE_FORMATS (sizeof(image_formats) / sizeof(image_formats[0]))

/* one engine a process: the family's */
static const struct backend *engine;

void surface_set_engine(const struct backend *backend)
{
    engine = backend;
}

uint32_t surface_fourcc_of(unsigned rt_format)
{
    return rt_format == VA_RT_FORMAT_YUV420_10 ? VA_FOURCC_P010 : VA_FOURCC_NV12;
}

static unsigned bytes_per_sample(uint32_t fourcc)
{
    return fourcc == VA_FOURCC_P010 ? 2 : 1;
}

static struct nv12_planes planes_of_backing(const struct surface *s)
{
    struct backing *b = s->backing;
    uint8_t *map = backing_map(b);
    return (struct nv12_planes){
        .luma = map,
        .chroma = map ? map + b->chroma_offset : NULL,
        .luma_pitch = b->pitch,
        .chroma_pitch = b->pitch,
        .width = s->width,
        .height = s->height,
        .ten_bit = s->fourcc == VA_FOURCC_P010,
    };
}

static void sync_backing(const struct backing *b, uint64_t flags)
{
    struct dma_buf_sync sync = { .flags = flags | DMA_BUF_SYNC_RW };
    ioctl(b->fd, DMA_BUF_IOCTL_SYNC, &sync);
}

/* a dma-buf from the system heap; a memfd where there is none, as on the host */
int dmabuf_alloc(size_t size)
{
    int heap = open(DMA_HEAP, O_RDWR | O_CLOEXEC);
    if (heap >= 0) {
        struct dma_heap_allocation_data alloc = { .len = size, .fd_flags = O_RDWR | O_CLOEXEC };
        int ret = ioctl(heap, DMA_HEAP_IOCTL_ALLOC, &alloc);
        close(heap);
        if (!ret)
            return alloc.fd;
    }
    int fd = memfd_create("tvb-va-surface", MFD_CLOEXEC);
    if (fd >= 0 && ftruncate(fd, size) < 0) {
        close(fd);
        return -1;
    }
    return fd;
}

static struct backing *backing_from_fd(int fd, size_t size, unsigned pitch, unsigned chroma_offset)
{
    struct backing *b = calloc(1, sizeof(*b));
    if (!b)
        return NULL;
    *b = (struct backing){ .fd = fd, .size = size, .pitch = pitch, .chroma_offset = chroma_offset };
    return b;
}

uint8_t *backing_map(struct backing *b)
{
    if (!b->map) {
        void *map = mmap(NULL, b->size, PROT_READ | PROT_WRITE, MAP_SHARED, b->fd, 0);
        b->map = map == MAP_FAILED ? NULL : map;
    }
    return b->map;
}

static void backing_free(struct backing *b)
{
    if (!b)
        return;
    if (b->map)
        munmap(b->map, b->size);
    close(b->fd);
    free(b);
}

static unsigned min_of(unsigned a, unsigned b)
{
    return a < b ? a : b;
}

static void release_picture(struct surface *s)
{
    if (s->picture && s->picture->release)
        s->picture->release(s->picture);
    s->picture = NULL;
}

static int copy_picture_to_backing(struct surface *s, const struct engine_picture *picture)
{
    struct nv12_planes dst = planes_of_backing(s);
    dst.width = min_of(dst.width, picture->width);
    dst.height = min_of(dst.height, picture->height);
    if (engine && engine->copy_picture &&
        engine->copy_picture(picture, s->backing, s->fourcc, dst.width, dst.height) == 0)
        return 0;
    if (!dst.luma)
        return -ENOMEM;
    sync_backing(s->backing, DMA_BUF_SYNC_START);
    int ret = pixels_from_engine(picture, 0, 0, &dst);
    sync_backing(s->backing, DMA_BUF_SYNC_END);
    return ret;
}

int surface_adopt_backing(struct surface *s, int fd, const struct backing_layout *layout)
{
    if (!(s->backing = backing_from_fd(fd, layout->size, layout->pitch, layout->chroma_offset))) {
        close(fd);
        return -ENOMEM;
    }
    int ret = s->picture ? copy_picture_to_backing(s, s->picture) : 0;
    release_picture(s);
    return ret;
}

int surface_ensure_backing(struct surface *s)
{
    if (s->backing)
        return 0;
    if (s->planned.size) {
        int fd = dmabuf_alloc(s->planned.size);
        return fd < 0 ? -errno : surface_adopt_backing(s, fd, &s->planned);
    }
    unsigned pitch = ALIGN(s->width * bytes_per_sample(s->fourcc), GPU_PLANE_ALIGN);
    unsigned luma_rows = ALIGN(s->height, HEIGHT_ALIGN);
    size_t size = (size_t)pitch * luma_rows * (engine && engine->decodes_into_backing ? 4 : 3) / 2;
    /* the whole pages the heap gives: an encoder asks a little past the picture */
    size = ALIGN(size, (size_t)sysconf(_SC_PAGESIZE));
    int fd = dmabuf_alloc(size);
    if (fd < 0)
        return -errno;
    const struct backing_layout layout = { pitch, pitch * luma_rows, size };
    return surface_adopt_backing(s, fd, &layout);
}

/* the decoder's own memory where it lends some, so its pictures need no copy */
static int ensure_decodable_backing(struct driver *drv, VASurfaceID id, struct surface *s)
{
    if (!s->backing && engine && engine->lend_backing && engine->lend_backing(drv, id, s) == 0)
        return 0;
    return surface_ensure_backing(s);
}

void surface_drop_unseen_backing(struct surface *s)
{
    if (s->backing && !s->exported && !s->images) {
        backing_free(s->backing);
        s->backing = NULL;
    }
}

void surface_mark_decoded(struct surface *s)
{
    release_picture(s);
    s->delivered = true;
}

static uint32_t drm_format_of(uint32_t fourcc)
{
    return fourcc == VA_FOURCC_P010 ? DRM_FORMAT_P010 : DRM_FORMAT_NV12;
}

static bool is_compressed_picture(const struct engine_picture *p)
{
    return p && p->modifier != DRM_FORMAT_MOD_LINEAR;
}

/* held as is, converted only when read in another layout; copied into the surface's own memory
 * where it has some. A compressed picture, which the CPU cannot read, is held always. */
int surface_bind_picture(struct surface *s, struct engine_picture *picture)
{
    release_picture(s);
    s->picture = picture;
    s->delivered |= picture != NULL;
    if (!picture || is_compressed_picture(picture) || !s->backing)
        return 0;
    int ret = copy_picture_to_backing(s, picture);
    release_picture(s);
    return ret;
}

void surface_free(struct surface *s)
{
    if (!s)
        return;
    release_picture(s);
    backing_free(s->backing);
    free(s);
}

/* creation, and import of the client's own buffers */

static struct backing *import_external(const VASurfaceAttribExternalBuffers *ext, unsigned index)
{
    if (index >= ext->num_buffers || ext->num_planes != 2 || ext->pitches[0] != ext->pitches[1])
        return NULL;
    int fd = dup((int)ext->buffers[index]);
    struct backing *b = fd >= 0 ? backing_from_fd(fd, ext->data_size, ext->pitches[0],
                                                  ext->offsets[1])
                                : NULL;
    if (!b && fd >= 0)
        close(fd);
    return b;
}

static struct backing *import_prime2(const VADRMPRIMESurfaceDescriptor *desc)
{
    unsigned planes = desc->num_layers == 1 ? desc->layers[0].num_planes : desc->num_layers;
    unsigned pitch = desc->layers[0].pitch[0];
    unsigned chroma_offset = desc->num_layers == 1 ? desc->layers[0].offset[1]
                                                   : desc->layers[1].offset[0];
    if (desc->num_objects != 1 || planes != 2 ||
        desc->objects[0].drm_format_modifier != DRM_FORMAT_MOD_LINEAR)
        return NULL;
    int fd = dup(desc->objects[0].fd);
    struct backing *b = fd >= 0 ? backing_from_fd(fd, desc->objects[0].size, pitch, chroma_offset)
                                : NULL;
    if (!b && fd >= 0)
        close(fd);
    return b;
}

struct creation {
    uint32_t fourcc;
    uint32_t memory_type;
    const void *external;
    const VADRMFormatModifierList *modifiers;
};

static VAStatus parse_attributes(const VASurfaceAttrib *attribs, unsigned num_attribs,
                                 struct creation *c)
{
    for (unsigned i = 0; i < num_attribs; i++) {
        const VASurfaceAttrib *a = &attribs[i];
        if (!(a->flags & VA_SURFACE_ATTRIB_SETTABLE))
            continue;
        switch (a->type) {
        case VASurfaceAttribPixelFormat:
            c->fourcc = a->value.value.i;
            if (c->fourcc != VA_FOURCC_NV12 && c->fourcc != VA_FOURCC_P010)
                return VA_STATUS_ERROR_UNSUPPORTED_RT_FORMAT;
            break;
        case VASurfaceAttribMemoryType:
            c->memory_type = a->value.value.i;
            break;
        case VASurfaceAttribExternalBufferDescriptor:
            c->external = a->value.value.p;
            break;
        case VASurfaceAttribDRMFormatModifiers:
            c->modifiers = a->value.value.p;
            break;
        default:
            break;
        }
    }
    bool imports = c->memory_type == VA_SURFACE_ATTRIB_MEM_TYPE_DRM_PRIME ||
                   c->memory_type == VA_SURFACE_ATTRIB_MEM_TYPE_DRM_PRIME_2;
    if (imports != !!c->external || (c->memory_type & ~(VA_SURFACE_ATTRIB_MEM_TYPE_VA |
                                                        VA_SURFACE_ATTRIB_MEM_TYPE_DRM_PRIME |
                                                        VA_SURFACE_ATTRIB_MEM_TYPE_DRM_PRIME_2)))
        return VA_STATUS_ERROR_UNSUPPORTED_MEMORY_TYPE;
    return VA_STATUS_SUCCESS;
}

static bool lists_modifier(const VADRMFormatModifierList *list, uint64_t modifier)
{
    for (unsigned i = 0; list && i < list->num_modifiers; i++)
        if (list->modifiers[i] == modifier)
            return true;
    return false;
}

static VAStatus destroy_surfaces(VADriverContextP ctx, VASurfaceID *ids, int num_surfaces)
{
    struct driver *drv = DRIVER(ctx);
    for (int i = 0; i < num_surfaces; i++) {
        pthread_mutex_lock(&drv->lock);
        surface_free(handle_take(drv, &drv->surfaces, ids[i]));
        pthread_mutex_unlock(&drv->lock);
    }
    return VA_STATUS_SUCCESS;
}

static VAStatus create_surfaces2(VADriverContextP ctx, unsigned format, unsigned width,
                                 unsigned height, VASurfaceID *ids, unsigned num_surfaces,
                                 VASurfaceAttrib *attribs, unsigned num_attribs)
{
    struct creation c = { .fourcc = surface_fourcc_of(format) };
    VAStatus status = parse_attributes(attribs, num_attribs, &c);
    if (status != VA_STATUS_SUCCESS)
        return status;
    if (format != VA_RT_FORMAT_YUV420 && format != VA_RT_FORMAT_YUV420_10)
        return VA_STATUS_ERROR_UNSUPPORTED_RT_FORMAT;
    uint64_t compressed = DRIVER(ctx)->compressed_modifier;
    bool takes_linear = !c.modifiers || lists_modifier(c.modifiers, DRM_FORMAT_MOD_LINEAR);
    bool takes_compressed = compressed && lists_modifier(c.modifiers, compressed);
    if (!takes_linear && (!takes_compressed || c.external))
        return VA_STATUS_ERROR_ATTR_NOT_SUPPORTED;

    for (unsigned i = 0; i < num_surfaces; i++) {
        struct surface *s = calloc(1, sizeof(*s));
        if (s) {
            *s = (struct surface){ .width = width,
                                   .height = height,
                                   .fourcc = c.fourcc,
                                   .takes_linear = takes_linear,
                                   .takes_compressed = takes_compressed };
            if (!c.external && engine && engine->plan_layout)
                engine->plan_layout(DRIVER(ctx)->decoding, c.fourcc, width, height, &s->planned);
            if (c.memory_type == VA_SURFACE_ATTRIB_MEM_TYPE_DRM_PRIME)
                s->backing = import_external(c.external, i);
            else if (c.memory_type == VA_SURFACE_ATTRIB_MEM_TYPE_DRM_PRIME_2)
                s->backing = import_prime2(c.external);
        }
        ids[i] = s && (s->backing || !c.external) ? handle_add(DRIVER(ctx), &DRIVER(ctx)->surfaces, s)
                                                   : VA_INVALID_ID;
        if (ids[i] == VA_INVALID_ID) {
            surface_free(s);
            destroy_surfaces(ctx, ids, i);
            return c.external ? VA_STATUS_ERROR_INVALID_PARAMETER
                              : VA_STATUS_ERROR_ALLOCATION_FAILED;
        }
    }
    return VA_STATUS_SUCCESS;
}

static VAStatus create_surfaces(VADriverContextP ctx, int width, int height, int format,
                                int num_surfaces, VASurfaceID *ids)
{
    return create_surfaces2(ctx, format, width, height, ids, num_surfaces, NULL, 0);
}

static VAStatus query_surface_attributes(VADriverContextP ctx, VAConfigID config_id,
                                         VASurfaceAttrib *attribs, unsigned *num_attribs)
{
    const struct config *config = handle_get(DRIVER(ctx), &DRIVER(ctx)->configs, config_id);
    if (!config)
        return VA_STATUS_ERROR_INVALID_CONFIG;
    if (!attribs) {
        *num_attribs = NUM_SURFACE_ATTRIBS;
        return VA_STATUS_SUCCESS;
    }
    if (*num_attribs < NUM_SURFACE_ATTRIBS)
        return VA_STATUS_ERROR_MAX_NUM_EXCEEDED;
    bool ten_bit = config->rt_format == VA_RT_FORMAT_YUV420_10;
    bool narrows = ten_bit && engine && engine->narrows_ten_bit;
    uint32_t listed_fourcc = narrows ? VA_FOURCC_NV12 : surface_fourcc_of(config->rt_format);
    const struct {
        VASurfaceAttribType type;
        uint32_t flags;
        int value;
    } values[NUM_SURFACE_ATTRIBS - 1] = {
        { VASurfaceAttribPixelFormat, VA_SURFACE_ATTRIB_SETTABLE, (int)listed_fourcc },
        { VASurfaceAttribMinWidth, 0, SURFACE_SIZE_MIN },
        { VASurfaceAttribMinHeight, 0, SURFACE_SIZE_MIN },
        { VASurfaceAttribMaxWidth, 0, SURFACE_SIZE_MAX },
        { VASurfaceAttribMaxHeight, 0, SURFACE_SIZE_MAX },
        { VASurfaceAttribMemoryType, VA_SURFACE_ATTRIB_SETTABLE,
          VA_SURFACE_ATTRIB_MEM_TYPE_VA | VA_SURFACE_ATTRIB_MEM_TYPE_DRM_PRIME |
              VA_SURFACE_ATTRIB_MEM_TYPE_DRM_PRIME_2 },
        { VASurfaceAttribExternalBufferDescriptor, VA_SURFACE_ATTRIB_SETTABLE, 0 },
    };
    unsigned n = 0;
    for (unsigned i = 0; i < NUM_SURFACE_ATTRIBS - 1; i++) {
        attribs[n++] = (VASurfaceAttrib){
            .type = values[i].type,
            .flags = VA_SURFACE_ATTRIB_GETTABLE | values[i].flags,
            .value = { .type = values[i].type == VASurfaceAttribExternalBufferDescriptor
                                   ? VAGenericValueTypePointer
                                   : VAGenericValueTypeInteger,
                       .value.i = values[i].value },
        };
    }
    /* 10-bit configs take 8-bit surfaces too, for clients that probe with NV12; an engine that
     * narrows lists NV12 alone, as FFmpeg and mpv take P010 whenever it is listed */
    if (ten_bit && !narrows)
        attribs[n++] = (VASurfaceAttrib){
            .type = VASurfaceAttribPixelFormat,
            .flags = VA_SURFACE_ATTRIB_GETTABLE | VA_SURFACE_ATTRIB_SETTABLE,
            .value = { .type = VAGenericValueTypeInteger, .value.i = VA_FOURCC_NV12 },
        };
    *num_attribs = n;
    return VA_STATUS_SUCCESS;
}

static VAStatus sync_surface(VADriverContextP ctx, VASurfaceID id)
{
    struct driver *drv = DRIVER(ctx);
    struct surface *s = handle_get(drv, &drv->surfaces, id);
    if (!s)
        return VA_STATUS_ERROR_INVALID_SURFACE;
    /* a stateful decoder hands a picture out after later packets: the lock is let go between
     * looks, so a client's other threads can send them */
    /* counted on the clock: an engine's sync may itself wait */
    for (uint64_t start = monotonic_ms();;) {
        bool last = monotonic_ms() - start >= SYNC_PATIENCE_MS;
        pthread_mutex_lock(&drv->lock);
        bool lost = s->submitted && !s->delivered && !s->hidden;
        bool engine = lost && s->context && drv->backend->sync;
        if (engine)
            lost = drv->backend->sync(drv, s->context, id, last) < 0 || !s->delivered;
        pthread_mutex_unlock(&drv->lock);
        if (!lost || !engine || last)
            return lost ? VA_STATUS_ERROR_DECODING_ERROR : VA_STATUS_SUCCESS;
        usleep(SYNC_POLL_MS * USEC_PER_MSEC);
    }
}

static VAStatus query_surface_status(VADriverContextP ctx, VASurfaceID id, VASurfaceStatus *status)
{
    VAStatus synced = sync_surface(ctx, id);
    *status = VASurfaceReady;
    return synced == VA_STATUS_ERROR_INVALID_SURFACE ? synced : VA_STATUS_SUCCESS;
}

/* export: the surface's memory, or the engine picture's own dma-bufs */

static uint32_t plane_format_of(uint32_t fourcc, unsigned plane)
{
    if (fourcc == VA_FOURCC_P010)
        return plane ? DRM_FORMAT_GR1616 : DRM_FORMAT_R16;
    return plane ? DRM_FORMAT_GR88 : DRM_FORMAT_R8;
}

struct plane_layout {
    unsigned object_index;
    unsigned offset;
    unsigned pitch;
};

static void fill_layers(VADRMPRIMESurfaceDescriptor *out, uint32_t fourcc, uint32_t drm_format,
                        bool separate, const struct plane_layout planes[2])
{
    out->num_layers = separate ? 2 : 1;
    for (unsigned p = 0; p < 2; p++) {
        unsigned layer = separate ? p : 0, slot = separate ? 0 : p;
        out->layers[layer].drm_format = separate ? plane_format_of(fourcc, p) : drm_format;
        out->layers[layer].num_planes = separate ? 1 : 2;
        out->layers[layer].object_index[slot] = planes[p].object_index;
        out->layers[layer].offset[slot] = planes[p].offset;
        out->layers[layer].pitch[slot] = planes[p].pitch;
    }
}

/* as the surface's format, or NV15 for a 10-bit surface's display planes: one layer, as NV15
 * has no per-plane formats */
static bool exportable(const struct engine_picture *p, uint32_t fourcc, bool separate)
{
    bool nv15 = p && p->drm_format == DRM_FORMAT_NV15 && fourcc == VA_FOURCC_P010 && !separate;
    if (!p || !(p->drm_format == drm_format_of(fourcc) || nv15) ||
        p->modifier != DRM_FORMAT_MOD_LINEAR)
        return false;
    for (unsigned i = 0; i < PICTURE_PLANES; i++)
        if (p->plane_pitch[i] % GPU_PLANE_ALIGN || p->plane_offset[i] % GPU_PLANE_ALIGN)
            return false;
    return true;
}

static void export_picture(const struct engine_picture *p, uint32_t fourcc, bool separate,
                           VADRMPRIMESurfaceDescriptor *out)
{
    struct plane_layout planes[2];
    out->num_objects = p->num_objects;
    for (unsigned i = 0; i < p->num_objects; i++) {
        out->objects[i].fd = dup(p->fds[i]);
        out->objects[i].size = p->sizes[i];
        out->objects[i].drm_format_modifier = p->modifier;
    }
    for (int plane = 0; plane < 2; plane++)
        planes[plane] = (struct plane_layout){ p->plane_object[plane], p->plane_offset[plane],
                                               p->plane_pitch[plane] };
    fill_layers(out, fourcc, p->drm_format, separate, planes);
}

static void export_backing(struct surface *s, bool separate, VADRMPRIMESurfaceDescriptor *out)
{
    const struct backing *b = s->backing;
    s->exported = true;
    const struct plane_layout planes[2] = { { 0, 0, b->pitch }, { 0, b->chroma_offset, b->pitch } };
    out->num_objects = 1;
    out->objects[0].fd = dup(b->fd);
    out->objects[0].size = b->size;
    out->objects[0].drm_format_modifier = DRM_FORMAT_MOD_LINEAR;
    fill_layers(out, s->fourcc, drm_format_of(s->fourcc), separate, planes);
}

static bool is_compressed(const struct surface *s)
{
    return is_compressed_picture(s->picture);
}

/* one plane, as FFmpeg's v4l2-request and Kodi hand Cedrus's AFBC to the display and GPU */
static void export_compressed(const struct engine_picture *p, VADRMPRIMESurfaceDescriptor *out)
{
    out->num_objects = 1;
    out->objects[0].fd = dup(p->fds[0]);
    out->objects[0].size = p->sizes[0];
    out->objects[0].drm_format_modifier = p->modifier;
    out->num_layers = 1;
    out->layers[0].drm_format = p->drm_format;
    out->layers[0].num_planes = 1;
}

static VAStatus export_surface_handle(VADriverContextP ctx, VASurfaceID surface_id,
                                      uint32_t mem_type, uint32_t flags, void *descriptor)
{
    struct driver *drv = DRIVER(ctx);
    struct surface *s = handle_get(drv, &drv->surfaces, surface_id);
    VADRMPRIMESurfaceDescriptor *out = descriptor;
    bool separate = flags & VA_EXPORT_SURFACE_SEPARATE_LAYERS;
    VAStatus status = VA_STATUS_SUCCESS;

    if (!s)
        return VA_STATUS_ERROR_INVALID_SURFACE;
    if (mem_type != VA_SURFACE_ATTRIB_MEM_TYPE_DRM_PRIME_2)
        return VA_STATUS_ERROR_UNSUPPORTED_MEMORY_TYPE;
    memset(out, 0, sizeof(*out));
    out->fourcc = s->fourcc;
    out->width = s->width;
    out->height = s->height;
    pthread_mutex_lock(&drv->lock);
    drv->layout_seen = true;
    if (is_compressed(s) && separate)
        status = VA_STATUS_ERROR_UNIMPLEMENTED;
    else if (is_compressed(s))
        export_compressed(s->picture, out);
    else if (exportable(s->picture, s->fourcc, separate))
        export_picture(s->picture, s->fourcc, separate, out);
    else if (ensure_decodable_backing(drv, surface_id, s) == 0)
        export_backing(s, separate, out);
    else
        status = VA_STATUS_ERROR_ALLOCATION_FAILED;
    pthread_mutex_unlock(&drv->lock);
    return status;
}

/* images: CPU access to a surface, copied or derived */

static VAStatus query_image_formats(VADriverContextP ctx, VAImageFormat *formats, int *num_formats)
{
    memcpy(formats, image_formats, sizeof(image_formats));
    *num_formats = NUM_IMAGE_FORMATS;
    return VA_STATUS_SUCCESS;
}

static VAStatus add_image(struct driver *drv, VAImage *image, struct va_buffer *b)
{
    VAImage *stored = malloc(sizeof(*stored));
    if (!stored)
        return VA_STATUS_ERROR_ALLOCATION_FAILED;
    if ((image->buf = handle_add(drv, &drv->buffers, b)) == VA_INVALID_ID ||
        (image->image_id = handle_add(drv, &drv->images, stored)) == VA_INVALID_ID) {
        handle_take(drv, &drv->buffers, image->buf);
        free(stored);
        return VA_STATUS_ERROR_ALLOCATION_FAILED;
    }
    *stored = *image;
    return VA_STATUS_SUCCESS;
}

static VAStatus create_image(VADriverContextP ctx, VAImageFormat *format, int width, int height,
                             VAImage *image)
{
    if (format->fourcc != VA_FOURCC_NV12 && format->fourcc != VA_FOURCC_P010)
        return VA_STATUS_ERROR_INVALID_IMAGE_FORMAT;
    unsigned pitch = ALIGN(width * bytes_per_sample(format->fourcc), GPU_PLANE_ALIGN);
    unsigned luma_size = pitch * height;
    struct va_buffer *b = calloc(1, sizeof(*b));

    *image = (VAImage){
        .format = format->fourcc == VA_FOURCC_P010 ? image_formats[1] : image_formats[0],
        .width = width,
        .height = height,
        .data_size = luma_size + pitch * ((height + 1) / 2),
        .num_planes = 2,
        .pitches = { pitch, pitch },
        .offsets = { 0, luma_size },
    };
    if (!b || !(b->data = calloc(1, image->data_size))) {
        free(b);
        return VA_STATUS_ERROR_ALLOCATION_FAILED;
    }
    *b = (struct va_buffer){ .type = VAImageBufferType, .element_size = image->data_size,
                             .num_elements = 1, .data = b->data };
    VAStatus status = add_image(DRIVER(ctx), image, b);
    if (status != VA_STATUS_SUCCESS) {
        free(b->data);
        free(b);
    }
    return status;
}

static VAStatus derive_image(VADriverContextP ctx, VASurfaceID surface_id, VAImage *image)
{
    struct driver *drv = DRIVER(ctx);
    struct surface *s = handle_get(drv, &drv->surfaces, surface_id);
    if (!s)
        return VA_STATUS_ERROR_INVALID_SURFACE;
    if (is_compressed(s))
        return VA_STATUS_ERROR_UNIMPLEMENTED;
    pthread_mutex_lock(&drv->lock);
    int ret = ensure_decodable_backing(drv, surface_id, s);
    pthread_mutex_unlock(&drv->lock);
    uint8_t *map = ret ? NULL : backing_map(s->backing);
    struct va_buffer *b = map ? calloc(1, sizeof(*b)) : NULL;
    if (!b)
        return VA_STATUS_ERROR_ALLOCATION_FAILED;
    const struct backing *backing = s->backing;
    *b = (struct va_buffer){ .type = VAImageBufferType, .element_size = backing->size,
                             .num_elements = 1, .data = map, .derived_from = s };
    s->images++;
    *image = (VAImage){
        .format = s->fourcc == VA_FOURCC_P010 ? image_formats[1] : image_formats[0],
        .width = s->width,
        .height = s->height,
        .data_size = backing->size,
        .num_planes = 2,
        .pitches = { backing->pitch, backing->pitch },
        .offsets = { 0, backing->chroma_offset },
    };
    VAStatus status = add_image(drv, image, b);
    if (status != VA_STATUS_SUCCESS) {
        s->images--;
        free(b);
    }
    return status;
}

static VAStatus destroy_image(VADriverContextP ctx, VAImageID image_id)
{
    struct driver *drv = DRIVER(ctx);
    VAImage *image = handle_take(drv, &drv->images, image_id);
    if (!image)
        return VA_STATUS_ERROR_INVALID_IMAGE;
    struct va_buffer *b = handle_take(drv, &drv->buffers, image->buf);
    if (b && b->derived_from)
        b->derived_from->images--;
    else if (b)
        free(b->data);
    free(b);
    free(image);
    return VA_STATUS_SUCCESS;
}

static struct nv12_planes planes_of_image(const VAImage *image, uint8_t *data)
{
    return (struct nv12_planes){
        .luma = data + image->offsets[0],
        .chroma = data + image->offsets[1],
        .luma_pitch = image->pitches[0],
        .chroma_pitch = image->pitches[1],
        .width = image->width,
        .height = image->height,
        .ten_bit = image->format.fourcc == VA_FOURCC_P010,
    };
}

static VAStatus get_image(VADriverContextP ctx, VASurfaceID surface_id, int x, int y,
                          unsigned width, unsigned height, VAImageID image_id)
{
    struct driver *drv = DRIVER(ctx);
    struct surface *s = handle_get(drv, &drv->surfaces, surface_id);
    VAImage *image = handle_get(drv, &drv->images, image_id);
    struct va_buffer *b = image ? handle_get(drv, &drv->buffers, image->buf) : NULL;
    VAStatus status = VA_STATUS_ERROR_OPERATION_FAILED;

    if (!s)
        return VA_STATUS_ERROR_INVALID_SURFACE;
    if (!b)
        return VA_STATUS_ERROR_INVALID_IMAGE;
    if (is_compressed(s))
        return VA_STATUS_ERROR_UNIMPLEMENTED;
    if (x < 0 || y < 0 || (unsigned)x >= s->width || (unsigned)y >= s->height)
        return VA_STATUS_ERROR_INVALID_PARAMETER;
    struct nv12_planes dst = planes_of_image(image, b->data);
    pthread_mutex_lock(&drv->lock);
    if (s->backing) {
        struct nv12_planes src = planes_of_backing(s);
        dst.width = min_of(min_of(width, dst.width), s->width - x);
        dst.height = min_of(min_of(height, dst.height), s->height - y);
        sync_backing(s->backing, DMA_BUF_SYNC_START);
        if (src.luma && src.ten_bit == dst.ten_bit) {
            unsigned bytes = dst.width * bytes_per_sample(s->fourcc);
            for (unsigned row = 0; row < dst.height; row++)
                memcpy(dst.luma + (size_t)row * dst.luma_pitch,
                       src.luma + (size_t)(y + row) * src.luma_pitch + x * bytes_per_sample(s->fourcc),
                       bytes);
            for (unsigned row = 0; row < (dst.height + 1) / 2; row++)
                memcpy(dst.chroma + (size_t)row * dst.chroma_pitch,
                       src.chroma + (size_t)(y / 2 + row) * src.chroma_pitch +
                           (x & ~1u) * bytes_per_sample(s->fourcc),
                       (bytes + 1) & ~1u);
            status = VA_STATUS_SUCCESS;
        }
        sync_backing(s->backing, DMA_BUF_SYNC_END);
    } else if (s->picture) {
        dst.width = min_of(min_of(width, dst.width), s->picture->width - x);
        dst.height = min_of(min_of(height, dst.height), s->picture->height - y);
        if (pixels_from_engine(s->picture, x, y, &dst) == 0)
            status = VA_STATUS_SUCCESS;
    }
    pthread_mutex_unlock(&drv->lock);
    return status;
}

static VAStatus put_image(VADriverContextP ctx, VASurfaceID surface_id, VAImageID image_id,
                          int src_x, int src_y, unsigned src_width, unsigned src_height,
                          int dest_x, int dest_y, unsigned dest_width, unsigned dest_height)
{
    struct driver *drv = DRIVER(ctx);
    struct surface *s = handle_get(drv, &drv->surfaces, surface_id);
    VAImage *image = handle_get(drv, &drv->images, image_id);
    struct va_buffer *b = image ? handle_get(drv, &drv->buffers, image->buf) : NULL;

    if (!s)
        return VA_STATUS_ERROR_INVALID_SURFACE;
    if (!b)
        return VA_STATUS_ERROR_INVALID_IMAGE;
    if (is_compressed(s) || src_width != dest_width || src_height != dest_height || src_x ||
        src_y || dest_x ||
        dest_y || (image->format.fourcc == VA_FOURCC_P010) != (s->fourcc == VA_FOURCC_P010))
        return VA_STATUS_ERROR_UNIMPLEMENTED;
    pthread_mutex_lock(&drv->lock);
    int ret = ensure_decodable_backing(drv, surface_id, s);
    if (!ret && !backing_map(s->backing))
        ret = -ENOMEM;
    if (!ret) {
        struct nv12_planes src = planes_of_image(image, b->data);
        struct nv12_planes dst = planes_of_backing(s);
        unsigned bytes = min_of(min_of(src_width, image->width), s->width) * bytes_per_sample(s->fourcc);
        unsigned rows = min_of(min_of(src_height, image->height), s->height);
        sync_backing(s->backing, DMA_BUF_SYNC_START);
        for (unsigned row = 0; row < rows; row++)
            memcpy(dst.luma + (size_t)row * dst.luma_pitch, src.luma + (size_t)row * src.luma_pitch,
                   bytes);
        for (unsigned row = 0; row < (rows + 1) / 2; row++)
            memcpy(dst.chroma + (size_t)row * dst.chroma_pitch,
                   src.chroma + (size_t)row * src.chroma_pitch, (bytes + 1) & ~1u);
        sync_backing(s->backing, DMA_BUF_SYNC_END);
    }
    pthread_mutex_unlock(&drv->lock);
    return ret ? VA_STATUS_ERROR_ALLOCATION_FAILED : VA_STATUS_SUCCESS;
}

static VAStatus acquire_buffer_handle(VADriverContextP ctx, VABufferID buf_id, VABufferInfo *info)
{
    struct va_buffer *b = handle_get(DRIVER(ctx), &DRIVER(ctx)->buffers, buf_id);
    if (!b)
        return VA_STATUS_ERROR_INVALID_BUFFER;
    if (!b->derived_from || (info->mem_type && !(info->mem_type & (VA_SURFACE_ATTRIB_MEM_TYPE_DRM_PRIME |
                                                                    VA_SURFACE_ATTRIB_MEM_TYPE_KERNEL_DRM))))
        return VA_STATUS_ERROR_UNSUPPORTED_MEMORY_TYPE;
    info->handle = b->derived_from->backing->fd;
    info->type = b->type;
    info->mem_type = VA_SURFACE_ATTRIB_MEM_TYPE_DRM_PRIME;
    info->mem_size = b->derived_from->backing->size;
    return VA_STATUS_SUCCESS;
}

static VAStatus release_buffer_handle(VADriverContextP ctx, VABufferID buf_id)
{
    return handle_get(DRIVER(ctx), &DRIVER(ctx)->buffers, buf_id) ? VA_STATUS_SUCCESS
                                                                  : VA_STATUS_ERROR_INVALID_BUFFER;
}

void surface_vtable(struct VADriverVTable *vt)
{
    vt->vaCreateSurfaces = create_surfaces;
    vt->vaCreateSurfaces2 = create_surfaces2;
    vt->vaDestroySurfaces = destroy_surfaces;
    vt->vaQuerySurfaceAttributes = query_surface_attributes;
    vt->vaSyncSurface = sync_surface;
    vt->vaQuerySurfaceStatus = query_surface_status;
    vt->vaExportSurfaceHandle = export_surface_handle;
    vt->vaQueryImageFormats = query_image_formats;
    vt->vaCreateImage = create_image;
    vt->vaDeriveImage = derive_image;
    vt->vaDestroyImage = destroy_image;
    vt->vaGetImage = get_image;
    vt->vaPutImage = put_image;
    vt->vaAcquireBufferHandle = acquire_buffer_handle;
    vt->vaReleaseBufferHandle = release_buffer_handle;
}
