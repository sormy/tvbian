/* Copies between engine pictures, surface memory and images: NV12 and P010 out. */
#include "pixels.h"

#include <errno.h>
#include <pthread.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>

#if defined(__aarch64__)
#include <arm_neon.h>
#endif

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

/* NV15 samples first.. to 8-bit, their high 8 bits: four from each group's five bytes at once */
#if defined(__aarch64__)
/* 16 samples from four groups' 20 bytes: each the high byte of one group byte shifted right and the
 * next shifted left; the 32-byte load needs 28 samples left */
#define NEON_SAMPLES 16
#define NEON_READ_SAMPLES 28

static unsigned narrow_nv15_neon(uint8_t *dst, const uint8_t *src, unsigned i, unsigned end)
{
    static const uint8_t low_bytes[16] = { 0, 1, 2, 4, 5, 6, 7, 9, 10, 11, 12, 14, 15, 16, 17, 19 };
    static const uint8_t high_bytes[16] = { 1,  2,  3,  0xff, 6,  7,  8,  0xff,
                                            11, 12, 13, 0xff, 16, 17, 18, 0xff };
    static const int8_t right[16] = { -2, -4, -6, 0, -2, -4, -6, 0, -2, -4, -6, 0, -2, -4, -6, 0 };
    static const int8_t left[16] = { 6, 4, 2, 0, 6, 4, 2, 0, 6, 4, 2, 0, 6, 4, 2, 0 };
    const uint8x16_t lows = vld1q_u8(low_bytes), highs = vld1q_u8(high_bytes);
    const int8x16_t shift_right = vld1q_s8(right), shift_left = vld1q_s8(left);
    for (; i + NEON_READ_SAMPLES <= end; i += NEON_SAMPLES, dst += NEON_SAMPLES) {
        uint8x16x2_t in = vld1q_u8_x2(src + i / NV15_SAMPLES_PER_GROUP * NV15_BYTES_PER_GROUP);
        uint8x16_t low = vshlq_u8(vqtbl2q_u8(in, lows), shift_right);
        uint8x16_t high = vshlq_u8(vqtbl2q_u8(in, highs), shift_left);
        vst1q_u8(dst, vorrq_u8(low, high));
    }
    return i;
}
#endif

static void narrow_nv15_row(uint8_t *dst, const uint8_t *src, unsigned first, unsigned count)
{
    unsigned i = first, end = first + count;
    uint16_t sample;
    for (; i < end && i % NV15_SAMPLES_PER_GROUP; i++) {
        nv15_unpack(&sample, src, i, 1);
        *dst++ = (uint8_t)(sample >> 8);
    }
#if defined(__aarch64__)
    unsigned from = i;
    i = narrow_nv15_neon(dst, src, i, end);
    dst += i - from;
#endif
    for (; i + NV15_SAMPLES_PER_GROUP <= end; i += NV15_SAMPLES_PER_GROUP) {
        const uint8_t *g = src + i / NV15_SAMPLES_PER_GROUP * NV15_BYTES_PER_GROUP;
        dst[0] = (uint8_t)(g[0] >> 2 | g[1] << 6);
        dst[1] = (uint8_t)(g[1] >> 4 | g[2] << 4);
        dst[2] = (uint8_t)(g[2] >> 6 | g[3] << 2);
        dst[3] = g[4];
        dst += NV15_SAMPLES_PER_GROUP;
    }
    for (; i < end; i++) {
        nv15_unpack(&sample, src, i, 1);
        *dst++ = (uint8_t)(sample >> 8);
    }
}

/* NV15 rows to 8-bit, as one plane's share */
struct nv15_rows {
    uint8_t *dst;
    unsigned dst_pitch;
    const uint8_t *src;
    ptrdiff_t src_pitch;
    unsigned first, count, rows;
};

/* each row copied whole into cached memory first: an engine's picture may be uncached, where the
 * narrowing's overlapping loads read it several times over */
static void *narrow_nv15_rows(void *arg)
{
    const struct nv15_rows *r = arg;
    size_t bytes = (size_t)(r->first + r->count + NV15_SAMPLES_PER_GROUP - 1) /
                   NV15_SAMPLES_PER_GROUP * NV15_BYTES_PER_GROUP;
    uint8_t *row_copy = malloc(bytes);
    for (unsigned row = 0; row < r->rows; row++) {
        const uint8_t *src = r->src + row * r->src_pitch;
        if (row_copy)
            src = memcpy(row_copy, src, bytes);
        narrow_nv15_row(r->dst + (size_t)row * r->dst_pitch, src, r->first, r->count);
    }
    free(row_copy);
    return NULL;
}

/* the luma's top half on a second core, the rest here: a 4K picture is 12 MB to narrow */
static void narrow_nv15(const struct source *s, unsigned x, unsigned y, const struct nv12_planes *d)
{
    unsigned top = d->height / 2, pairs = (d->width + 1) / 2;
    struct nv15_rows upper = { d->luma, d->luma_pitch, s->data[0] + (ptrdiff_t)y * s->pitch[0],
                               s->pitch[0], x, d->width, top };
    struct nv15_rows lower = upper;
    lower.dst += (size_t)top * d->luma_pitch;
    lower.src += (ptrdiff_t)top * s->pitch[0];
    lower.rows = d->height - top;
    struct nv15_rows chroma = { d->chroma, d->chroma_pitch,
                                s->data[1] + (ptrdiff_t)(y / 2) * s->pitch[1], s->pitch[1],
                                x / 2 * 2, 2 * pairs, (d->height + 1) / 2 };
    pthread_t helper;
    bool helped = !pthread_create(&helper, NULL, narrow_nv15_rows, &upper);
    if (!helped)
        narrow_nv15_rows(&upper);
    narrow_nv15_rows(&lower);
    narrow_nv15_rows(&chroma);
    if (helped)
        pthread_join(helper, NULL);
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
    if (narrow && s->layout == LAYOUT_NV15) {
        narrow_nv15(s, x, y, dst);
        return 0;
    }
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
