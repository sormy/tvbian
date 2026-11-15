/* Copies between engine pictures, surface memory and images: NV12 and P010 out. */
#include "pixels.h"

#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>

#include <drm_fourcc.h>
#include <linux/dma-buf.h>

#include "driver.h"

#define P010_SHIFT 6
#define NV15_SAMPLES_PER_GROUP 4
#define NV15_BYTES_PER_GROUP 5
#define NV15_SAMPLE_BITS 10
#define NV15_SAMPLE_MASK 0x3ff

#ifndef DRM_FORMAT_NV15
#define DRM_FORMAT_NV15 fourcc_code('N', 'V', '1', '5')
#endif

static bool is_ten_bit(enum layout layout)
{
    return layout == LAYOUT_I010 || layout == LAYOUT_P010 || layout == LAYOUT_NV15;
}

static void nv15_unpack(uint16_t *dst, const uint8_t *src, unsigned first, unsigned count)
{
    for (unsigned i = first; i < first + count; i++) {
        const uint8_t *group = src + (i / NV15_SAMPLES_PER_GROUP) * NV15_BYTES_PER_GROUP;
        unsigned bit = (i % NV15_SAMPLES_PER_GROUP) * NV15_SAMPLE_BITS;
        unsigned pair = group[bit / 8] | group[bit / 8 + 1] << 8;
        *dst++ = ((pair >> (bit % 8)) & NV15_SAMPLE_MASK) << P010_SHIFT;
    }
}

static void copy_luma_row(uint8_t *dst, const struct source *s, unsigned x, unsigned y,
                          unsigned width)
{
    const uint8_t *row = s->data[0] + (ptrdiff_t)y * s->pitch[0];
    switch (s->layout) {
    case LAYOUT_I420:
    case LAYOUT_NV12:
        memcpy(dst, row + x, width);
        break;
    case LAYOUT_P010:
        memcpy(dst, row + 2 * x, 2 * width);
        break;
    case LAYOUT_I010:
        for (unsigned i = 0; i < width; i++)
            ((uint16_t *)dst)[i] = ((const uint16_t *)row)[x + i] << P010_SHIFT;
        break;
    case LAYOUT_NV15:
        nv15_unpack((uint16_t *)dst, row, x, width);
        break;
    }
}

/* one row of interleaved chroma, cx and pairs in chroma samples */
static void copy_chroma_row(uint8_t *dst, const struct source *s, unsigned cx, unsigned cy,
                            unsigned pairs)
{
    const uint8_t *row = s->data[1] + (ptrdiff_t)cy * s->pitch[1];
    const uint8_t *v_row = s->data[2] ? s->data[2] + (ptrdiff_t)cy * s->pitch[2] : NULL;
    switch (s->layout) {
    case LAYOUT_NV12:
        memcpy(dst, row + 2 * cx, 2 * pairs);
        break;
    case LAYOUT_P010:
        memcpy(dst, row + 4 * cx, 4 * pairs);
        break;
    case LAYOUT_I420:
        for (unsigned i = 0; i < pairs; i++) {
            dst[2 * i] = row[cx + i];
            dst[2 * i + 1] = v_row[cx + i];
        }
        break;
    case LAYOUT_I010:
        for (unsigned i = 0; i < pairs; i++) {
            ((uint16_t *)dst)[2 * i] = ((const uint16_t *)row)[cx + i] << P010_SHIFT;
            ((uint16_t *)dst)[2 * i + 1] = ((const uint16_t *)v_row)[cx + i] << P010_SHIFT;
        }
        break;
    case LAYOUT_NV15:
        nv15_unpack((uint16_t *)dst, row, 2 * cx, 2 * pairs);
        break;
    }
}

/* a 10-bit row, as P010's samples, to 8-bit: its high byte */
static void narrow_row(uint8_t *dst, const uint16_t *wide, unsigned count)
{
    for (unsigned i = 0; i < count; i++)
        dst[i] = (uint8_t)(wide[i] >> 8);
}

/* an 8-bit row to P010's samples: an engine that writes 8 bits of a 10-bit stream */
static void widen_row(uint16_t *dst, const uint8_t *narrow, unsigned count)
{
    for (unsigned i = 0; i < count; i++)
        dst[i] = (uint16_t)(narrow[i] << 8);
}

/* a row as the source wrote it into staging, then to the destination's depth */
static void convert_row(uint8_t *out, const uint8_t *staged, unsigned count, bool narrow)
{
    if (narrow)
        narrow_row(out, (const uint16_t *)staged, count);
    else
        widen_row((uint16_t *)out, staged, count);
}

int pixels_copy(const struct source *s, unsigned x, unsigned y, const struct nv12_planes *dst)
{
    bool narrow = is_ten_bit(s->layout) && !dst->ten_bit;
    bool convert = is_ten_bit(s->layout) != dst->ten_bit;
    unsigned pairs = (dst->width + 1) / 2;
    uint8_t *staged = convert ? malloc(2 * pairs * sizeof(uint16_t)) : NULL;
    if (convert && !staged)
        return -ENOMEM;
    for (unsigned row = 0; row < dst->height; row++) {
        uint8_t *out = dst->luma + (size_t)row * dst->luma_pitch;
        copy_luma_row(convert ? staged : out, s, x, y + row, dst->width);
        if (convert)
            convert_row(out, staged, dst->width, narrow);
    }
    for (unsigned row = 0; row < (dst->height + 1) / 2; row++) {
        uint8_t *out = dst->chroma + (size_t)row * dst->chroma_pitch;
        copy_chroma_row(convert ? staged : out, s, x / 2, y / 2 + row, pairs);
        if (convert)
            convert_row(out, staged, 2 * pairs, narrow);
    }
    free(staged);
    return 0;
}

static int layout_of_drm(uint32_t format, enum layout *layout)
{
    switch (format) {
    case DRM_FORMAT_NV12:
        *layout = LAYOUT_NV12;
        return 0;
    case DRM_FORMAT_YUV420:
        *layout = LAYOUT_I420;
        return 0;
    case DRM_FORMAT_P010:
        *layout = LAYOUT_P010;
        return 0;
    case DRM_FORMAT_NV15:
        *layout = LAYOUT_NV15;
        return 0;
    default:
        return -ENOSYS;
    }
}

static void sync_objects(const struct engine_picture *p, uint64_t flags)
{
    struct dma_buf_sync sync = { .flags = flags | DMA_BUF_SYNC_READ };
    for (unsigned i = 0; i < p->num_objects; i++)
        ioctl(p->fds[i], DMA_BUF_IOCTL_SYNC, &sync);
}

int pixels_from_engine(const struct engine_picture *p, unsigned x, unsigned y,
                       const struct nv12_planes *dst)
{
    void *maps[PICTURE_PLANES] = { 0 };
    struct source s = { 0 };
    int ret = layout_of_drm(p->drm_format, &s.layout);

    if (!ret && p->modifier != DRM_FORMAT_MOD_LINEAR && p->modifier != DRM_FORMAT_MOD_INVALID)
        ret = -ENOSYS;
    for (unsigned i = 0; !ret && i < p->num_objects; i++) {
        maps[i] = mmap(NULL, p->sizes[i], PROT_READ, MAP_SHARED, p->fds[i], 0);
        if (maps[i] == MAP_FAILED) {
            maps[i] = NULL;
            ret = -errno;
        }
    }
    if (!ret) {
        unsigned planes = s.layout == LAYOUT_I420 ? PICTURE_PLANES : PICTURE_PLANES - 1;
        for (unsigned plane = 0; plane < planes; plane++) {
            s.data[plane] = (const uint8_t *)maps[p->plane_object[plane]] + p->plane_offset[plane];
            s.pitch[plane] = p->plane_pitch[plane];
        }
        sync_objects(p, DMA_BUF_SYNC_START);
        ret = pixels_copy(&s, x, y, dst);
        sync_objects(p, DMA_BUF_SYNC_END);
    }
    for (unsigned i = 0; i < p->num_objects; i++)
        if (maps[i])
            munmap(maps[i], p->sizes[i]);
    return ret;
}

void pixels_nv12_to_i420(const struct nv12_planes *src, uint8_t *const data[3],
                         const int pitch[3])
{
    for (unsigned row = 0; row < src->height; row++)
        memcpy(data[0] + (ptrdiff_t)row * pitch[0], src->luma + (size_t)row * src->luma_pitch,
               src->width);
    for (unsigned row = 0; row < (src->height + 1) / 2; row++) {
        const uint8_t *uv = src->chroma + (size_t)row * src->chroma_pitch;
        uint8_t *u = data[1] + (ptrdiff_t)row * pitch[1];
        uint8_t *v = data[2] + (ptrdiff_t)row * pitch[2];
        for (unsigned i = 0; i < (src->width + 1) / 2; i++) {
            u[i] = uv[2 * i];
            v[i] = uv[2 * i + 1];
        }
    }
}
