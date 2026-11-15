#ifndef VAAPI_PIXELS_H
#define VAAPI_PIXELS_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

struct engine_picture;

/* A region of an NV12 or P010 picture in CPU memory: a surface's backing or an image. */
struct nv12_planes {
    uint8_t *luma;
    uint8_t *chroma;
    unsigned luma_pitch;
    unsigned chroma_pitch;
    unsigned width;
    unsigned height;
    bool ten_bit;
};

enum layout { LAYOUT_I420, LAYOUT_NV12, LAYOUT_I010, LAYOUT_P010, LAYOUT_NV15 };

/* Where a source picture's samples are, whatever memory holds them. */
struct source {
    enum layout layout;
    const uint8_t *data[3];
    ptrdiff_t pitch[3];
};

/* src from its (x, y) into dst, NV12 or P010 out */
int pixels_copy(const struct source *src, unsigned x, unsigned y, const struct nv12_planes *dst);
/* an engine's dma-buf picture, mapped for the copy */
int pixels_from_engine(const struct engine_picture *p, unsigned x, unsigned y,
                       const struct nv12_planes *dst);
/* NV12 to three planes, for an encoder that takes I420 */
void pixels_nv12_to_i420(const struct nv12_planes *src, uint8_t *const data[3],
                         const int pitch[3]);

#endif
